"""NS7c: Deep event-common types and enums — tests.

Tests for:
- 16 new CDM event-common enums (valuation, position, margin, etc.)
- 5 deep types (CreditEvent, CorporateAction, ObservationEvent, Valuation, Reset)
- CDM conditions on deep types
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from attestor.core.money import Money, NonEmptyStr
from attestor.core.types import UtcDatetime
from attestor.instrument.derivative_types import CreditEventTypeEnum
from attestor.instrument.lifecycle import (
    AssetTransferTypeEnum,
    CallTypeEnum,
    CollateralStatusEnum,
    CorporateAction,
    CorporateActionTypeEnum,
    CreditEvent,
    HaircutIndicatorEnum,
    InstructionFunctionEnum,
    MarginCallActionEnum,
    MarginCallResponseTypeEnum,
    ObservationEvent,
    PerformanceTransferTypeEnum,
    PositionEventIntentEnum,
    PriceTimingEnum,
    RecordAmountTypeEnum,
    RegIMRoleEnum,
    RegMarginTypeEnum,
    Reset,
    Valuation,
    ValuationScopeEnum,
    ValuationSourceEnum,
    ValuationTypeEnum,
)

# ---------------------------------------------------------------------------
# Valuation enums
# ---------------------------------------------------------------------------


class TestValuationTypeEnum:
    def test_member_count(self) -> None:
        assert len(ValuationTypeEnum) == 2

    def test_values(self) -> None:
        assert {e.value for e in ValuationTypeEnum} == {
            "MarkToMarket", "MarkToModel",
        }


class TestValuationSourceEnum:
    def test_member_count(self) -> None:
        assert len(ValuationSourceEnum) == 1

    def test_value(self) -> None:
        assert ValuationSourceEnum.CENTRAL_COUNTERPARTY.value == "CentralCounterparty"


class TestValuationScopeEnum:
    def test_member_count(self) -> None:
        assert len(ValuationScopeEnum) == 2

    def test_values(self) -> None:
        assert {e.value for e in ValuationScopeEnum} == {"Collateral", "Trade"}


class TestPriceTimingEnum:
    def test_member_count(self) -> None:
        assert len(PriceTimingEnum) == 2

    def test_values(self) -> None:
        assert {e.value for e in PriceTimingEnum} == {
            "ClosingPrice", "OpeningPrice",
        }


# ---------------------------------------------------------------------------
# Position / instruction / transfer enums
# ---------------------------------------------------------------------------


class TestPositionEventIntentEnum:
    def test_member_count(self) -> None:
        assert len(PositionEventIntentEnum) == 7

    def test_values(self) -> None:
        assert {e.value for e in PositionEventIntentEnum} == {
            "PositionCreation", "CorporateActionAdjustment", "Decrease",
            "Increase", "Transfer", "OptionExercise", "Valuation",
        }


class TestRecordAmountTypeEnum:
    def test_member_count(self) -> None:
        assert len(RecordAmountTypeEnum) == 3

    def test_values(self) -> None:
        assert {e.value for e in RecordAmountTypeEnum} == {
            "AccountTotal", "GrandTotal", "ParentTotal",
        }


class TestInstructionFunctionEnum:
    def test_member_count(self) -> None:
        assert len(InstructionFunctionEnum) == 5

    def test_values(self) -> None:
        assert {e.value for e in InstructionFunctionEnum} == {
            "Execution", "ContractFormation", "QuantityChange",
            "Renegotiation", "Compression",
        }


class TestPerformanceTransferTypeEnum:
    def test_member_count(self) -> None:
        assert len(PerformanceTransferTypeEnum) == 7

    def test_values(self) -> None:
        assert {e.value for e in PerformanceTransferTypeEnum} == {
            "Commodity", "Correlation", "Dividend", "Equity",
            "Interest", "Volatility", "Variance",
        }


class TestAssetTransferTypeEnum:
    def test_member_count(self) -> None:
        assert len(AssetTransferTypeEnum) == 1

    def test_value(self) -> None:
        assert AssetTransferTypeEnum.FREE_OF_PAYMENT.value == "FreeOfPayment"


# ---------------------------------------------------------------------------
# Margin / collateral enums
# ---------------------------------------------------------------------------


class TestCallTypeEnum:
    def test_member_count(self) -> None:
        assert len(CallTypeEnum) == 3

    def test_values(self) -> None:
        assert {e.value for e in CallTypeEnum} == {
            "MarginCall", "Notification", "ExpectedCall",
        }


class TestMarginCallActionEnum:
    def test_member_count(self) -> None:
        assert len(MarginCallActionEnum) == 2

    def test_values(self) -> None:
        assert {e.value for e in MarginCallActionEnum} == {"Delivery", "Return"}


class TestCollateralStatusEnum:
    def test_member_count(self) -> None:
        assert len(CollateralStatusEnum) == 3

    def test_values(self) -> None:
        assert {e.value for e in CollateralStatusEnum} == {
            "FullAmount", "SettledAmount", "InTransitAmount",
        }


class TestMarginCallResponseTypeEnum:
    def test_member_count(self) -> None:
        assert len(MarginCallResponseTypeEnum) == 3

    def test_values(self) -> None:
        assert {e.value for e in MarginCallResponseTypeEnum} == {
            "AgreeinFull", "PartiallyAgree", "Dispute",
        }


class TestRegMarginTypeEnum:
    def test_member_count(self) -> None:
        assert len(RegMarginTypeEnum) == 3

    def test_values(self) -> None:
        assert {e.value for e in RegMarginTypeEnum} == {"VM", "RegIM", "NonRegIM"}


class TestRegIMRoleEnum:
    def test_member_count(self) -> None:
        assert len(RegIMRoleEnum) == 2

    def test_values(self) -> None:
        assert {e.value for e in RegIMRoleEnum} == {"Pledgor", "Secured"}


class TestHaircutIndicatorEnum:
    def test_member_count(self) -> None:
        assert len(HaircutIndicatorEnum) == 2

    def test_values(self) -> None:
        assert {e.value for e in HaircutIndicatorEnum} == {
            "PreHaircut", "PostHaircut",
        }


# ---------------------------------------------------------------------------
# CreditEvent
# ---------------------------------------------------------------------------


def _make_credit_event(**overrides: object) -> CreditEvent:
    defaults: dict[str, object] = {
        "credit_event_type": CreditEventTypeEnum.BANKRUPTCY,
        "event_determination_date": date(2025, 7, 1),
        "reference_entity": NonEmptyStr(value="ACME Corp"),
    }
    defaults.update(overrides)
    return CreditEvent(**defaults)  # type: ignore[arg-type]


class TestCreditEvent:
    def test_valid(self) -> None:
        ce = _make_credit_event()
        assert ce.credit_event_type == CreditEventTypeEnum.BANKRUPTCY
        assert ce.reference_entity.value == "ACME Corp"

    def test_with_auction_and_recovery(self) -> None:
        ce = _make_credit_event(
            auction_date=date(2025, 8, 1),
            recovery_percent=Decimal("0.40"),
        )
        assert ce.auction_date == date(2025, 8, 1)
        assert ce.recovery_percent == Decimal("0.40")

    def test_recovery_percent_zero(self) -> None:
        ce = _make_credit_event(recovery_percent=Decimal("0"))
        assert ce.recovery_percent == Decimal("0")

    def test_recovery_percent_one(self) -> None:
        ce = _make_credit_event(recovery_percent=Decimal("1"))
        assert ce.recovery_percent == Decimal("1")

    def test_recovery_percent_below_zero_rejected(self) -> None:
        with pytest.raises(TypeError, match="recovery_percent"):
            _make_credit_event(recovery_percent=Decimal("-0.01"))

    def test_recovery_percent_above_one_rejected(self) -> None:
        with pytest.raises(TypeError, match="recovery_percent"):
            _make_credit_event(recovery_percent=Decimal("1.01"))

    def test_frozen(self) -> None:
        ce = _make_credit_event()
        with pytest.raises(AttributeError):
            ce.credit_event_type = CreditEventTypeEnum.RESTRUCTURING  # type: ignore[misc]


# ---------------------------------------------------------------------------
# CorporateAction
# ---------------------------------------------------------------------------


def _make_corporate_action(**overrides: object) -> CorporateAction:
    defaults: dict[str, object] = {
        "corporate_action_type": CorporateActionTypeEnum.CASH_DIVIDEND,
        "ex_date": date(2025, 7, 1),
        "pay_date": date(2025, 7, 15),
        "underlier": NonEmptyStr(value="NVDA"),
    }
    defaults.update(overrides)
    return CorporateAction(**defaults)  # type: ignore[arg-type]


class TestCorporateAction:
    def test_valid(self) -> None:
        ca = _make_corporate_action()
        assert ca.corporate_action_type == CorporateActionTypeEnum.CASH_DIVIDEND
        assert ca.underlier.value == "NVDA"

    def test_with_dates(self) -> None:
        ca = _make_corporate_action(
            record_date=date(2025, 6, 28),
            announcement_date=date(2025, 6, 20),
        )
        assert ca.record_date == date(2025, 6, 28)
        assert ca.announcement_date == date(2025, 6, 20)

    def test_bespoke_event_requires_description(self) -> None:
        with pytest.raises(TypeError, match="bespoke_event_description"):
            _make_corporate_action(
                corporate_action_type=CorporateActionTypeEnum.BESPOKE_EVENT,
            )

    def test_bespoke_event_with_description_ok(self) -> None:
        ca = _make_corporate_action(
            corporate_action_type=CorporateActionTypeEnum.BESPOKE_EVENT,
            bespoke_event_description=NonEmptyStr(value="Special restructuring"),
        )
        assert ca.bespoke_event_description is not None
        assert ca.bespoke_event_description.value == "Special restructuring"

    def test_frozen(self) -> None:
        ca = _make_corporate_action()
        with pytest.raises(AttributeError):
            ca.ex_date = date(2025, 8, 1)  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ObservationEvent (one-of condition)
# ---------------------------------------------------------------------------


class TestObservationEvent:
    def test_credit_event_only(self) -> None:
        oe = ObservationEvent(credit_event=_make_credit_event())
        assert oe.credit_event is not None
        assert oe.corporate_action is None

    def test_corporate_action_only(self) -> None:
        oe = ObservationEvent(corporate_action=_make_corporate_action())
        assert oe.corporate_action is not None
        assert oe.credit_event is None

    def test_neither_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            ObservationEvent()

    def test_both_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            ObservationEvent(
                credit_event=_make_credit_event(),
                corporate_action=_make_corporate_action(),
            )

    def test_frozen(self) -> None:
        oe = ObservationEvent(credit_event=_make_credit_event())
        with pytest.raises(AttributeError):
            oe.credit_event = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Valuation (required choice method/source)
# ---------------------------------------------------------------------------


def _make_valuation(**overrides: object) -> Valuation:
    defaults: dict[str, object] = {
        "amount": Money(amount=Decimal("1000000"), currency="USD"),
        "timestamp": UtcDatetime.now(),
        "scope": ValuationScopeEnum.TRADE,
        "method": ValuationTypeEnum.MARK_TO_MARKET,
    }
    defaults.update(overrides)
    return Valuation(**defaults)  # type: ignore[arg-type]


class TestValuation:
    def test_valid_with_method(self) -> None:
        v = _make_valuation()
        assert v.method == ValuationTypeEnum.MARK_TO_MARKET
        assert v.source is None

    def test_valid_with_source(self) -> None:
        v = _make_valuation(
            method=None,
            source=ValuationSourceEnum.CENTRAL_COUNTERPARTY,
        )
        assert v.source == ValuationSourceEnum.CENTRAL_COUNTERPARTY
        assert v.method is None

    def test_neither_method_nor_source_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            _make_valuation(method=None, source=None)

    def test_both_method_and_source_rejected(self) -> None:
        with pytest.raises(TypeError, match="exactly one"):
            _make_valuation(
                method=ValuationTypeEnum.MARK_TO_MODEL,
                source=ValuationSourceEnum.CENTRAL_COUNTERPARTY,
            )

    def test_with_delta(self) -> None:
        v = _make_valuation(delta=Decimal("0.65"))
        assert v.delta == Decimal("0.65")

    def test_with_timing(self) -> None:
        v = _make_valuation(valuation_timing=PriceTimingEnum.CLOSING_PRICE)
        assert v.valuation_timing == PriceTimingEnum.CLOSING_PRICE

    def test_frozen(self) -> None:
        v = _make_valuation()
        with pytest.raises(AttributeError):
            v.scope = ValuationScopeEnum.COLLATERAL  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------


class TestReset:
    def test_valid(self) -> None:
        r = Reset(reset_value=Decimal("0.035"), reset_date=date(2025, 7, 1))
        assert r.reset_value == Decimal("0.035")
        assert r.reset_date == date(2025, 7, 1)
        assert r.rate_record_date is None

    def test_with_rate_record_date(self) -> None:
        r = Reset(
            reset_value=Decimal("0.04"),
            reset_date=date(2025, 7, 1),
            rate_record_date=date(2025, 6, 30),
        )
        assert r.rate_record_date == date(2025, 6, 30)

    def test_infinite_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite"):
            Reset(reset_value=Decimal("Inf"), reset_date=date(2025, 7, 1))

    def test_nan_rejected(self) -> None:
        with pytest.raises(TypeError, match="finite"):
            Reset(reset_value=Decimal("NaN"), reset_date=date(2025, 7, 1))

    def test_frozen(self) -> None:
        r = Reset(reset_value=Decimal("0.035"), reset_date=date(2025, 7, 1))
        with pytest.raises(AttributeError):
            r.reset_value = Decimal("0.04")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Re-exports
# ---------------------------------------------------------------------------


class TestNS7cReExports:
    def test_enums_from_instrument(self) -> None:
        from attestor.instrument import (
            AssetTransferTypeEnum,
            CallTypeEnum,
            CollateralStatusEnum,
            HaircutIndicatorEnum,
            InstructionFunctionEnum,
            MarginCallActionEnum,
            MarginCallResponseTypeEnum,
            PerformanceTransferTypeEnum,
            PositionEventIntentEnum,
            PriceTimingEnum,
            RecordAmountTypeEnum,
            RegIMRoleEnum,
            RegMarginTypeEnum,
            ValuationScopeEnum,
            ValuationSourceEnum,
            ValuationTypeEnum,
        )
        assert len(ValuationTypeEnum) == 2
        assert len(PositionEventIntentEnum) == 7
        assert len(CallTypeEnum) == 3
        assert len(PerformanceTransferTypeEnum) == 7
        assert len(AssetTransferTypeEnum) == 1
        assert len(CollateralStatusEnum) == 3
        assert len(MarginCallActionEnum) == 2
        assert len(MarginCallResponseTypeEnum) == 3
        assert len(RegMarginTypeEnum) == 3
        assert len(RegIMRoleEnum) == 2
        assert len(HaircutIndicatorEnum) == 2
        assert len(RecordAmountTypeEnum) == 3
        assert len(InstructionFunctionEnum) == 5
        assert len(PriceTimingEnum) == 2
        assert len(ValuationScopeEnum) == 2
        assert len(ValuationSourceEnum) == 1

    def test_types_from_instrument(self) -> None:
        from attestor.instrument import (
            CorporateAction,
            CreditEvent,
            ObservationEvent,
            Reset,
            Valuation,
        )
        assert CreditEvent is not None
        assert CorporateAction is not None
        assert ObservationEvent is not None
        assert Valuation is not None
        assert Reset is not None
