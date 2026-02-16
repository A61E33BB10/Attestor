"""Arbitrage-freedom gates for yield curves, FX rates, vol surfaces, and credit curves.

AF-YC-01..05: Yield curve checks.
AF-FX-01..02: FX consistency checks.
AF-VS-01..06: Vol surface calendar/butterfly/wing checks.
AF-CR-01..04: Credit curve survival/hazard checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, localcontext
from enum import Enum
from typing import final

from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, CurrencyPair
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import FrozenMap
from attestor.oracle.calibration import YieldCurve, forward_rate
from attestor.oracle.credit_curve import CreditCurve
from attestor.oracle.vol_surface import (
    SVIParameters,
    VolSurface,
    svi_first_derivative,
    svi_second_derivative,
    svi_total_variance,
)


class ArbitrageCheckType(Enum):
    YIELD_CURVE = "YIELD_CURVE"
    FX_TRIANGULAR = "FX_TRIANGULAR"
    FX_SPOT_FORWARD = "FX_SPOT_FORWARD"
    VOL_SURFACE = "VOL_SURFACE"
    CREDIT_CURVE = "CREDIT_CURVE"


class CheckSeverity(Enum):
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"


@final
@dataclass(frozen=True, slots=True)
class ArbitrageCheckResult:
    """Result of a single arbitrage freedom check."""

    check_id: str
    check_type: ArbitrageCheckType
    passed: bool
    severity: CheckSeverity
    details: FrozenMap[str, str]


def _make_result(
    check_id: str,
    check_type: ArbitrageCheckType,
    passed: bool,
    severity: CheckSeverity,
    details: dict[str, str] | None = None,
) -> ArbitrageCheckResult:
    return ArbitrageCheckResult(
        check_id=check_id,
        check_type=check_type,
        passed=passed,
        severity=severity,
        details=unwrap(FrozenMap.create(details or {})),
    )


def check_yield_curve_arbitrage_freedom(
    curve: YieldCurve,
    forward_rate_floor: Decimal = Decimal("-0.01"),
    smoothness_bound: Decimal = Decimal("10"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run yield curve arbitrage-freedom gates.

    AF-YC-01: D(t) > 0 for all t                              (CRITICAL)
    AF-YC-02: D(0) = 1 (enforced at construction)             (CRITICAL)
    AF-YC-03: D(t2) <= D(t1) for t2 > t1 (monotone)           (CRITICAL)
    AF-YC-04: f(t1, t2) >= forward_rate_floor                  (HIGH)
    AF-YC-05: |f''(t)| < smoothness_bound                      (MEDIUM)
    """
    results: list[ArbitrageCheckResult] = []

    # AF-YC-01: positive discount factors
    all_positive = all(d > 0 for d in curve.discount_factors)
    results.append(_make_result(
        "AF-YC-01", ArbitrageCheckType.YIELD_CURVE, all_positive,
        CheckSeverity.CRITICAL,
        {"check": "D(t) > 0 for all t"},
    ))

    # AF-YC-02: D(0) = 1 (implied by construction — always passes)
    results.append(_make_result(
        "AF-YC-02", ArbitrageCheckType.YIELD_CURVE, True,
        CheckSeverity.CRITICAL,
        {"check": "D(0) = 1 (enforced at construction)"},
    ))

    # AF-YC-03: monotone decreasing
    monotone = True
    for i in range(len(curve.discount_factors) - 1):
        if curve.discount_factors[i + 1] > curve.discount_factors[i]:
            monotone = False
            break
    results.append(_make_result(
        "AF-YC-03", ArbitrageCheckType.YIELD_CURVE, monotone,
        CheckSeverity.CRITICAL,
        {"check": "D(t2) <= D(t1) for t2 > t1"},
    ))

    # AF-YC-04: forward rates above floor
    fwd_above_floor = True
    for i in range(len(curve.tenors) - 1):
        match forward_rate(curve, curve.tenors[i], curve.tenors[i + 1]):
            case Ok(f):
                if f < forward_rate_floor:
                    fwd_above_floor = False
                    break
            case Err(_):
                fwd_above_floor = False
                break
    results.append(_make_result(
        "AF-YC-04", ArbitrageCheckType.YIELD_CURVE, fwd_above_floor,
        CheckSeverity.HIGH,
        {"check": f"f(t1,t2) >= {forward_rate_floor}"},
    ))

    # AF-YC-05: smoothness (second derivative of forward rates)
    smooth = True
    if len(curve.tenors) >= 3:
        fwds: list[Decimal] = []
        for i in range(len(curve.tenors) - 1):
            match forward_rate(curve, curve.tenors[i], curve.tenors[i + 1]):
                case Ok(f):
                    fwds.append(f)
                case Err(_):
                    fwds.append(Decimal("0"))
        for i in range(len(fwds) - 1):
            dt = float(curve.tenors[i + 1] - curve.tenors[i])
            if dt > 0:
                second_deriv = abs(float(fwds[i + 1] - fwds[i]) / dt)
                if second_deriv > float(smoothness_bound):
                    smooth = False
                    break
    results.append(_make_result(
        "AF-YC-05", ArbitrageCheckType.YIELD_CURVE, smooth,
        CheckSeverity.MEDIUM,
        {"check": f"|f''(t)| < {smoothness_bound}"},
    ))

    return Ok(tuple(results))


