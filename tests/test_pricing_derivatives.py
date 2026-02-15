"""Tests for StubPricingEngine with derivative instrument IDs.

Step 9: No source changes — StubPricingEngine already accepts any instrument_id.
These tests verify the stub works correctly for option and futures identifiers.
"""

from __future__ import annotations

from decimal import Decimal

from attestor.core.result import Ok
from attestor.pricing.protocols import StubPricingEngine
from attestor.pricing.types import Greeks


class TestStubPricingDerivatives:
    def test_option_instrument_price(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("5.50"))
        result = engine.price("AAPL251219C00150000", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("5.50")
        assert result.value.instrument_id == "AAPL251219C00150000"

    def test_futures_instrument_price(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("5200"))
        result = engine.price("ESZ5", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("5200")
        assert result.value.instrument_id == "ESZ5"

    def test_option_greeks_zero(self) -> None:
        engine = StubPricingEngine()
        result = engine.greeks("AAPL251219C00150000", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        g = result.value
        assert isinstance(g, Greeks)
        assert g.delta == Decimal("0")
        assert g.gamma == Decimal("0")
        assert g.vega == Decimal("0")

    def test_futures_greeks_zero(self) -> None:
        engine = StubPricingEngine()
        result = engine.greeks("ESZ5", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.delta == Decimal("0")

    def test_master_square_option(self) -> None:
        """Stub preserves Master Square: price(id) returns oracle_price."""
        oracle = Decimal("7.25")
        engine = StubPricingEngine(oracle_price=oracle)
        r1 = engine.price("OPT-A", "snap-1", "cfg-1")
        r2 = engine.price("OPT-A", "snap-2", "cfg-2")
        assert isinstance(r1, Ok) and isinstance(r2, Ok)
        assert r1.value.npv == r2.value.npv == oracle

    def test_master_square_futures(self) -> None:
        """Stub preserves Master Square: price(id) returns oracle_price."""
        oracle = Decimal("5200")
        engine = StubPricingEngine(oracle_price=oracle)
        r1 = engine.price("FUT-A", "snap-1", "cfg-1")
        r2 = engine.price("FUT-A", "snap-2", "cfg-2")
        assert isinstance(r1, Ok) and isinstance(r2, Ok)
        assert r1.value.npv == r2.value.npv == oracle
