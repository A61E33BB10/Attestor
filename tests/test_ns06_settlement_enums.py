"""NS6a tests — settlement-related enums aligned to CDM Rosetta.

Tests cover: SettlementTypeEnum (4), CashSettlementMethodEnum (12),
DeliveryMethodEnum (4), TransferSettlementEnum (4),
StandardSettlementStyleEnum (4), SettlementCentreEnum (2),
ScheduledTransferEnum (12), UnscheduledTransferEnum (2).
"""

from __future__ import annotations

from attestor.instrument.derivative_types import (
    CashSettlementMethodEnum,
    DeliveryMethodEnum,
    ScheduledTransferEnum,
    SettlementCentreEnum,
    SettlementTypeEnum,
    StandardSettlementStyleEnum,
    TransferSettlementEnum,
    UnscheduledTransferEnum,
)

# ---------------------------------------------------------------------------
# SettlementTypeEnum (expanded from 2 to 4)
# ---------------------------------------------------------------------------


class TestSettlementTypeEnum:
    def test_count(self) -> None:
        assert len(SettlementTypeEnum) == 4

    def test_members(self) -> None:
        assert {e.name for e in SettlementTypeEnum} == {
            "CASH", "PHYSICAL", "ELECTION", "CASH_OR_PHYSICAL",
        }

    def test_values_pascal_case(self) -> None:
        assert SettlementTypeEnum.CASH.value == "Cash"
        assert SettlementTypeEnum.PHYSICAL.value == "Physical"
        assert SettlementTypeEnum.ELECTION.value == "Election"
        assert SettlementTypeEnum.CASH_OR_PHYSICAL.value == "CashOrPhysical"

    def test_construct_from_value(self) -> None:
        assert SettlementTypeEnum("Election") is SettlementTypeEnum.ELECTION
        assert SettlementTypeEnum("CashOrPhysical") is SettlementTypeEnum.CASH_OR_PHYSICAL


# ---------------------------------------------------------------------------
# CashSettlementMethodEnum
# ---------------------------------------------------------------------------


class TestCashSettlementMethodEnum:
    def test_count(self) -> None:
        assert len(CashSettlementMethodEnum) == 12

    def test_members(self) -> None:
        assert {e.name for e in CashSettlementMethodEnum} == {
            "CASH_PRICE_METHOD",
            "CASH_PRICE_ALTERNATE_METHOD",
            "PAR_YIELD_CURVE_ADJUSTED_METHOD",
            "ZERO_COUPON_YIELD_ADJUSTED_METHOD",
            "PAR_YIELD_CURVE_UNADJUSTED_METHOD",
            "CROSS_CURRENCY_METHOD",
            "COLLATERALIZED_CASH_PRICE_METHOD",
            "MID_MARKET_INDICATIVE_QUOTATIONS",
            "MID_MARKET_INDICATIVE_QUOTATIONS_ALTERNATE",
            "MID_MARKET_CALCULATION_AGENT_DETERMINATION",
            "REPLACEMENT_VALUE_FIRM_QUOTATIONS",
            "REPLACEMENT_VALUE_CALCULATION_AGENT_DETERMINATION",
        }

    def test_values_pascal_case(self) -> None:
        assert CashSettlementMethodEnum.CASH_PRICE_METHOD.value == "CashPriceMethod"
        assert (
            CashSettlementMethodEnum.PAR_YIELD_CURVE_ADJUSTED_METHOD.value
            == "ParYieldCurveAdjustedMethod"
        )

    def test_construct_from_value(self) -> None:
        assert (
            CashSettlementMethodEnum("CrossCurrencyMethod")
            is CashSettlementMethodEnum.CROSS_CURRENCY_METHOD
        )


# ---------------------------------------------------------------------------
# DeliveryMethodEnum
# ---------------------------------------------------------------------------


class TestDeliveryMethodEnum:
    def test_count(self) -> None:
        assert len(DeliveryMethodEnum) == 4

    def test_members(self) -> None:
        assert {e.name for e in DeliveryMethodEnum} == {
            "DELIVERY_VERSUS_PAYMENT", "FREE_OF_PAYMENT",
            "PRE_DELIVERY", "PRE_PAYMENT",
        }

    def test_values_pascal_case(self) -> None:
        assert DeliveryMethodEnum.DELIVERY_VERSUS_PAYMENT.value == "DeliveryVersusPayment"
        assert DeliveryMethodEnum.FREE_OF_PAYMENT.value == "FreeOfPayment"


