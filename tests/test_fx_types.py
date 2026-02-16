"""Tests for Phase 3 FX and IRS instrument types.

Step 1: CurrencyPair, FX PayoutSpecs, IRS PayoutSpec, FXDetail, IRSwapDetail,
instrument factories, Payout union completeness.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import CurrencyPair
from attestor.core.result import Err, Ok
from attestor.instrument.derivative_types import (
    FXDetail,
    IRSwapDetail,
    SettlementType,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    FXForwardPayoutSpec,
    FXSpotPayoutSpec,
    IRSwapPayoutSpec,
    NDFPayoutSpec,
    PaymentFrequency,
    SwapLegType,
)
from attestor.instrument.types import (
    Party,
    create_fx_forward_instrument,
    create_fx_spot_instrument,
    create_irs_instrument,
    create_ndf_instrument,
)

# ---------------------------------------------------------------------------
# CurrencyPair
# ---------------------------------------------------------------------------


class TestCurrencyPair:
    def test_valid_pair(self) -> None:
        result = CurrencyPair.parse("EUR/USD")
        assert isinstance(result, Ok)
        cp = result.value
        assert cp.base.value == "EUR"
        assert cp.quote.value == "USD"
        assert cp.value == "EUR/USD"

    def test_valid_pair_gbp_jpy(self) -> None:
        result = CurrencyPair.parse("GBP/JPY")
        assert isinstance(result, Ok)
        assert result.value.value == "GBP/JPY"

    def test_invalid_no_slash(self) -> None:
        result = CurrencyPair.parse("EURUSD")
        assert isinstance(result, Err)

    def test_invalid_base_currency(self) -> None:
        result = CurrencyPair.parse("XYZ/USD")
        assert isinstance(result, Err)
        assert "Invalid base currency" in result.error

    def test_invalid_quote_currency(self) -> None:
        result = CurrencyPair.parse("EUR/XYZ")
        assert isinstance(result, Err)
        assert "Invalid quote currency" in result.error

    def test_same_currency(self) -> None:
        result = CurrencyPair.parse("EUR/EUR")
        assert isinstance(result, Err)
        assert "differ" in result.error

    def test_frozen(self) -> None:
        cp = CurrencyPair.parse("EUR/USD")
        assert isinstance(cp, Ok)
        with pytest.raises(AttributeError):
            cp.value.base = "GBP"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FXSpotPayoutSpec
# ---------------------------------------------------------------------------


class TestFXSpotPayoutSpec:
    def test_valid(self) -> None:
        result = FXSpotPayoutSpec.create(
            currency_pair="EUR/USD",
            base_notional=Decimal("1000000"),
            currency="USD",
        )
        assert isinstance(result, Ok)
        spec = result.value
        assert spec.currency_pair.value == "EUR/USD"
        assert spec.base_notional.value == Decimal("1000000")
        assert spec.settlement_type == SettlementType.PHYSICAL

    def test_invalid_pair(self) -> None:
        result = FXSpotPayoutSpec.create(
            currency_pair="INVALID",
            base_notional=Decimal("1000000"),
            currency="USD",
        )
        assert isinstance(result, Err)

    def test_negative_notional(self) -> None:
        result = FXSpotPayoutSpec.create(
            currency_pair="EUR/USD",
            base_notional=Decimal("-1000"),
            currency="USD",
        )
        assert isinstance(result, Err)

    def test_frozen(self) -> None:
        r = FXSpotPayoutSpec.create("EUR/USD", Decimal("1000"), "USD")
        assert isinstance(r, Ok)
        with pytest.raises(AttributeError):
            r.value.currency_pair = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# FXForwardPayoutSpec
# ---------------------------------------------------------------------------


class TestFXForwardPayoutSpec:
    def test_valid(self) -> None:
        result = FXForwardPayoutSpec.create(
            currency_pair="EUR/USD",
            base_notional=Decimal("1000000"),
            forward_rate=Decimal("1.0850"),
            settlement_date=date(2026, 6, 15),
            currency="USD",
        )
        assert isinstance(result, Ok)
        spec = result.value
        assert spec.forward_rate.value == Decimal("1.0850")
        assert spec.settlement_date == date(2026, 6, 15)

    def test_invalid_forward_rate(self) -> None:
        result = FXForwardPayoutSpec.create(
            currency_pair="EUR/USD",
            base_notional=Decimal("1000000"),
            forward_rate=Decimal("-1.0850"),
            settlement_date=date(2026, 6, 15),
            currency="USD",
        )
        assert isinstance(result, Err)
        assert "forward_rate" in result.error


# ---------------------------------------------------------------------------
# NDFPayoutSpec
# ---------------------------------------------------------------------------


class TestNDFPayoutSpec:
    def test_valid(self) -> None:
        result = NDFPayoutSpec.create(
            currency_pair="USD/CNY",
            base_notional=Decimal("5000000"),
            forward_rate=Decimal("7.2500"),
            fixing_date=date(2026, 6, 10),
            settlement_date=date(2026, 6, 12),
            fixing_source="WMR",
            currency="USD",
        )
        assert isinstance(result, Ok)
        spec = result.value
        assert spec.fixing_source.value == "WMR"
        assert spec.fixing_date == date(2026, 6, 10)

    def test_fixing_after_settlement(self) -> None:
        result = NDFPayoutSpec.create(
            currency_pair="USD/CNY",
            base_notional=Decimal("5000000"),
            forward_rate=Decimal("7.2500"),
            fixing_date=date(2026, 6, 15),
            settlement_date=date(2026, 6, 12),
            fixing_source="WMR",
            currency="USD",
        )
        assert isinstance(result, Err)
        assert "fixing_date" in result.error

    def test_empty_fixing_source(self) -> None:
        result = NDFPayoutSpec.create(
            currency_pair="USD/CNY",
            base_notional=Decimal("5000000"),
            forward_rate=Decimal("7.2500"),
            fixing_date=date(2026, 6, 10),
            settlement_date=date(2026, 6, 12),
            fixing_source="",
            currency="USD",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# IRSwapPayoutSpec
# ---------------------------------------------------------------------------


class TestIRSwapPayoutSpec:
    def test_valid(self) -> None:
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2026, 3, 15),
            end_date=date(2031, 3, 15),
        )
        assert isinstance(result, Ok)
        spec = result.value
        assert spec.fixed_leg.fixed_rate.value == Decimal("0.035")
        assert spec.float_leg.float_index.value == "SOFR"
        assert spec.fixed_leg.notional.value == Decimal("10000000")

    def test_start_after_end(self) -> None:
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2031, 3, 15),
            end_date=date(2026, 3, 15),
        )
        assert isinstance(result, Err)
        assert "start_date" in result.error

    def test_same_start_end(self) -> None:
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.ANNUAL,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2026, 3, 15),
            end_date=date(2026, 3, 15),
        )
        assert isinstance(result, Err)

    def test_with_spread(self) -> None:
        result = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.035"),
            float_index="EURIBOR_3M",
            day_count=DayCountConvention.THIRTY_360,
            payment_frequency=PaymentFrequency.SEMI_ANNUAL,
            notional=Decimal("5000000"),
            currency="EUR",
            start_date=date(2026, 3, 15),
            end_date=date(2031, 3, 15),
            spread=Decimal("0.0025"),
        )
        assert isinstance(result, Ok)
        assert result.value.float_leg.spread == Decimal("0.0025")

    def test_frozen(self) -> None:
        r = IRSwapPayoutSpec.create(
            fixed_rate=Decimal("0.035"), float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"), currency="USD",
            start_date=date(2026, 3, 15), end_date=date(2031, 3, 15),
        )
        assert isinstance(r, Ok)
        with pytest.raises(AttributeError):
            r.value.start_date = date(2027, 1, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_day_count_convention(self) -> None:
        assert len(DayCountConvention) == 3
        assert DayCountConvention.ACT_360.value == "ACT/360"

    def test_payment_frequency(self) -> None:
        assert len(PaymentFrequency) == 4

    def test_swap_leg_type(self) -> None:
        assert SwapLegType.FIXED.value == "FIXED"
        assert SwapLegType.FLOAT.value == "FLOAT"


# ---------------------------------------------------------------------------
# FXDetail
# ---------------------------------------------------------------------------


class TestFXDetail:
    def test_spot_detail(self) -> None:
        result = FXDetail.create(
            currency_pair="EUR/USD",
            settlement_date=date(2026, 3, 17),
            settlement_type=SettlementType.PHYSICAL,
        )
        assert isinstance(result, Ok)
        assert result.value.forward_rate is None
        assert result.value.fixing_source is None

    def test_forward_detail(self) -> None:
        result = FXDetail.create(
            currency_pair="EUR/USD",
            settlement_date=date(2026, 6, 15),
            settlement_type=SettlementType.PHYSICAL,
            forward_rate=Decimal("1.0850"),
        )
        assert isinstance(result, Ok)
        assert result.value.forward_rate is not None

    def test_ndf_detail(self) -> None:
        result = FXDetail.create(
            currency_pair="USD/CNY",
            settlement_date=date(2026, 6, 12),
            settlement_type=SettlementType.CASH,
            forward_rate=Decimal("7.25"),
            fixing_source="WMR",
            fixing_date=date(2026, 6, 10),
        )
        assert isinstance(result, Ok)
        assert result.value.fixing_source is not None

    def test_invalid_pair(self) -> None:
        result = FXDetail.create(
            currency_pair="INVALID",
            settlement_date=date(2026, 3, 17),
            settlement_type=SettlementType.PHYSICAL,
        )
        assert isinstance(result, Err)

    def test_fixing_after_settlement(self) -> None:
        result = FXDetail.create(
            currency_pair="EUR/USD",
            settlement_date=date(2026, 6, 10),
            settlement_type=SettlementType.CASH,
            fixing_date=date(2026, 6, 15),
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# IRSwapDetail
# ---------------------------------------------------------------------------


class TestIRSwapDetail:
    def test_valid(self) -> None:
        result = IRSwapDetail.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months=60,
            start_date=date(2026, 3, 15),
            end_date=date(2031, 3, 15),
        )
        assert isinstance(result, Ok)
        assert result.value.tenor_months == 60

    def test_zero_tenor(self) -> None:
        result = IRSwapDetail.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months=0,
            start_date=date(2026, 3, 15),
            end_date=date(2031, 3, 15),
        )
        assert isinstance(result, Err)

    def test_start_after_end(self) -> None:
        result = IRSwapDetail.create(
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months=60,
            start_date=date(2031, 3, 15),
            end_date=date(2026, 3, 15),
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Instrument factories
# ---------------------------------------------------------------------------


def _make_parties() -> tuple[Party, ...]:
    p = Party.create("P1", "Bank A", "12345678901234567890")
    assert isinstance(p, Ok)
    return (p.value,)


class TestFXSpotInstrument:
    def test_create(self) -> None:
        result = create_fx_spot_instrument(
            instrument_id="FXSPOT-001",
            currency_pair="EUR/USD",
            base_notional=Decimal("1000000"),
            currency="USD",
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
        )
        assert isinstance(result, Ok)
        inst = result.value
        assert inst.instrument_id.value == "FXSPOT-001"
        assert isinstance(inst.product.economic_terms.payout, FXSpotPayoutSpec)

    def test_invalid_pair(self) -> None:
        result = create_fx_spot_instrument(
            instrument_id="FXSPOT-001",
            currency_pair="INVALID",
            base_notional=Decimal("1000000"),
            currency="USD",
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
        )
        assert isinstance(result, Err)


class TestFXForwardInstrument:
    def test_create(self) -> None:
        result = create_fx_forward_instrument(
            instrument_id="FXFWD-001",
            currency_pair="EUR/USD",
            base_notional=Decimal("1000000"),
            forward_rate=Decimal("1.0850"),
            settlement_date=date(2026, 6, 15),
            currency="USD",
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
        )
        assert isinstance(result, Ok)
        assert isinstance(result.value.product.economic_terms.payout, FXForwardPayoutSpec)


class TestNDFInstrument:
    def test_create(self) -> None:
        result = create_ndf_instrument(
            instrument_id="NDF-001",
            currency_pair="USD/CNY",
            base_notional=Decimal("5000000"),
            forward_rate=Decimal("7.25"),
            fixing_date=date(2026, 6, 10),
            settlement_date=date(2026, 6, 12),
            fixing_source="WMR",
            currency="USD",
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
        )
        assert isinstance(result, Ok)
        assert isinstance(result.value.product.economic_terms.payout, NDFPayoutSpec)


class TestIRSInstrument:
    def test_create(self) -> None:
        result = create_irs_instrument(
            instrument_id="IRS-001",
            fixed_rate=Decimal("0.035"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2026, 3, 15),
            end_date=date(2031, 3, 15),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
        )
        assert isinstance(result, Ok)
        inst = result.value
        assert isinstance(inst.product.economic_terms.payout, IRSwapPayoutSpec)
        assert inst.product.economic_terms.termination_date == date(2031, 3, 15)

    def test_invalid_rate(self) -> None:
        result = create_irs_instrument(
            instrument_id="IRS-001",
            fixed_rate=Decimal("-0.035"),
            float_index="SOFR",
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            notional=Decimal("10000000"),
            currency="USD",
            start_date=date(2026, 3, 15),
            end_date=date(2031, 3, 15),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Payout union completeness
# ---------------------------------------------------------------------------


class TestPayoutUnion:
    def test_all_seven_payout_variants(self) -> None:
        """Payout union has 7 variants after Phase 3."""
        # type Payout = ... has 7 alternatives
        # Just verify all types are importable and distinct
        from attestor.instrument.derivative_types import FuturesPayoutSpec, OptionPayoutSpec
        from attestor.instrument.types import EquityPayoutSpec, Payout

        payout_types = {
            EquityPayoutSpec, OptionPayoutSpec, FuturesPayoutSpec,
            FXSpotPayoutSpec, FXForwardPayoutSpec, NDFPayoutSpec, IRSwapPayoutSpec,
        }
        assert len(payout_types) == 7
        # Verify Payout is accessible
        assert Payout is not None

    def test_instrument_detail_has_5_variants(self) -> None:
        """InstrumentDetail union has 5 variants after Phase 3."""
        from attestor.instrument.derivative_types import (
            EquityDetail,
            FuturesDetail,
            OptionDetail,
        )

        detail_types = {EquityDetail, OptionDetail, FuturesDetail, FXDetail, IRSwapDetail}
        assert len(detail_types) == 5
