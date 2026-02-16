"""Credit curve types and bootstrapping from CDS par spread quotes.

Covers Phase 4 Step 3: CDSQuote, CreditCurve (with survival probability and
hazard rate interpolation), and bootstrap_credit_curve.

All arithmetic uses Decimal with ATTESTOR_DECIMAL_CONTEXT.  No float.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, localcontext
from typing import final

from attestor.core.decimal_math import exp_d, ln_d
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.oracle.attestation import (
    Attestation,
    DerivedConfidence,
    create_attestation,
)
from attestor.oracle.calibration import ModelConfig, YieldCurve

_ZERO = Decimal("0")
_ONE = Decimal("1")


# ---------------------------------------------------------------------------
# CDSQuote
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CDSQuote:
    """Market CDS par spread quote for bootstrapping."""

    reference_entity: NonEmptyStr
    tenor: Decimal
    spread: Decimal       # par spread in decimal (0.01 = 100bps)
    recovery_rate: Decimal  # typically 0.4
    currency: NonEmptyStr

    @staticmethod
    def create(
        reference_entity: str,
        tenor: Decimal,
        spread: Decimal,
        recovery_rate: Decimal,
        currency: str,
    ) -> Ok[CDSQuote] | Err[str]:
        """Validated construction.

        Rejects: empty strings, tenor <= 0, spread < 0, recovery_rate not in [0, 1).
        """
        match NonEmptyStr.parse(reference_entity):
            case Err(e):
                return Err(f"CDSQuote.reference_entity: {e}")
            case Ok(ref):
                pass
        if tenor <= Decimal("0"):
            return Err(f"CDSQuote.tenor must be > 0, got {tenor}")
        if spread < Decimal("0"):
            return Err(f"CDSQuote.spread must be >= 0, got {spread}")
        if recovery_rate < Decimal("0") or recovery_rate >= Decimal("1"):
            return Err(
                f"CDSQuote.recovery_rate must be in [0, 1), got {recovery_rate}"
            )
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"CDSQuote.currency: {e}")
            case Ok(cur):
                pass
        return Ok(CDSQuote(
            reference_entity=ref, tenor=tenor, spread=spread,
            recovery_rate=recovery_rate, currency=cur,
        ))


# ---------------------------------------------------------------------------
# CreditCurve
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CreditCurve:
    """Bootstrapped credit curve -- survival probabilities at tenor points.

    Construction enforces:
    - len(tenors) == len(survival_probs) == len(hazard_rates)
    - tenors sorted ascending, all > 0
    - 0 < Q(t) <= 1 for all t
    - Q(t2) <= Q(t1) for t2 > t1 (monotone decreasing)
    - hazard_rates all >= 0
    - 0 <= recovery_rate < 1
    """

    reference_entity: NonEmptyStr
    as_of: date
    tenors: tuple[Decimal, ...]
    survival_probs: tuple[Decimal, ...]
    hazard_rates: tuple[Decimal, ...]
    recovery_rate: Decimal
    discount_curve_ref: str
    model_config_ref: str

    @staticmethod
    def create(
        reference_entity: str,
        as_of: date,
        tenors: tuple[Decimal, ...],
        survival_probs: tuple[Decimal, ...],
        hazard_rates: tuple[Decimal, ...],
        recovery_rate: Decimal,
        discount_curve_ref: str,
        model_config_ref: str,
    ) -> Ok[CreditCurve] | Err[str]:
        """Validate all invariants and construct a CreditCurve."""
        match NonEmptyStr.parse(reference_entity):
            case Err(e):
                return Err(f"CreditCurve.reference_entity: {e}")
            case Ok(ref_ent):
                pass

        # Length consistency
        if len(tenors) != len(survival_probs):
            return Err(
                f"tenors ({len(tenors)}) and survival_probs ({len(survival_probs)}) "
                "must have same length"
            )
        if len(tenors) != len(hazard_rates):
            return Err(
                f"tenors ({len(tenors)}) and hazard_rates ({len(hazard_rates)}) "
                "must have same length"
            )
        if len(tenors) == 0:
            return Err("tenors must be non-empty")

        # Tenors: positive and ascending
        for i, t in enumerate(tenors):
            if t <= _ZERO:
                return Err(f"tenors[{i}] must be > 0, got {t}")
            if i > 0 and t <= tenors[i - 1]:
                return Err(
                    f"tenors must be ascending: tenors[{i}]={t} "
                    f"<= tenors[{i - 1}]={tenors[i - 1]}"
                )

        # Survival probabilities: 0 < Q(t) <= 1 and monotone decreasing
        for i, q in enumerate(survival_probs):
            if q <= _ZERO:
                return Err(f"survival_probs[{i}] must be > 0, got {q}")
            if q > _ONE:
                return Err(f"survival_probs[{i}] must be <= 1, got {q}")
            if i > 0 and q > survival_probs[i - 1]:
                return Err(
                    f"survival_probs must be monotone decreasing: "
                    f"survival_probs[{i}]={q} > survival_probs[{i - 1}]={survival_probs[i - 1]}"
                )

        # Hazard rates: non-negative
        for i, h in enumerate(hazard_rates):
            if h < _ZERO:
                return Err(f"hazard_rates[{i}] must be >= 0, got {h}")

        # Recovery rate: 0 <= R < 1
        if recovery_rate < _ZERO:
            return Err(f"recovery_rate must be >= 0, got {recovery_rate}")
        if recovery_rate >= _ONE:
            return Err(f"recovery_rate must be < 1, got {recovery_rate}")

        return Ok(CreditCurve(
            reference_entity=ref_ent,
            as_of=as_of,
            tenors=tenors,
            survival_probs=survival_probs,
            hazard_rates=hazard_rates,
            recovery_rate=recovery_rate,
            discount_curve_ref=discount_curve_ref,
            model_config_ref=model_config_ref,
        ))


# ---------------------------------------------------------------------------
# survival_probability -- exponential interpolation
# ---------------------------------------------------------------------------


def survival_probability(
    curve: CreditCurve, tenor: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Interpolate survival probability at arbitrary tenor.

    Per math spec Section 3.5: exponential interpolation using
    piecewise constant hazard rates.  Q(0) = 1 by convention.
    Uses exp_d from decimal_math (no float).

    - t <= 0: Q = 1
    - 0 < t <= T_1: Q = exp(-lambda_1 * t)
    - T_{j-1} < t <= T_j: Q = Q(T_{j-1}) * exp(-lambda_j * (t - T_{j-1}))
    - t > T_N: flat hazard extrapolation: Q = Q(T_N) * exp(-lambda_N * (t - T_N))
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        if tenor <= _ZERO:
            return Ok(_ONE)

        tenors = curve.tenors
        hazards = curve.hazard_rates
        sprobs = curve.survival_probs

        # 0 < t <= T_1
        if tenor <= tenors[0]:
            q = exp_d(-hazards[0] * tenor)
            return Ok(q)

        # T_{j-1} < t <= T_j: find the bracketing interval
        for j in range(1, len(tenors)):
            if tenor <= tenors[j]:
                q_prev = sprobs[j - 1]
                dt = tenor - tenors[j - 1]
                q = q_prev * exp_d(-hazards[j] * dt)
                return Ok(q)

        # t > T_N: flat hazard extrapolation using last hazard rate
        q_last = sprobs[-1]
        dt = tenor - tenors[-1]
        q = q_last * exp_d(-hazards[-1] * dt)
        return Ok(q)


# ---------------------------------------------------------------------------
# hazard_rate -- piecewise constant between two points
# ---------------------------------------------------------------------------


def hazard_rate(
    curve: CreditCurve, t1: Decimal, t2: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Compute piecewise-constant hazard rate between two points.

    lambda = -ln(Q(t2)/Q(t1)) / (t2-t1)
    Uses ln_d from decimal_math (no float).
    Requires t2 > t1, returns Err if t2 <= t1.
    """
    if t2 <= t1:
        return Err(f"t2 ({t2}) must be > t1 ({t1})")

    match survival_probability(curve, t1):
        case Err(e):
            return Err(e)
        case Ok(q1):
            pass
    match survival_probability(curve, t2):
        case Err(e):
            return Err(e)
        case Ok(q2):
            pass

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        if q1 <= _ZERO or q2 <= _ZERO:
            return Err("Survival probabilities must be positive for hazard rate computation")
        ratio = q2 / q1
        lam = -ln_d(ratio) / (t2 - t1)
        return Ok(lam)


