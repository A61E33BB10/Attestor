"""Tests for attestor.oracle.arbitrage_gates — AF-YC and AF-FX checks."""

from __future__ import annotations

from decimal import Decimal

from attestor.core.money import CurrencyPair, NonEmptyStr
from attestor.core.result import Ok, unwrap
from attestor.oracle.arbitrage_gates import (
    ArbitrageCheckType,
    CheckSeverity,
    check_fx_spot_forward_consistency,
    check_fx_triangular_arbitrage,
    check_yield_curve_arbitrage_freedom,
)
from attestor.oracle.calibration import YieldCurve


def _normal_curve() -> YieldCurve:
    return unwrap(YieldCurve.create(
        currency="USD",
        as_of=__import__("datetime").date(2025, 6, 15),
        tenors=(Decimal("0.25"), Decimal("0.5"), Decimal("1"), Decimal("2")),
        discount_factors=(Decimal("0.99"), Decimal("0.98"), Decimal("0.96"), Decimal("0.92")),
        model_config_ref="CFG-001",
    ))


def _inverted_curve() -> YieldCurve:
    """Non-monotone DFs: D(0.5) > D(0.25)."""
    return unwrap(YieldCurve.create(
        currency="USD",
        as_of=__import__("datetime").date(2025, 6, 15),
        tenors=(Decimal("0.25"), Decimal("0.5"), Decimal("1")),
        discount_factors=(Decimal("0.95"), Decimal("0.97"), Decimal("0.90")),
        model_config_ref="CFG-001",
    ))


# ---------------------------------------------------------------------------
# Yield Curve Arbitrage Freedom
# ---------------------------------------------------------------------------


class TestYieldCurveArbitrageFreedom:
    def test_normal_curve_all_pass(self) -> None:
        results = unwrap(check_yield_curve_arbitrage_freedom(_normal_curve()))
        assert len(results) == 5
        assert all(r.passed for r in results)

    def test_check_ids(self) -> None:
        results = unwrap(check_yield_curve_arbitrage_freedom(_normal_curve()))
        ids = [r.check_id for r in results]
        assert ids == ["AF-YC-01", "AF-YC-02", "AF-YC-03", "AF-YC-04", "AF-YC-05"]

    def test_all_yield_curve_type(self) -> None:
        results = unwrap(check_yield_curve_arbitrage_freedom(_normal_curve()))
        assert all(r.check_type == ArbitrageCheckType.YIELD_CURVE for r in results)

    def test_severities(self) -> None:
        results = unwrap(check_yield_curve_arbitrage_freedom(_normal_curve()))
        assert results[0].severity == CheckSeverity.CRITICAL  # AF-YC-01
        assert results[1].severity == CheckSeverity.CRITICAL  # AF-YC-02
        assert results[2].severity == CheckSeverity.CRITICAL  # AF-YC-03
        assert results[3].severity == CheckSeverity.HIGH      # AF-YC-04
        assert results[4].severity == CheckSeverity.MEDIUM    # AF-YC-05

    def test_non_monotone_fails_yc03(self) -> None:
        results = unwrap(check_yield_curve_arbitrage_freedom(_inverted_curve()))
        yc03 = results[2]
        assert yc03.check_id == "AF-YC-03"
        assert yc03.passed is False

    def test_yc01_always_true_for_valid_curve(self) -> None:
        """Valid curves always have D(t) > 0 (enforced at construction)."""
        results = unwrap(check_yield_curve_arbitrage_freedom(_normal_curve()))
        assert results[0].passed is True

    def test_details_present(self) -> None:
        results = unwrap(check_yield_curve_arbitrage_freedom(_normal_curve()))
        for r in results:
            assert len(r.details) > 0


# ---------------------------------------------------------------------------
# FX Triangular Arbitrage
# ---------------------------------------------------------------------------


def _make_pair(s: str) -> CurrencyPair:
    return unwrap(CurrencyPair.parse(s))