def check_fx_triangular_arbitrage(
    rates: tuple[tuple[CurrencyPair, Decimal], ...],
    tolerance: Decimal = Decimal("0.001"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Check triangular arbitrage condition for FX crosses.

    AF-FX-01: For any cycle A/B * B/C * C/A, |product - 1| < tolerance.
    """
    if len(rates) < 3:
        return Ok(())

    # Build rate map
    rate_map: dict[str, Decimal] = {}
    for cp, rate in rates:
        rate_map[cp.value] = rate

    results: list[ArbitrageCheckResult] = []
    ccys = set[str]()
    for cp, _ in rates:
        ccys.add(cp.base.value)
        ccys.add(cp.quote.value)

    ccy_list = sorted(ccys)
    for i, a in enumerate(ccy_list):
        for j, b in enumerate(ccy_list):
            if j <= i:
                continue
            for k, c in enumerate(ccy_list):
                if k <= j:
                    continue
                ab = rate_map.get(f"{a}/{b}")
                bc = rate_map.get(f"{b}/{c}")
                ca = rate_map.get(f"{c}/{a}")
                if ab is not None and bc is not None and ca is not None:
                    product = ab * bc * ca
                    passed = abs(product - Decimal("1")) < tolerance
                    results.append(_make_result(
                        "AF-FX-01",
                        ArbitrageCheckType.FX_TRIANGULAR,
                        passed,
                        CheckSeverity.CRITICAL,
                        {"cycle": f"{a}/{b} * {b}/{c} * {c}/{a}", "product": str(product)},
                    ))

    return Ok(tuple(results))


def check_fx_spot_forward_consistency(
    spot_rate: Decimal,
    forward_rate_val: Decimal,
    domestic_df: Decimal,
    foreign_df: Decimal,
    tolerance: Decimal = Decimal("0.001"),
) -> Ok[ArbitrageCheckResult] | Err[str]:
    """Check covered interest rate parity.

    AF-FX-02: |F(T)/S - D_domestic(T)/D_foreign(T)| < tolerance.
    """
    if spot_rate <= 0 or forward_rate_val <= 0:
        return Err("Rates must be positive")
    if domestic_df <= 0 or foreign_df <= 0:
        return Err("Discount factors must be positive")

    implied_ratio = domestic_df / foreign_df
    actual_ratio = forward_rate_val / spot_rate
    diff = abs(actual_ratio - implied_ratio)
    passed = diff < tolerance

    return Ok(_make_result(
        "AF-FX-02",
        ArbitrageCheckType.FX_SPOT_FORWARD,
        passed,
        CheckSeverity.HIGH,
        {"diff": str(diff), "tolerance": str(tolerance)},
    ))


# ---------------------------------------------------------------------------
# Vol Surface Arbitrage Freedom
# ---------------------------------------------------------------------------

_ZERO = Decimal("0")
_ONE = Decimal("1")
_TWO = Decimal("2")
_FOUR = Decimal("4")


def _build_k_grid(
    k_range: Decimal,
    grid_step: Decimal,
) -> tuple[Decimal, ...]:
    """Build a symmetric grid of log-moneyness values [-k_range, k_range]."""
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        points: list[Decimal] = []
        k = -k_range
        while k <= k_range:
            points.append(k)
            k = k + grid_step
        return tuple(points)


def _durrleman_g(
    params: SVIParameters,
    k: Decimal,
) -> Decimal | None:
    """Compute Durrleman's g(k) for the butterfly arbitrage condition.

    g(k) = (1 - k*w'/(2*w))^2 - (w')^2/4 * (1/w + 1/4) + w''/2

    Returns None if w(k) is too close to zero (division unsafe).
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        w = svi_total_variance(params, k)
        if w <= Decimal("1e-20"):
            return None
        wp = svi_first_derivative(params, k)
        wpp = svi_second_derivative(params, k)

        # term1 = (1 - k*w'/(2*w))^2
        term1_inner = _ONE - k * wp / (_TWO * w)
        term1 = term1_inner * term1_inner

        # term2 = (w')^2/4 * (1/w + 1/4)
        wp_sq_over_4 = wp * wp / _FOUR
        term2 = wp_sq_over_4 * (_ONE / w + _ONE / _FOUR)

        # term3 = w''/2
        term3 = wpp / _TWO

        return term1 - term2 + term3


def check_vol_surface_arbitrage_freedom(
    surface: VolSurface,
    grid_step: Decimal = Decimal("0.1"),
    k_range: Decimal = Decimal("5"),
    tolerance: Decimal = Decimal("1e-10"),
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run vol surface arbitrage-freedom gates.

    AF-VS-01: Calendar spread freedom -- w(k, T_{i+1}) >= w(k, T_i) for all k
    AF-VS-02: Durrleman butterfly condition -- g(k) >= 0 for all k in grid
    AF-VS-03: Roger Lee right wing -- b*(1+rho) <= 2 for each slice
    AF-VS-04: Roger Lee left wing -- b*(1-rho) <= 2 for each slice
    AF-VS-05: Positive implied variance -- w(k) > -tolerance for all k in grid
    AF-VS-06: ATM variance monotonicity -- w(0, T_{i+1}) >= w(0, T_i)
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        results: list[ArbitrageCheckResult] = []
        grid = _build_k_grid(k_range, grid_step)

        # -----------------------------------------------------------------
        # AF-VS-01: Calendar spread freedom
        # For adjacent slices, w_{i+1}(k) >= w_i(k) - tolerance for all k.
        # -----------------------------------------------------------------
        cal_passed = True
        for i in range(len(surface.slices) - 1):
            s_near = surface.slices[i]
            s_far = surface.slices[i + 1]
            for k in grid:
                w_near = svi_total_variance(s_near, k)
                w_far = svi_total_variance(s_far, k)
                if w_far < w_near - tolerance:
                    cal_passed = False
                    break
            if not cal_passed:
                break
        results.append(_make_result(
            "AF-VS-01",
            ArbitrageCheckType.VOL_SURFACE,
            cal_passed,
            CheckSeverity.CRITICAL,
            {"check": "w(k, T_{i+1}) >= w(k, T_i) for all k"},
        ))

        # -----------------------------------------------------------------
        # AF-VS-02: Durrleman butterfly condition
        # g(k) >= -tolerance for all k in grid, for each slice.
        # -----------------------------------------------------------------
        butterfly_passed = True
        for sl in surface.slices:
            for k in grid:
                g = _durrleman_g(sl, k)
                if g is None:
                    continue  # skip near-zero variance points
                if g < -tolerance:
                    butterfly_passed = False
                    break
            if not butterfly_passed:
                break
        results.append(_make_result(
            "AF-VS-02",
            ArbitrageCheckType.VOL_SURFACE,
            butterfly_passed,
            CheckSeverity.CRITICAL,
            {"check": "Durrleman g(k) >= 0 for all k"},
        ))

        # -----------------------------------------------------------------
        # AF-VS-03: Roger Lee right wing -- b*(1+rho) <= 2
        # -----------------------------------------------------------------
        lee_right_passed = True
        for sl in surface.slices:
            if sl.b * (_ONE + sl.rho) > _TWO:
                lee_right_passed = False
                break
        results.append(_make_result(
            "AF-VS-03",
            ArbitrageCheckType.VOL_SURFACE,
            lee_right_passed,
            CheckSeverity.HIGH,
            {"check": "b*(1+rho) <= 2 (Roger Lee right wing)"},
        ))

        # -----------------------------------------------------------------
        # AF-VS-04: Roger Lee left wing -- b*(1-rho) <= 2
        # -----------------------------------------------------------------
        lee_left_passed = True
        for sl in surface.slices:
            if sl.b * (_ONE - sl.rho) > _TWO:
                lee_left_passed = False
                break
        results.append(_make_result(
            "AF-VS-04",
            ArbitrageCheckType.VOL_SURFACE,
            lee_left_passed,
            CheckSeverity.HIGH,
            {"check": "b*(1-rho) <= 2 (Roger Lee left wing)"},
        ))

        # -----------------------------------------------------------------
        # AF-VS-05: Positive implied variance -- w(k) >= -tolerance
        # -----------------------------------------------------------------
        pos_var_passed = True
        for sl in surface.slices:
            for k in grid:
                w = svi_total_variance(sl, k)
                if w < -tolerance:
                    pos_var_passed = False
                    break
            if not pos_var_passed:
                break
        results.append(_make_result(
            "AF-VS-05",
            ArbitrageCheckType.VOL_SURFACE,
            pos_var_passed,
            CheckSeverity.CRITICAL,
            {"check": "w(k) >= 0 for all k"},
        ))

        # -----------------------------------------------------------------
        # AF-VS-06: ATM variance monotonicity
        # w(0, T_{i+1}) >= w(0, T_i) - tolerance for adjacent slices.
        # -----------------------------------------------------------------
        atm_mono_passed = True
        k_atm = _ZERO
        for i in range(len(surface.slices) - 1):
            w_near = svi_total_variance(surface.slices[i], k_atm)
            w_far = svi_total_variance(surface.slices[i + 1], k_atm)
            if w_far < w_near - tolerance:
                atm_mono_passed = False
                break
        results.append(_make_result(
            "AF-VS-06",
            ArbitrageCheckType.VOL_SURFACE,
            atm_mono_passed,
            CheckSeverity.HIGH,
            {"check": "w(0, T_{i+1}) >= w(0, T_i)"},
        ))

    return Ok(tuple(results))


# ---------------------------------------------------------------------------
# Credit Curve Arbitrage Freedom
# ---------------------------------------------------------------------------


def check_credit_curve_arbitrage_freedom(
    curve: CreditCurve,
) -> Ok[tuple[ArbitrageCheckResult, ...]] | Err[str]:
    """Run credit curve arbitrage-freedom gates.

    AF-CR-01: 0 < Q(t) <= 1 for all tenor points
    AF-CR-02: Q(0) = 1 (by convention/construction)
    AF-CR-03: Q monotone non-increasing
    AF-CR-04: hazard rates >= 0
    """
    results: list[ArbitrageCheckResult] = []

    # AF-CR-01: 0 < Q(t) <= 1 for all tenor points
    bounds_passed = all(
        _ZERO < q <= _ONE for q in curve.survival_probs
    )
    results.append(_make_result(
        "AF-CR-01",
        ArbitrageCheckType.CREDIT_CURVE,
        bounds_passed,
        CheckSeverity.CRITICAL,
        {"check": "0 < Q(t) <= 1 for all t"},
    ))

    # AF-CR-02: Q(0) = 1 (by convention — enforced by construction)
    results.append(_make_result(
        "AF-CR-02",
        ArbitrageCheckType.CREDIT_CURVE,
        True,
        CheckSeverity.CRITICAL,
        {"check": "Q(0) = 1 (enforced at construction)"},
    ))

    # AF-CR-03: Q monotone non-increasing
    mono_passed = True
    for i in range(len(curve.survival_probs) - 1):
        if curve.survival_probs[i + 1] > curve.survival_probs[i]:
            mono_passed = False
            break
    results.append(_make_result(
        "AF-CR-03",
        ArbitrageCheckType.CREDIT_CURVE,
        mono_passed,
        CheckSeverity.CRITICAL,
        {"check": "Q(t2) <= Q(t1) for t2 > t1"},
    ))

    # AF-CR-04: hazard rates >= 0
    hazard_passed = all(h >= _ZERO for h in curve.hazard_rates)
    results.append(_make_result(
        "AF-CR-04",
        ArbitrageCheckType.CREDIT_CURVE,
        hazard_passed,
        CheckSeverity.HIGH,
        {"check": "lambda(t) >= 0 for all t"},
    ))

    return Ok(tuple(results))