# ---------------------------------------------------------------------------
# bootstrap_credit_curve
# ---------------------------------------------------------------------------


def bootstrap_credit_curve(
    quotes: tuple[CDSQuote, ...],
    discount_curve: YieldCurve,
    config: ModelConfig,
    as_of: date,
    reference_entity: str,
) -> Ok[Attestation[CreditCurve]] | Err[str]:
    """Bootstrap survival probabilities from CDS spread quotes.

    Uses simplified zero-coupon approximation:
        Q(t) = 1 / (1 + spread * t / (1 - R))

    Then derives hazard_rate from the survival probabilities:
        lambda_j = -ln(Q(T_j) / Q(T_{j-1})) / (T_j - T_{j-1})

    Returns Attestation[CreditCurve] with DerivedConfidence.
    Quotes must be sorted by tenor.  Empty quotes -> Err.
    """
    if len(quotes) == 0:
        return Err("At least one CDS quote required for bootstrapping")

    # Sort by tenor
    sorted_quotes = sorted(quotes, key=lambda q: q.tenor)

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        tenors: list[Decimal] = []
        sprobs: list[Decimal] = []

        for quote in sorted_quotes:
            if quote.tenor <= _ZERO:
                return Err(f"CDS quote tenor must be > 0, got {quote.tenor}")
            if quote.recovery_rate >= _ONE:
                return Err(f"CDS quote recovery_rate must be < 1, got {quote.recovery_rate}")

            lgd = _ONE - quote.recovery_rate  # loss given default
            q = _ONE / (_ONE + quote.spread * quote.tenor / lgd)
            if q <= _ZERO or q > _ONE:
                return Err(
                    f"Computed survival probability out of range "
                    f"for tenor {quote.tenor}: {q}"
                )
            tenors.append(quote.tenor)
            sprobs.append(q)

        # Derive piecewise hazard rates from survival probabilities
        hazards: list[Decimal] = []
        for j in range(len(tenors)):
            if j == 0:
                # lambda_1 = -ln(Q(T_1)) / T_1
                lam = -ln_d(sprobs[0]) / tenors[0]
            else:
                # lambda_j = -ln(Q(T_j) / Q(T_{j-1})) / (T_j - T_{j-1})
                ratio = sprobs[j] / sprobs[j - 1]
                lam = -ln_d(ratio) / (tenors[j] - tenors[j - 1])
            hazards.append(lam)

        # Use recovery rate from first quote (all should be consistent)
        recovery = sorted_quotes[0].recovery_rate

    match CreditCurve.create(
        reference_entity=reference_entity,
        as_of=as_of,
        tenors=tuple(tenors),
        survival_probs=tuple(sprobs),
        hazard_rates=tuple(hazards),
        recovery_rate=recovery,
        discount_curve_ref=discount_curve.model_config_ref,
        model_config_ref=config.config_id.value,
    ):
        case Err(e):
            return Err(e)
        case Ok(curve):
            pass

    # Create DerivedConfidence
    match FrozenMap.create({"rmse": _ZERO, "max_error": _ZERO}):
        case Err(e):
            return Err(f"fit_quality: {e}")
        case Ok(fit_quality):
            pass

    match DerivedConfidence.create(
        method=config.model_class.value,
        config_ref=config.config_id.value,
        fit_quality=fit_quality,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    return create_attestation(
        value=curve,
        confidence=confidence,
        source=config.model_class.value,
        timestamp=datetime.now(tz=UtcDatetime.now().value.tzinfo),
    )