class TestFXTriangularArbitrage:
    def test_consistent_rates_pass(self) -> None:
        """EUR/JPY * JPY/USD * USD/EUR ≈ 1 (sorted triplet)."""
        # Algorithm sorts ccys → (EUR, JPY, USD) and looks for a/b, b/c, c/a
        ej = Decimal("170.8875")  # EUR/JPY
        ju = Decimal("1") / Decimal("157.50")  # JPY/USD
        ue = Decimal("1") / Decimal("1.0850")  # USD/EUR
        rates = (
            (_make_pair("EUR/JPY"), ej),
            (_make_pair("JPY/USD"), ju),
            (_make_pair("USD/EUR"), ue),
        )
        results = unwrap(check_fx_triangular_arbitrage(rates))
        assert len(results) == 1
        assert results[0].passed is True

    def test_inconsistent_rates_fail(self) -> None:
        rates = (
            (_make_pair("EUR/JPY"), Decimal("170.00")),
            (_make_pair("JPY/USD"), Decimal("0.0064")),
            (_make_pair("USD/EUR"), Decimal("5.0")),  # way off
        )
        results = unwrap(check_fx_triangular_arbitrage(rates))
        assert len(results) == 1
        assert results[0].passed is False

    def test_fewer_than_3_returns_empty(self) -> None:
        rates = (
            (_make_pair("EUR/USD"), Decimal("1.0850")),
            (_make_pair("USD/JPY"), Decimal("157.50")),
        )
        results = unwrap(check_fx_triangular_arbitrage(rates))
        assert len(results) == 0

    def test_check_type_fx(self) -> None:
        ej = Decimal("170.8875")
        ju = Decimal("1") / Decimal("157.50")
        ue = Decimal("1") / Decimal("1.0850")
        rates = (
            (_make_pair("EUR/JPY"), ej),
            (_make_pair("JPY/USD"), ju),
            (_make_pair("USD/EUR"), ue),
        )
        results = unwrap(check_fx_triangular_arbitrage(rates))
        assert results[0].check_type == ArbitrageCheckType.FX_TRIANGULAR


# ---------------------------------------------------------------------------
# FX Spot-Forward Consistency (CIP)
# ---------------------------------------------------------------------------


class TestFXSpotForwardConsistency:
    def test_consistent_cip(self) -> None:
        # F/S = D_dom / D_for => F = S * D_dom / D_for
        spot = Decimal("1.0850")
        dom_df = Decimal("0.98")
        for_df = Decimal("0.97")
        fwd = spot * dom_df / for_df
        result = unwrap(check_fx_spot_forward_consistency(
            spot, fwd, dom_df, for_df,
        ))
        assert result.passed is True

    def test_inconsistent_cip(self) -> None:
        result = unwrap(check_fx_spot_forward_consistency(
            spot_rate=Decimal("1.0850"),
            forward_rate_val=Decimal("2.0"),  # way off
            domestic_df=Decimal("0.98"),
            foreign_df=Decimal("0.97"),
        ))
        assert result.passed is False

    def test_zero_spot_err(self) -> None:
        from attestor.core.result import Err
        result = check_fx_spot_forward_consistency(
            Decimal("0"), Decimal("1.09"), Decimal("0.98"), Decimal("0.97"),
        )
        assert isinstance(result, Err)

    def test_zero_df_err(self) -> None:
        from attestor.core.result import Err
        result = check_fx_spot_forward_consistency(
            Decimal("1.08"), Decimal("1.09"), Decimal("0"), Decimal("0.97"),
        )
        assert isinstance(result, Err)

    def test_check_type(self) -> None:
        spot = Decimal("1.0850")
        dom_df = Decimal("0.98")
        for_df = Decimal("0.97")
        fwd = spot * dom_df / for_df
        result = unwrap(check_fx_spot_forward_consistency(
            spot, fwd, dom_df, for_df,
        ))
        assert result.check_type == ArbitrageCheckType.FX_SPOT_FORWARD
