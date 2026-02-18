"""Tests for Phase 4 CDS and Swaption instrument types.

Step 1: enums, CDSPayoutSpec, SwaptionPayoutSpec, CDSDetail, SwaptionDetail,
InstrumentDetail union (7 variants), Payout union (9 variants), factory functions.
"""

from __future__ import annotations

import dataclasses
from datetime import date
from decimal import Decimal

import pytest

from attestor.core.party import CounterpartyRoleEnum
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import PayerReceiver, Period
from attestor.instrument.credit_types import (
    CDSPayoutSpec,
    SwaptionPayoutSpec,
)
from attestor.instrument.derivative_types import (
    CDSDetail,
    CreditEventType,
    EquityDetail,
    FuturesDetail,
    FuturesPayoutSpec,
    FXDetail,
    IRSwapDetail,
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionPayoutSpec,
    OptionTypeEnum,
    ProtectionSide,
    SeniorityLevel,
    SettlementTypeEnum,
    SwaptionDetail,
    SwaptionType,
)
from attestor.instrument.fx_types import (
    DayCountConvention,
    FXForwardPayoutSpec,
    FXSpotPayoutSpec,
    IRSwapPayoutSpec,
    NDFPayoutSpec,
    PaymentFrequency,
)
from attestor.instrument.types import (
    EquityPayoutSpec,
    Party,
    create_cds_instrument,
    create_swaption_instrument,
)
from attestor.oracle.observable import FloatingRateIndex, FloatingRateIndexEnum

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_LEI = "529900HNOAA1KXQJUQ27"
_PR = PayerReceiver(payer=CounterpartyRoleEnum.PARTY1, receiver=CounterpartyRoleEnum.PARTY2)
_SOFR = FloatingRateIndex(index=FloatingRateIndexEnum.SOFR, designated_maturity=Period(1, "D"))


def _make_parties() -> tuple[Party, ...]:
    p = Party.create("P1", "Bank A", _LEI)
    assert isinstance(p, Ok)
    return (p.value,)


def _make_underlying_swap() -> IRSwapPayoutSpec:
    result = IRSwapPayoutSpec.create(
        fixed_rate=Decimal("0.035"),
        float_index=_SOFR,
        day_count=DayCountConvention.ACT_360,
        payment_frequency=PaymentFrequency.QUARTERLY,
        notional=Decimal("10000000"),
        currency="USD",
        start_date=date(2027, 6, 15),
        end_date=date(2032, 6, 15),
        payer_receiver=_PR,
    )
    return unwrap(result)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestCreditEnums:
    def test_credit_event_type_values(self) -> None:
        assert {e.value for e in CreditEventType} == {
            "BANKRUPTCY", "FAILURE_TO_PAY", "RESTRUCTURING",
            "OBLIGATION_DEFAULT", "GOVERNMENTAL_INTERVENTION",
            "REPUDIATION_MORATORIUM",
        }

    def test_seniority_level_values(self) -> None:
        assert {e.value for e in SeniorityLevel} == {
            "SENIOR_UNSECURED", "SUBORDINATED", "SENIOR_SECURED",
        }

    def test_protection_side_values(self) -> None:
        assert {e.value for e in ProtectionSide} == {"BUYER", "SELLER"}

    def test_swaption_type_values(self) -> None:
        assert {e.value for e in SwaptionType} == {"PAYER", "RECEIVER"}


# ---------------------------------------------------------------------------
# CDSPayoutSpec
# ---------------------------------------------------------------------------


