"""Tests for attestor.pricing.types — pricing interface types."""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from attestor.core.result import unwrap
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.pricing.types import (
    Greeks,
    PnLAttribution,
    Scenario,
    ScenarioResult,
    ValuationResult,
    VaRResult,
)

# ---------------------------------------------------------------------------
# ValuationResult (GAP-36)
# ---------------------------------------------------------------------------


class TestValuationResult:
    def test_construction(self) -> None:
        vr = ValuationResult(
            instrument_id="AAPL-CALL",
            npv=Decimal("1500.50"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
        )
        assert vr.npv == Decimal("1500.50")

    def test_has_valuation_date(self) -> None:
        vd = UtcDatetime.now()
        vr = ValuationResult(
            instrument_id="X", npv=Decimal("0"), currency="USD",
            valuation_date=vd,
        )
        assert vr.valuation_date == vd

    def test_components_default_empty(self) -> None:
        vr = ValuationResult(
            instrument_id="X", npv=Decimal("0"), currency="USD",
            valuation_date=UtcDatetime.now(),
        )
        assert len(vr.components) == 0

    def test_frozen(self) -> None:
        vr = ValuationResult(
            instrument_id="X", npv=Decimal("0"), currency="USD",
            valuation_date=UtcDatetime.now(),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            vr.npv = Decimal("1")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Greeks (GAP-35)
# ---------------------------------------------------------------------------


class TestGreeks:
    def test_defaults_are_zero(self) -> None:
        g = Greeks()
        assert g.delta == Decimal("0")
        assert g.gamma == Decimal("0")
        assert g.vega == Decimal("0")

    def test_additional_default_empty(self) -> None:
        g = Greeks()
        assert len(g.additional) == 0

    def test_additional_custom(self) -> None:
        add = unwrap(FrozenMap.create({"speed": Decimal("0.01")}))
        g = Greeks(additional=add)
        assert g.additional["speed"] == Decimal("0.01")

    def test_frozen(self) -> None:
        g = Greeks()
        with pytest.raises(dataclasses.FrozenInstanceError):
            g.delta = Decimal("1")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Scenario + ScenarioResult
# ---------------------------------------------------------------------------


class TestScenario:
    def test_create(self) -> None:
        s = Scenario.create("rates_up_100bp", {"USD_RATE": Decimal("0.01")}, "snap-1")
        assert s.label == "rates_up_100bp"
        assert s.overrides["USD_RATE"] == Decimal("0.01")

    def test_frozen(self) -> None:
        s = Scenario.create("x", {}, "snap-1")
        with pytest.raises(dataclasses.FrozenInstanceError):
            s.label = "y"  # type: ignore[misc]


class TestScenarioResult:
    def test_construction(self) -> None:
        impacts = unwrap(FrozenMap.create({"AAPL": Decimal("-50")}))
        sr = ScenarioResult(
            scenario_label="up", base_npv=Decimal("1000"),
            stressed_npv=Decimal("950"), pnl_impact=Decimal("-50"),
            instrument_impacts=impacts,
        )
        assert sr.pnl_impact == Decimal("-50")


# ---------------------------------------------------------------------------
# VaRResult (GAP-34)
# ---------------------------------------------------------------------------


class TestVaRResult:
    def test_has_es_amount(self) -> None:
        vr = VaRResult(
            confidence_level=Decimal("0.99"), horizon_days=10,
            var_amount=Decimal("1000000"), es_amount=Decimal("1200000"),
            currency="USD", method="HistoricalSimulation",
        )
        assert vr.es_amount == Decimal("1200000")

    def test_component_var_default_empty(self) -> None:
        vr = VaRResult(
            confidence_level=Decimal("0.99"), horizon_days=1,
            var_amount=Decimal("100"), es_amount=Decimal("120"),
            currency="USD", method="M",
        )
        assert len(vr.component_var) == 0

    def test_frozen(self) -> None:
        vr = VaRResult(
            confidence_level=Decimal("0.99"), horizon_days=1,
            var_amount=Decimal("100"), es_amount=Decimal("120"),
            currency="USD", method="M",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            vr.var_amount = Decimal("0")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# PnLAttribution (GAP-37)
# ---------------------------------------------------------------------------


class TestPnLAttribution:
    def test_create_computes_total(self) -> None:
        pnl = PnLAttribution.create(
            market_pnl=Decimal("100"), carry_pnl=Decimal("20"),
            trade_pnl=Decimal("50"), residual_pnl=Decimal("-5"),
            currency="USD",
        )
        assert pnl.total_pnl == Decimal("165")

    def test_create_zero_components(self) -> None:
        pnl = PnLAttribution.create(
            Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "USD",
        )
        assert pnl.total_pnl == Decimal("0")

    def test_frozen(self) -> None:
        pnl = PnLAttribution.create(
            Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4"), "USD",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            pnl.total_pnl = Decimal("0")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Property-based
# ---------------------------------------------------------------------------


_pnl_amounts = st.decimals(
    min_value=Decimal("-1e9"), max_value=Decimal("1e9"),
    allow_nan=False, allow_infinity=False, places=2,
)


class TestPnLProperties:
    @given(m=_pnl_amounts, c=_pnl_amounts, t=_pnl_amounts, r=_pnl_amounts)
    def test_decomposition_invariant(
        self, m: Decimal, c: Decimal, t: Decimal, r: Decimal,
    ) -> None:
        """total == market + carry + trade + residual, always."""
        pnl = PnLAttribution.create(m, c, t, r, "USD")
        assert pnl.total_pnl == m + c + t + r

    @given(
        bid=st.decimals(min_value=Decimal("0"), max_value=Decimal("1000"),
                        allow_nan=False, allow_infinity=False, places=2),
    )
    def test_greeks_default_values_are_zero(self, bid: Decimal) -> None:
        """All default greek values are zero regardless of parameterization."""
        g = Greeks(delta=bid)
        assert g.gamma == Decimal("0")
        assert g.vega == Decimal("0")
