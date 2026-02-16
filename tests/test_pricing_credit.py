"""Tests for CDS-specific pricing types and StubPricingEngine with credit instruments.

Step 12: Extends ValuationResult with premium_leg_pv and protection_leg_pv fields.
Verifies CDS pricing workflow and stub engine behavior with credit instrument IDs.
"""

from __future__ import annotations

import dataclasses
from decimal import Decimal

import pytest

from attestor.core.result import Ok
from attestor.core.types import UtcDatetime
from attestor.pricing.protocols import StubPricingEngine
from attestor.pricing.types import Greeks, ValuationResult

# ---------------------------------------------------------------------------
# ValuationResult CDS Extensions
# ---------------------------------------------------------------------------


class TestValuationResultCDSFields:
    def test_premium_leg_pv_default_zero(self) -> None:
        """premium_leg_pv defaults to Decimal('0')."""
        vr = ValuationResult(
            instrument_id="CDS-AAPL",
            npv=Decimal("1000"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
        )
        assert vr.premium_leg_pv == Decimal("0")

    def test_protection_leg_pv_default_zero(self) -> None:
        """protection_leg_pv defaults to Decimal('0')."""
        vr = ValuationResult(
            instrument_id="CDS-AAPL",
            npv=Decimal("1000"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
        )
        assert vr.protection_leg_pv == Decimal("0")

    def test_both_cds_fields_zero_by_default(self) -> None:
        """Both premium_leg_pv and protection_leg_pv are Decimal('0') by default."""
        vr = ValuationResult(
            instrument_id="CDS-IBM",
            npv=Decimal("500"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
        )
        assert vr.premium_leg_pv == Decimal("0")
        assert vr.protection_leg_pv == Decimal("0")

    def test_premium_leg_pv_non_zero(self) -> None:
        """premium_leg_pv can be set to non-zero value."""
        vr = ValuationResult(
            instrument_id="CDS-TSLA",
            npv=Decimal("750"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            premium_leg_pv=Decimal("250"),
        )
        assert vr.premium_leg_pv == Decimal("250")

    def test_protection_leg_pv_non_zero(self) -> None:
        """protection_leg_pv can be set to non-zero value."""
        vr = ValuationResult(
            instrument_id="CDS-GE",
            npv=Decimal("600"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            protection_leg_pv=Decimal("600"),
        )
        assert vr.protection_leg_pv == Decimal("600")

    def test_both_cds_fields_non_zero(self) -> None:
        """Both CDS fields can be set to non-zero values."""
        vr = ValuationResult(
            instrument_id="CDS-JPM",
            npv=Decimal("100"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            premium_leg_pv=Decimal("350"),
            protection_leg_pv=Decimal("-250"),
        )
        assert vr.premium_leg_pv == Decimal("350")
        assert vr.protection_leg_pv == Decimal("-250")

    def test_cds_fields_independent_of_npv(self) -> None:
        """CDS fields are informational; they don't affect npv calculation."""
        npv = Decimal("500")
        vr = ValuationResult(
            instrument_id="CDS-X",
            npv=npv,
            currency="USD",
            valuation_date=UtcDatetime.now(),
            premium_leg_pv=Decimal("300"),
            protection_leg_pv=Decimal("200"),
        )
        # npv remains independent of leg components
        assert vr.npv == npv


# ---------------------------------------------------------------------------
# ValuationResult Immutability with CDS Fields
# ---------------------------------------------------------------------------


class TestValuationResultCDSImmutability:
    def test_frozen_premium_leg_pv(self) -> None:
        """ValuationResult is frozen; premium_leg_pv cannot be modified."""
        vr = ValuationResult(
            instrument_id="CDS-F",
            npv=Decimal("200"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            premium_leg_pv=Decimal("100"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            vr.premium_leg_pv = Decimal("500")  # type: ignore[misc]

    def test_frozen_protection_leg_pv(self) -> None:
        """ValuationResult is frozen; protection_leg_pv cannot be modified."""
        vr = ValuationResult(
            instrument_id="CDS-G",
            npv=Decimal("300"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            protection_leg_pv=Decimal("100"),
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            vr.protection_leg_pv = Decimal("600")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# StubPricingEngine with CDS Instruments
# ---------------------------------------------------------------------------


class TestStubPricingEngineCDS:
    def test_cds_instrument_price(self) -> None:
        """StubPricingEngine.price() works with CDS-style instrument IDs."""
        engine = StubPricingEngine(oracle_price=Decimal("750"))
        result = engine.price("CDS-AAPL", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.instrument_id == "CDS-AAPL"
        assert result.value.npv == Decimal("750")

    def test_cds_instrument_price_any_id_pattern(self) -> None:
        """StubPricingEngine accepts any CDS identifier pattern."""
        engine = StubPricingEngine(oracle_price=Decimal("1000"))
        # Test various CDS ID patterns
        ids = [
            "CDS-IBM",
            "CDS-TSLA-5Y",
            "CDS-EUR/JPM/SENIOR",
            "CDS-123456",
        ]
        for cds_id in ids:
            result = engine.price(cds_id, "snap-1", "cfg-1")
            assert isinstance(result, Ok)
            assert result.value.instrument_id == cds_id

    def test_cds_greeks_all_zero(self) -> None:
        """StubPricingEngine.greeks() returns all zero Greeks for CDS."""
        engine = StubPricingEngine()
        result = engine.greeks("CDS-AAPL", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        g = result.value
        assert isinstance(g, Greeks)
        assert g.delta == Decimal("0")
        assert g.gamma == Decimal("0")
        assert g.vega == Decimal("0")
        assert g.theta == Decimal("0")
        assert g.rho == Decimal("0")

    def test_cds_master_square_deterministic(self) -> None:
        """StubPricingEngine.price() is deterministic for same oracle_price."""
        oracle = Decimal("850")
        engine = StubPricingEngine(oracle_price=oracle)
        cds_id = "CDS-JPM"

        # Price same instrument with different snapshots/configs
        r1 = engine.price(cds_id, "snap-1", "cfg-1")
        r2 = engine.price(cds_id, "snap-2", "cfg-2")
        r3 = engine.price(cds_id, "snap-100", "cfg-xyz")

        assert isinstance(r1, Ok) and isinstance(r2, Ok) and isinstance(r3, Ok)
        assert r1.value.npv == r2.value.npv == r3.value.npv == oracle

    def test_stub_pricing_cds_with_zero_oracle(self) -> None:
        """StubPricingEngine returns oracle_price=0 when not specified."""
        engine = StubPricingEngine()  # No oracle_price
        result = engine.price("CDS-X", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.npv == Decimal("0")

    def test_stub_pricing_cds_default_currency(self) -> None:
        """StubPricingEngine defaults to USD currency."""
        engine = StubPricingEngine(oracle_price=Decimal("500"))
        result = engine.price("CDS-EUR/BANK", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.currency == "USD"

    def test_stub_pricing_cds_custom_currency(self) -> None:
        """StubPricingEngine accepts custom currency."""
        engine = StubPricingEngine(oracle_price=Decimal("500"), currency="EUR")
        result = engine.price("CDS-EUR/BANK", "snap-1", "cfg-1")
        assert isinstance(result, Ok)
        assert result.value.currency == "EUR"


# ---------------------------------------------------------------------------
# CDS Pricing Workflow: Components as informational
# ---------------------------------------------------------------------------


class TestCDSPricingInformation:
    def test_cds_premium_and_protection_legs_informational(self) -> None:
        """Premium and protection legs are informational; npv is independent."""
        # In a real CDS pricing, npv might derive from legs,
        # but these fields exist to document the components.
        npv = Decimal("500")
        premium = Decimal("600")
        protection = Decimal("-100")

        vr = ValuationResult(
            instrument_id="CDS-ACME",
            npv=npv,
            currency="USD",
            valuation_date=UtcDatetime.now(),
            premium_leg_pv=premium,
            protection_leg_pv=protection,
        )

        # The fields are there, but npv doesn't automatically compute from them
        assert vr.npv == npv
        assert vr.premium_leg_pv == premium
        assert vr.protection_leg_pv == protection

    def test_cds_legs_with_fixed_floating_legs(self) -> None:
        """CDS fields coexist with fixed_leg_pv and floating_leg_pv (for hybrid instruments)."""
        vr = ValuationResult(
            instrument_id="CDS-HYBRID",
            npv=Decimal("1000"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            fixed_leg_pv=Decimal("400"),
            floating_leg_pv=Decimal("200"),
            premium_leg_pv=Decimal("300"),
            protection_leg_pv=Decimal("100"),
        )

        # All leg types can coexist
        assert vr.fixed_leg_pv == Decimal("400")
        assert vr.floating_leg_pv == Decimal("200")
        assert vr.premium_leg_pv == Decimal("300")
        assert vr.protection_leg_pv == Decimal("100")

    def test_cds_negative_premium_leg(self) -> None:
        """CDS premium_leg_pv can be negative (e.g., cash out-of-pocket)."""
        vr = ValuationResult(
            instrument_id="CDS-SELLER",
            npv=Decimal("250"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            premium_leg_pv=Decimal("-100"),  # Seller receives premium → negative liability
        )
        assert vr.premium_leg_pv == Decimal("-100")

    def test_cds_negative_protection_leg(self) -> None:
        """CDS protection_leg_pv can be negative (e.g., buyer pays for protection)."""
        vr = ValuationResult(
            instrument_id="CDS-BUYER",
            npv=Decimal("250"),
            currency="USD",
            valuation_date=UtcDatetime.now(),
            protection_leg_pv=Decimal("-200"),  # Buyer pays premium for protection
        )
        assert vr.protection_leg_pv == Decimal("-200")
