"""Tests for pricing stub extension — FX and IRS instrument IDs."""

from __future__ import annotations

from decimal import Decimal

from attestor.core.result import Ok, unwrap
from attestor.pricing.protocols import StubPricingEngine
from attestor.pricing.types import ValuationResult


class TestStubPricingFX:
    def test_price_fx_instrument(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("1085000"))
        result = engine.price("EURUSD-SPOT", "MKT-001", "CFG-001")
        assert isinstance(result, Ok)
        val = unwrap(result)
        assert val.instrument_id == "EURUSD-SPOT"
        assert val.npv == Decimal("1085000")

    def test_greeks_fx_instrument(self) -> None:
        engine = StubPricingEngine()
        result = engine.greeks("EURUSD-FWD-3M", "MKT-001", "CFG-001")
        assert isinstance(result, Ok)

    def test_price_deterministic_fx(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("42"))
        r1 = unwrap(engine.price("EURUSD-SPOT", "MKT", "CFG"))
        r2 = unwrap(engine.price("EURUSD-SPOT", "MKT", "CFG"))
        assert r1.npv == r2.npv


class TestStubPricingIRS:
    def test_price_irs_instrument(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("25000"))
        result = engine.price("IRS-USD-5Y", "MKT-001", "CFG-001")
        assert isinstance(result, Ok)
        val = unwrap(result)
        assert val.instrument_id == "IRS-USD-5Y"
        assert val.npv == Decimal("25000")

    def test_greeks_irs_instrument(self) -> None:
        engine = StubPricingEngine()
        result = engine.greeks("IRS-EUR-10Y", "MKT-001", "CFG-001")
        assert isinstance(result, Ok)

    def test_price_deterministic_irs(self) -> None:
        engine = StubPricingEngine(oracle_price=Decimal("100"))
        r1 = unwrap(engine.price("IRS-USD-5Y", "MKT", "CFG"))
        r2 = unwrap(engine.price("IRS-USD-5Y", "MKT", "CFG"))
        assert r1.npv == r2.npv


class TestValuationResultLegs:
    def test_default_leg_pvs_zero(self) -> None:
        engine = StubPricingEngine()
        val = unwrap(engine.price("IRS-001", "MKT", "CFG"))
        assert val.fixed_leg_pv == Decimal("0")
        assert val.floating_leg_pv == Decimal("0")

    def test_explicit_leg_pvs(self) -> None:
        from attestor.core.types import UtcDatetime
        val = ValuationResult(
            instrument_id="IRS-001",
            npv=Decimal("5000"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            fixed_leg_pv=Decimal("1050000"),
            floating_leg_pv=Decimal("1045000"),
        )
        assert val.fixed_leg_pv == Decimal("1050000")
        assert val.floating_leg_pv == Decimal("1045000")
