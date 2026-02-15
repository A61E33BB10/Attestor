"""Yield curve bootstrapping, model configuration, and calibration failure handling.

Covers III-04 (yield curves), III-06 (ModelConfig attestation), and
III-08 (calibration failure handling with fallback).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import final

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.oracle.attestation import (
    Attestation,
    DerivedConfidence,
    create_attestation,
)

# ---------------------------------------------------------------------------
# ModelConfig
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ModelConfig:
    """Immutable model configuration for calibration."""

    config_id: NonEmptyStr
    model_class: NonEmptyStr  # e.g. "PIECEWISE_LOG_LINEAR"
    code_version: NonEmptyStr
    parameters: FrozenMap[str, Decimal]

    @staticmethod
    def create(
        config_id: str,
        model_class: str,
        code_version: str,
        parameters: dict[str, Decimal] | None = None,
    ) -> Ok[ModelConfig] | Err[str]:
        match NonEmptyStr.parse(config_id):
            case Err(e):
                return Err(f"ModelConfig.config_id: {e}")
            case Ok(cid):
                pass
        match NonEmptyStr.parse(model_class):
            case Err(e):
                return Err(f"ModelConfig.model_class: {e}")
            case Ok(mc):
                pass
        match NonEmptyStr.parse(code_version):
            case Err(e):
                return Err(f"ModelConfig.code_version: {e}")
            case Ok(cv):
                pass
        match FrozenMap.create(parameters or {}):
            case Err(e):
                return Err(f"ModelConfig.parameters: {e}")
            case Ok(params):
                pass
        return Ok(ModelConfig(config_id=cid, model_class=mc, code_version=cv, parameters=params))


# ---------------------------------------------------------------------------
# YieldCurve
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class YieldCurve:
    """Bootstrapped yield curve — discount factors at tenor points."""

    currency: NonEmptyStr
    as_of: date
    tenors: tuple[Decimal, ...]
    discount_factors: tuple[Decimal, ...]
    model_config_ref: str

    @staticmethod
    def create(
        currency: str,
        as_of: date,
        tenors: tuple[Decimal, ...],
        discount_factors: tuple[Decimal, ...],
        model_config_ref: str,
    ) -> Ok[YieldCurve] | Err[str]:
        """Validate yield curve construction.

        Enforced:
        - len(tenors) == len(discount_factors)
        - tenors sorted ascending, all > 0
        - all discount factors > 0
        """
        match NonEmptyStr.parse(currency):
            case Err(e):
                return Err(f"YieldCurve.currency: {e}")
            case Ok(cur):
                pass
        if len(tenors) != len(discount_factors):
            return Err(
                f"tenors ({len(tenors)}) and discount_factors ({len(discount_factors)}) "
                "must have same length"
            )
        if len(tenors) == 0:
            return Err("tenors must be non-empty")
        for i, t in enumerate(tenors):
            if t <= 0:
                return Err(f"tenors[{i}] must be > 0, got {t}")
            if i > 0 and t <= tenors[i - 1]:
                return Err(
                    f"tenors must be ascending: tenors[{i}]={t} "
                    f"<= tenors[{i-1}]={tenors[i-1]}"
                )
        for i, d in enumerate(discount_factors):
            if d <= 0:
                return Err(f"discount_factors[{i}] must be > 0, got {d}")
        return Ok(YieldCurve(
            currency=cur, as_of=as_of, tenors=tenors,
            discount_factors=discount_factors, model_config_ref=model_config_ref,
        ))


def discount_factor(curve: YieldCurve, tenor: Decimal) -> Ok[Decimal] | Err[str]:
    """Interpolate discount factor at arbitrary tenor (log-linear)."""
    if tenor <= 0:
        return Ok(Decimal("1"))  # D(0) = 1 by convention

    tenors = curve.tenors
    dfs = curve.discount_factors

    if tenor <= tenors[0]:
        # Extrapolate from D(0)=1 to first point
        ln_d = float(tenor) / float(tenors[0]) * math.log(float(dfs[0]))
        return Ok(Decimal(str(math.exp(ln_d))))

    if tenor >= tenors[-1]:
        # Flat extrapolation beyond last point
        return Ok(dfs[-1])

    # Find bracketing points
    for i in range(len(tenors) - 1):
        if tenors[i] <= tenor <= tenors[i + 1]:
            t1, t2 = float(tenors[i]), float(tenors[i + 1])
            d1, d2 = float(dfs[i]), float(dfs[i + 1])
            w = (float(tenor) - t1) / (t2 - t1)
            ln_d = (1 - w) * math.log(d1) + w * math.log(d2)
            return Ok(Decimal(str(math.exp(ln_d))))

    return Err(f"Cannot interpolate at tenor={tenor}")


def forward_rate(
    curve: YieldCurve, t1: Decimal, t2: Decimal,
) -> Ok[Decimal] | Err[str]:
    """Compute forward rate f(t1, t2) = -ln(D(t2)/D(t1)) / (t2 - t1)."""
    if t2 <= t1:
        return Err(f"t2 ({t2}) must be > t1 ({t1})")
    match discount_factor(curve, t1):
        case Err(e):
            return Err(e)
        case Ok(d1):
            pass
    match discount_factor(curve, t2):
        case Err(e):
            return Err(e)
        case Ok(d2):
            pass
    if d1 <= 0 or d2 <= 0:
        return Err("Discount factors must be positive")
    fwd = -Decimal(str(math.log(float(d2) / float(d1)))) / (t2 - t1)
    return Ok(fwd)


# ---------------------------------------------------------------------------
# Rate instruments for bootstrapping
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class RateInstrument:
    """Input instrument for bootstrapping (deposit, swap, future)."""

    instrument_type: NonEmptyStr
    tenor: Decimal
    rate: Decimal
    currency: NonEmptyStr


def bootstrap_curve(
    instruments: tuple[RateInstrument, ...],
    config: ModelConfig,
    as_of: date,
    currency: str,
) -> Ok[Attestation[YieldCurve]] | Err[str]:
    """Bootstrap a yield curve from market instruments.

    Uses simple conversion: D(t) = 1 / (1 + r*t) for deposits.
    Returns Attestation[YieldCurve] with DerivedConfidence.
    """
    if len(instruments) == 0:
        return Err("At least one instrument required for bootstrapping")

    # Sort by tenor
    sorted_insts = sorted(instruments, key=lambda i: i.tenor)

    tenors: list[Decimal] = []
    dfs: list[Decimal] = []
    for inst in sorted_insts:
        if inst.tenor <= 0:
            return Err(f"Instrument tenor must be > 0, got {inst.tenor}")
        d = Decimal("1") / (Decimal("1") + inst.rate * inst.tenor)
        if d <= 0:
            return Err(f"Computed discount factor <= 0 for tenor {inst.tenor}")
        tenors.append(inst.tenor)
        dfs.append(d)

    match YieldCurve.create(
        currency=currency,
        as_of=as_of,
        tenors=tuple(tenors),
        discount_factors=tuple(dfs),
        model_config_ref=config.config_id.value,
    ):
        case Err(e):
            return Err(e)
        case Ok(curve):
            pass

    # Create DerivedConfidence
    match FrozenMap.create({"rmse": Decimal("0"), "max_error": Decimal("0")}):
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


# ---------------------------------------------------------------------------
# ModelConfig attestation (III-06)
# ---------------------------------------------------------------------------


def create_model_config_attestation(
    config: ModelConfig,
    source: str,
    timestamp: datetime,
) -> Ok[Attestation[ModelConfig]] | Err[str]:
    """Create an immutable ModelConfig attestation."""
    match FrozenMap.create({"model": Decimal("1")}):
        case Err(e):
            return Err(f"fit_quality: {e}")
        case Ok(fq):
            pass
    match DerivedConfidence.create(
        method="MODEL_CONFIG",
        config_ref=config.config_id.value,
        fit_quality=fq,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass
    return create_attestation(
        value=config, confidence=confidence, source=source, timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# Calibration failure handling (III-08)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CalibrationResult:
    """Result of a calibration attempt."""

    curve: YieldCurve | None
    model_config: ModelConfig
    passed: bool


@final
@dataclass(frozen=True, slots=True)
class FailedCalibrationRecord:
    """Published when calibration fails."""

    model_class: NonEmptyStr
    reason: NonEmptyStr
    fallback_config_ref: str | None
    timestamp: UtcDatetime


def handle_calibration_failure(
    error_reason: str,
    model_config: ModelConfig,
    last_good: Attestation[YieldCurve] | None,
    timestamp: datetime,
) -> Ok[Attestation[YieldCurve]] | Err[str]:
    """Handle calibration failure with fallback to last-good curve.

    III-08: Falls back to last-good snapshot. If no last-good exists, returns Err.
    """
    if last_good is None:
        return Err(f"Calibration failed ({error_reason}) and no fallback available")
    return Ok(last_good)
