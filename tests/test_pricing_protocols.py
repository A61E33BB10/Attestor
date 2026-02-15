"""Tests for attestor.pricing.protocols — pricing & risk engine protocols."""

from __future__ import annotations

from decimal import Decimal

from attestor.core.result import Ok
from attestor.pricing.protocols import (
    PricingEngine,
    RiskEngine,
    StubPricingEngine,
)
from attestor.pricing.types import (
    Greeks,
    PnLAttribution,
    ScenarioResult,
    ValuationResult,
    VaRResult,
)

# ---------------------------------------------------------------------------
# StubPricingEngine — satisfies PricingEngine protocol
# ---------------------------------------------------------------------------


class TestStubPricingEngine:
    def test_price_returns_ok(self) -> None:
        engine = StubPricingEngine()
        result = engine.price("AAPL", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        vr = result.value
        assert isinstance(vr, ValuationResult)
        assert vr.instrument_id == "AAPL"
        assert vr.npv == Decimal("0")
        assert vr.currency == "USD"

    def test_greeks_returns_ok(self) -> None:
        engine = StubPricingEngine()
        result = engine.greeks("AAPL", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        g = result.value
        assert isinstance(g, Greeks)
        assert g.delta == Decimal("0")

    def test_var_returns_ok(self) -> None:
        engine = StubPricingEngine()
        result = engine.var(
            ("AAPL", "MSFT"), "snap-1",
            confidence_level=Decimal("0.99"), horizon_days=10, method="HS",
        )
        assert isinstance(result, Ok)
        vr = result.value
        assert isinstance(vr, VaRResult)
        assert vr.confidence_level == Decimal("0.99")
        assert vr.horizon_days == 10
        assert vr.var_amount == Decimal("0")
        assert vr.es_amount == Decimal("0")
        assert vr.method == "HS"

    def test_pnl_attribution_returns_ok(self) -> None:
        engine = StubPricingEngine()
        result = engine.pnl_attribution(("AAPL",), "snap-1", "snap-2")
        assert isinstance(result, Ok)
        pnl = result.value
        assert isinstance(pnl, PnLAttribution)
        assert pnl.total_pnl == Decimal("0")

    def test_price_with_oracle_price(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("175.50"))
        result = engine.price("AAPL", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("175.50")

    def test_price_with_oracle_price_and_currency(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("150"), currency="EUR")
        result = engine.price("SAP", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("150")
        assert result.value.currency == "EUR"

    def test_price_default_zero_without_oracle(self) -> None:
        engine = StubPricingEngine()
        result = engine.price("AAPL", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("0")

    def test_stub_satisfies_pricing_engine_protocol(self) -> None:
        """StubPricingEngine is structurally compatible with PricingEngine."""
        engine: PricingEngine = StubPricingEngine()
        result = engine.price("X", "S", "C")
        assert isinstance(result, Ok)


# ---------------------------------------------------------------------------
# Protocol structural typing
# ---------------------------------------------------------------------------


class TestProtocolStructuralTyping:
    def test_custom_engine_satisfies_protocol(self) -> None:
        """Any class with matching signatures satisfies PricingEngine."""

        class _CustomEngine:
            def price(
                self, instrument_id: str, market_snapshot_id: str,
                model_config_id: str,
            ) -> Ok[ValuationResult]:
                from attestor.core.types import UtcDatetime
                return Ok(ValuationResult(
                    instrument_id=instrument_id, npv=Decimal("42"),
                    currency="EUR", valuation_date=UtcDatetime.now(),
                ))

            def greeks(
                self, instrument_id: str, market_snapshot_id: str,
                model_config_id: str,
            ) -> Ok[Greeks]:
                return Ok(Greeks())

            def var(
                self, portfolio: tuple[str, ...], market_snapshot_id: str,
                confidence_level: Decimal, horizon_days: int, method: str,
            ) -> Ok[VaRResult]:
                return Ok(VaRResult(
                    confidence_level=confidence_level, horizon_days=horizon_days,
                    var_amount=Decimal("0"), es_amount=Decimal("0"),
                    currency="USD", method=method,
                ))

            def pnl_attribution(
                self, portfolio: tuple[str, ...],
                start_snapshot_id: str, end_snapshot_id: str,
            ) -> Ok[PnLAttribution]:
                return Ok(PnLAttribution.create(
                    Decimal("0"), Decimal("0"), Decimal("0"), Decimal("0"), "USD",
                ))

        engine: PricingEngine = _CustomEngine()
        result = engine.price("TEST", "S", "C")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("42")

    def test_custom_risk_engine_satisfies_protocol(self) -> None:
        """Any class with matching scenario_pnl satisfies RiskEngine."""

        class _CustomRiskEngine:
            def scenario_pnl(
                self, portfolio: tuple[str, ...],
                scenarios: tuple[object, ...],
                market_snapshot_id: str,
            ) -> Ok[tuple[ScenarioResult, ...]]:
                return Ok(())

        engine: RiskEngine = _CustomRiskEngine()
        result = engine.scenario_pnl(("A",), (), "snap-1")
        assert isinstance(result, Ok)
        assert result.value == ()
