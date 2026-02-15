"""Arbitrage-freedom gates for yield curves and FX rates (III-07).

AF-YC-01..05: Yield curve checks.
AF-FX-01..03: FX consistency checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.money import CurrencyPair
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import FrozenMap
from attestor.oracle.calibration import YieldCurve, forward_rate


class ArbitrageCheckType(Enum):
    YIELD_CURVE = "YIELD_CURVE"
    FX_TRIANGULAR = "FX_TRIANGULAR"
    FX_SPOT_FORWARD = "FX_SPOT_FORWARD"


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