# ---------------------------------------------------------------------------
# TransferSettlementEnum
# ---------------------------------------------------------------------------


class TestTransferSettlementEnum:
    def test_count(self) -> None:
        assert len(TransferSettlementEnum) == 4

    def test_members(self) -> None:
        assert {e.name for e in TransferSettlementEnum} == {
            "DELIVERY_VERSUS_DELIVERY", "DELIVERY_VERSUS_PAYMENT",
            "PAYMENT_VERSUS_PAYMENT", "NOT_CENTRAL_SETTLEMENT",
        }

    def test_values_pascal_case(self) -> None:
        assert TransferSettlementEnum.DELIVERY_VERSUS_DELIVERY.value == "DeliveryVersusDelivery"
        assert TransferSettlementEnum.NOT_CENTRAL_SETTLEMENT.value == "NotCentralSettlement"


# ---------------------------------------------------------------------------
# StandardSettlementStyleEnum
# ---------------------------------------------------------------------------


class TestStandardSettlementStyleEnum:
    def test_count(self) -> None:
        assert len(StandardSettlementStyleEnum) == 4

    def test_members(self) -> None:
        assert {e.name for e in StandardSettlementStyleEnum} == {
            "STANDARD", "NET", "STANDARD_AND_NET", "PAIR_AND_NET",
        }

    def test_values_pascal_case(self) -> None:
        assert StandardSettlementStyleEnum.STANDARD.value == "Standard"
        assert StandardSettlementStyleEnum.PAIR_AND_NET.value == "PairAndNet"


# ---------------------------------------------------------------------------
# SettlementCentreEnum
# ---------------------------------------------------------------------------


class TestSettlementCentreEnum:
    def test_count(self) -> None:
        assert len(SettlementCentreEnum) == 2

    def test_members(self) -> None:
        assert {e.name for e in SettlementCentreEnum} == {
            "EUROCLEAR_BANK", "CLEARSTREAM_BANKING_LUXEMBOURG",
        }

    def test_values_pascal_case(self) -> None:
        assert SettlementCentreEnum.EUROCLEAR_BANK.value == "EuroclearBank"
        assert (
            SettlementCentreEnum.CLEARSTREAM_BANKING_LUXEMBOURG.value
            == "ClearstreamBankingLuxembourg"
        )


# ---------------------------------------------------------------------------
# ScheduledTransferEnum
# ---------------------------------------------------------------------------


class TestScheduledTransferEnum:
    def test_count(self) -> None:
        assert len(ScheduledTransferEnum) == 12

    def test_members(self) -> None:
        assert {e.name for e in ScheduledTransferEnum} == {
            "CORPORATE_ACTION", "COUPON", "CREDIT_EVENT",
            "DIVIDEND_RETURN", "EXERCISE", "FIXED_RATE_RETURN",
            "FLOATING_RATE_RETURN", "FRACTIONAL_AMOUNT",
            "INTEREST_RETURN", "NET_INTEREST",
            "PERFORMANCE", "PRINCIPAL",
        }

    def test_values_pascal_case(self) -> None:
        assert ScheduledTransferEnum.CORPORATE_ACTION.value == "CorporateAction"
        assert ScheduledTransferEnum.COUPON.value == "Coupon"
        assert ScheduledTransferEnum.PERFORMANCE.value == "Performance"


# ---------------------------------------------------------------------------
# UnscheduledTransferEnum
# ---------------------------------------------------------------------------


class TestUnscheduledTransferEnum:
    def test_count(self) -> None:
        assert len(UnscheduledTransferEnum) == 2

    def test_members(self) -> None:
        assert {e.name for e in UnscheduledTransferEnum} == {"RECALL", "RETURN"}

    def test_values_pascal_case(self) -> None:
        assert UnscheduledTransferEnum.RECALL.value == "Recall"
        assert UnscheduledTransferEnum.RETURN.value == "Return"