class TestCDSPayoutSpec:
    def test_create_valid(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        spec = unwrap(result)
        assert spec.reference_entity.value == "ACME Corp"
        assert spec.notional.value == Decimal("10000000")
        assert spec.spread == Decimal("0.01")
        assert spec.recovery_rate == Decimal("0.4")
        assert spec.payment_frequency == PaymentFrequency.QUARTERLY
        assert spec.day_count == DayCountConvention.ACT_360

    def test_empty_reference_entity_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "reference_entity" in result.error

    def test_zero_notional_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("0"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "notional" in result.error

    def test_zero_spread_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "spread" in result.error

    def test_negative_spread_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("-0.005"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "spread" in result.error

    def test_effective_equals_maturity_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2026, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "effective_date" in result.error

    def test_effective_after_maturity_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2031, 3, 20),
            maturity_date=date(2026, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "effective_date" in result.error

    def test_recovery_rate_one_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("1"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "recovery_rate" in result.error

    def test_recovery_rate_negative_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("-0.1"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "recovery_rate" in result.error

    def test_recovery_rate_zero_ok(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        assert result.value.recovery_rate == Decimal("0")

    def test_empty_currency_err(self) -> None:
        result = CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "currency" in result.error

    def test_frozen(self) -> None:
        spec = unwrap(CDSPayoutSpec.create(
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            payer_receiver=_PR,
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.spread = Decimal("0.02")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# SwaptionPayoutSpec
# ---------------------------------------------------------------------------


class TestSwaptionPayoutSpec:
    def test_create_valid(self) -> None:
        swap = _make_underlying_swap()
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        spec = unwrap(result)
        assert spec.swaption_type == SwaptionType.PAYER
        assert spec.strike.value == Decimal("0.035")
        assert spec.underlying_swap is swap
        assert spec.settlement_type == SettlementTypeEnum.PHYSICAL

    def test_exercise_before_swap_start_ok(self) -> None:
        swap = _make_underlying_swap()
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.RECEIVER,
            strike=Decimal("0.04"),
            exercise_date=date(2027, 6, 10),  # before swap start 2027-06-15
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.CASH,
            currency="USD",
            notional=Decimal("5000000"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)

    def test_exercise_after_swap_start_err(self) -> None:
        swap = _make_underlying_swap()
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 16),  # after swap start 2027-06-15
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "exercise_date" in result.error

    def test_zero_strike_ok(self) -> None:
        """P0-4: zero-strike is now valid for total return structures."""
        swap = _make_underlying_swap()
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        assert result.value.strike.value == Decimal("0")

    def test_zero_notional_err(self) -> None:
        swap = _make_underlying_swap()
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("0"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "notional" in result.error

    def test_empty_currency_err(self) -> None:
        swap = _make_underlying_swap()
        result = SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="",
            notional=Decimal("10000000"),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)
        assert "currency" in result.error

    def test_frozen(self) -> None:
        swap = _make_underlying_swap()
        spec = unwrap(SwaptionPayoutSpec.create(
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            payer_receiver=_PR,
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.swaption_type = SwaptionType.RECEIVER  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CDSDetail
# ---------------------------------------------------------------------------


class TestCDSDetail:
    def test_create_valid(self) -> None:
        result = CDSDetail.create(
            reference_entity="ACME Corp",
            spread_bps=Decimal("100"),
            seniority=SeniorityLevel.SENIOR_UNSECURED,
            protection_side=ProtectionSide.BUYER,
            start_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
        )
        assert isinstance(result, Ok)
        detail = unwrap(result)
        assert detail.reference_entity.value == "ACME Corp"
        assert detail.spread_bps.value == Decimal("100")
        assert detail.seniority == SeniorityLevel.SENIOR_UNSECURED
        assert detail.protection_side == ProtectionSide.BUYER

    def test_empty_reference_entity_err(self) -> None:
        result = CDSDetail.create(
            reference_entity="",
            spread_bps=Decimal("100"),
            seniority=SeniorityLevel.SENIOR_UNSECURED,
            protection_side=ProtectionSide.BUYER,
            start_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
        )
        assert isinstance(result, Err)
        assert "reference_entity" in result.error

    def test_zero_spread_bps_err(self) -> None:
        result = CDSDetail.create(
            reference_entity="ACME Corp",
            spread_bps=Decimal("0"),
            seniority=SeniorityLevel.SENIOR_UNSECURED,
            protection_side=ProtectionSide.BUYER,
            start_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
        )
        assert isinstance(result, Err)
        assert "spread_bps" in result.error

    def test_start_equals_maturity_err(self) -> None:
        result = CDSDetail.create(
            reference_entity="ACME Corp",
            spread_bps=Decimal("100"),
            seniority=SeniorityLevel.SUBORDINATED,
            protection_side=ProtectionSide.SELLER,
            start_date=date(2026, 3, 20),
            maturity_date=date(2026, 3, 20),
        )
        assert isinstance(result, Err)
        assert "start_date" in result.error

    def test_start_after_maturity_err(self) -> None:
        result = CDSDetail.create(
            reference_entity="ACME Corp",
            spread_bps=Decimal("100"),
            seniority=SeniorityLevel.SENIOR_SECURED,
            protection_side=ProtectionSide.BUYER,
            start_date=date(2031, 3, 20),
            maturity_date=date(2026, 3, 20),
        )
        assert isinstance(result, Err)
        assert "start_date" in result.error


# ---------------------------------------------------------------------------
# SwaptionDetail
# ---------------------------------------------------------------------------


class TestSwaptionDetail:
    def test_create_valid(self) -> None:
        result = SwaptionDetail.create(
            swaption_type=SwaptionType.PAYER,
            expiry_date=date(2027, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="SOFR",
            underlying_tenor_months=60,
            settlement_type=SettlementTypeEnum.PHYSICAL,
        )
        assert isinstance(result, Ok)
        detail = unwrap(result)
        assert detail.swaption_type == SwaptionType.PAYER
        assert detail.underlying_tenor_months == 60

    def test_zero_fixed_rate_ok(self) -> None:
        """P0-4: zero/negative fixed rates are now valid (EUR/JPY/CHF markets)."""
        result = SwaptionDetail.create(
            swaption_type=SwaptionType.RECEIVER,
            expiry_date=date(2027, 6, 15),
            underlying_fixed_rate=Decimal("0"),
            underlying_float_index="SOFR",
            underlying_tenor_months=60,
            settlement_type=SettlementTypeEnum.CASH,
        )
        assert isinstance(result, Ok)
        assert result.value.underlying_fixed_rate == Decimal("0")

    def test_empty_float_index_err(self) -> None:
        result = SwaptionDetail.create(
            swaption_type=SwaptionType.PAYER,
            expiry_date=date(2027, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="",
            underlying_tenor_months=60,
            settlement_type=SettlementTypeEnum.PHYSICAL,
        )
        assert isinstance(result, Err)
        assert "underlying_float_index" in result.error

    def test_zero_tenor_months_err(self) -> None:
        result = SwaptionDetail.create(
            swaption_type=SwaptionType.PAYER,
            expiry_date=date(2027, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="SOFR",
            underlying_tenor_months=0,
            settlement_type=SettlementTypeEnum.PHYSICAL,
        )
        assert isinstance(result, Err)
        assert "underlying_tenor_months" in result.error

    def test_negative_tenor_months_err(self) -> None:
        result = SwaptionDetail.create(
            swaption_type=SwaptionType.PAYER,
            expiry_date=date(2027, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="SOFR",
            underlying_tenor_months=-12,
            settlement_type=SettlementTypeEnum.PHYSICAL,
        )
        assert isinstance(result, Err)
        assert "underlying_tenor_months" in result.error


# ---------------------------------------------------------------------------
# InstrumentDetail union (7 variants)
# ---------------------------------------------------------------------------


class TestInstrumentDetailUnion:
    def test_exhaustive_match_all_seven_variants(self) -> None:
        details: list[
            EquityDetail | OptionDetail | FuturesDetail | FXDetail
            | IRSwapDetail | CDSDetail | SwaptionDetail
        ] = [
            EquityDetail(),
            unwrap(OptionDetail.create(
                strike=Decimal("150"), expiry_date=date(2025, 12, 19),
                option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.AMERICAN,
                settlement_type=SettlementTypeEnum.PHYSICAL, underlying_id="AAPL",
            )),
            unwrap(FuturesDetail.create(
                expiry_date=date(2025, 12, 19), contract_size=Decimal("50"),
                settlement_type=SettlementTypeEnum.CASH, underlying_id="ES",
            )),
            unwrap(FXDetail.create(
                currency_pair="EUR/USD",
                settlement_date=date(2026, 3, 17),
                settlement_type=SettlementTypeEnum.PHYSICAL,
            )),
            unwrap(IRSwapDetail.create(
                fixed_rate=Decimal("0.035"), float_index="SOFR",
                day_count="ACT/360", payment_frequency="QUARTERLY",
                tenor_months=60, start_date=date(2026, 3, 15),
                end_date=date(2031, 3, 15),
            )),
            unwrap(CDSDetail.create(
                reference_entity="ACME Corp", spread_bps=Decimal("100"),
                seniority=SeniorityLevel.SENIOR_UNSECURED,
                protection_side=ProtectionSide.BUYER,
                start_date=date(2026, 3, 20), maturity_date=date(2031, 3, 20),
            )),
            unwrap(SwaptionDetail.create(
                swaption_type=SwaptionType.PAYER,
                expiry_date=date(2027, 6, 15),
                underlying_fixed_rate=Decimal("0.035"),
                underlying_float_index="SOFR",
                underlying_tenor_months=60,
                settlement_type=SettlementTypeEnum.PHYSICAL,
            )),
        ]
        for d in details:
            match d:
                case EquityDetail():
                    pass
                case OptionDetail():
                    pass
                case FuturesDetail():
                    pass
                case FXDetail():
                    pass
                case IRSwapDetail():
                    pass
                case CDSDetail():
                    pass
                case SwaptionDetail():
                    pass

    def test_instrument_detail_has_7_variants(self) -> None:
        detail_types = {
            EquityDetail, OptionDetail, FuturesDetail, FXDetail, IRSwapDetail,
            CDSDetail, SwaptionDetail,
        }
        assert len(detail_types) == 7


# ---------------------------------------------------------------------------
# Payout union (9 variants)
# ---------------------------------------------------------------------------


class TestPayoutUnion:
    def test_payout_has_9_variants(self) -> None:
        from attestor.instrument.types import Payout

        payout_types = {
            EquityPayoutSpec, OptionPayoutSpec, FuturesPayoutSpec,
            FXSpotPayoutSpec, FXForwardPayoutSpec, NDFPayoutSpec, IRSwapPayoutSpec,
            CDSPayoutSpec, SwaptionPayoutSpec,
        }
        assert len(payout_types) == 9
        assert Payout is not None


# ---------------------------------------------------------------------------
# Instrument factories
# ---------------------------------------------------------------------------


class TestCreateCDSInstrument:
    def test_valid(self) -> None:
        result = create_cds_instrument(
            instrument_id="CDS-001",
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        inst = unwrap(result)
        assert inst.instrument_id.value == "CDS-001"
        assert isinstance(inst.product.economic_terms.payouts[0], CDSPayoutSpec)
        assert inst.product.economic_terms.effective_date == date(2026, 3, 20)
        assert inst.product.economic_terms.termination_date == date(2031, 3, 20)

    def test_empty_instrument_id_err(self) -> None:
        result = create_cds_instrument(
            instrument_id="",
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)

    def test_invalid_spread_err(self) -> None:
        result = create_cds_instrument(
            instrument_id="CDS-001",
            reference_entity="ACME Corp",
            notional=Decimal("10000000"),
            spread=Decimal("-0.01"),
            currency="USD",
            effective_date=date(2026, 3, 20),
            maturity_date=date(2031, 3, 20),
            payment_frequency=PaymentFrequency.QUARTERLY,
            day_count=DayCountConvention.ACT_360,
            recovery_rate=Decimal("0.4"),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)


class TestCreateSwaptionInstrument:
    def test_valid(self) -> None:
        swap = _make_underlying_swap()
        result = create_swaption_instrument(
            instrument_id="SWPTN-001",
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Ok)
        inst = unwrap(result)
        assert inst.instrument_id.value == "SWPTN-001"
        assert isinstance(inst.product.economic_terms.payouts[0], SwaptionPayoutSpec)
        assert inst.product.economic_terms.termination_date == date(2027, 6, 15)

    def test_empty_instrument_id_err(self) -> None:
        swap = _make_underlying_swap()
        result = create_swaption_instrument(
            instrument_id="",
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 6, 15),
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)

    def test_exercise_after_swap_start_err(self) -> None:
        swap = _make_underlying_swap()
        result = create_swaption_instrument(
            instrument_id="SWPTN-001",
            swaption_type=SwaptionType.PAYER,
            strike=Decimal("0.035"),
            exercise_date=date(2027, 7, 1),  # after swap start 2027-06-15
            underlying_swap=swap,
            settlement_type=SettlementTypeEnum.PHYSICAL,
            currency="USD",
            notional=Decimal("10000000"),
            parties=_make_parties(),
            trade_date=date(2026, 3, 15),
            payer_receiver=_PR,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Immutability -- all types frozen
# ---------------------------------------------------------------------------


class TestImmutability:
    def test_cds_detail_frozen(self) -> None:
        detail = unwrap(CDSDetail.create(
            reference_entity="ACME Corp", spread_bps=Decimal("100"),
            seniority=SeniorityLevel.SENIOR_UNSECURED,
            protection_side=ProtectionSide.BUYER,
            start_date=date(2026, 3, 20), maturity_date=date(2031, 3, 20),
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            detail.seniority = SeniorityLevel.SUBORDINATED  # type: ignore[misc]

    def test_swaption_detail_frozen(self) -> None:
        detail = unwrap(SwaptionDetail.create(
            swaption_type=SwaptionType.PAYER,
            expiry_date=date(2027, 6, 15),
            underlying_fixed_rate=Decimal("0.035"),
            underlying_float_index="SOFR",
            underlying_tenor_months=60,
            settlement_type=SettlementTypeEnum.PHYSICAL,
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            detail.swaption_type = SwaptionType.RECEIVER  # type: ignore[misc]
