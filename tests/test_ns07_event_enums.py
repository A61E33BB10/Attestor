"""NS7a tests — event-common enum alignment to CDM Rosetta.

Tests cover:
- ClosedStateEnum (7 members, +Allocated)
- TransferStatusEnum (5 members, PascalCase values)
- EventIntentEnum (23 members, expanded)
- CorporateActionTypeEnum (20 members, expanded)
- ActionEnum (3 members, PascalCase values)
- CreditEventTypeEnum (13 members, renamed + expanded)
- ExecutionTypeEnum (3 members, new)
- ConfirmationStatusEnum (2 members, new)
- AffirmationStatusEnum (2 members, new)
"""

from __future__ import annotations

from attestor.instrument.derivative_types import CreditEventTypeEnum
from attestor.instrument.lifecycle import (
    ActionEnum,
    AffirmationStatusEnum,
    ClosedStateEnum,
    ConfirmationStatusEnum,
    CorporateActionTypeEnum,
    EventIntentEnum,
    ExecutionTypeEnum,
    TransferStatusEnum,
)

# ---------------------------------------------------------------------------
# ClosedStateEnum
# ---------------------------------------------------------------------------


class TestClosedStateEnum:
    def test_count(self) -> None:
        assert len(ClosedStateEnum) == 7

    def test_allocated_member(self) -> None:
        assert ClosedStateEnum.ALLOCATED.value == "Allocated"

    def test_pascal_case_values(self) -> None:
        assert ClosedStateEnum.MATURED.value == "Matured"
        assert ClosedStateEnum.TERMINATED.value == "Terminated"
        assert ClosedStateEnum.NOVATED.value == "Novated"
        assert ClosedStateEnum.EXERCISED.value == "Exercised"
        assert ClosedStateEnum.EXPIRED.value == "Expired"
        assert ClosedStateEnum.CANCELLED.value == "Cancelled"

    def test_all_names(self) -> None:
        expected = {
            "ALLOCATED", "CANCELLED", "EXERCISED",
            "EXPIRED", "MATURED", "NOVATED", "TERMINATED",
        }
        assert {e.name for e in ClosedStateEnum} == expected


# ---------------------------------------------------------------------------
# TransferStatusEnum
# ---------------------------------------------------------------------------


class TestTransferStatusEnum:
    def test_count(self) -> None:
        assert len(TransferStatusEnum) == 5

    def test_pascal_case_values(self) -> None:
        assert TransferStatusEnum.PENDING.value == "Pending"
        assert TransferStatusEnum.INSTRUCTED.value == "Instructed"
        assert TransferStatusEnum.SETTLED.value == "Settled"
        assert TransferStatusEnum.NETTED.value == "Netted"
        assert TransferStatusEnum.DISPUTED.value == "Disputed"


# ---------------------------------------------------------------------------
# EventIntentEnum
# ---------------------------------------------------------------------------


class TestEventIntentEnum:
    def test_count(self) -> None:
        assert len(EventIntentEnum) == 23

    def test_pascal_case_values(self) -> None:
        assert EventIntentEnum.ALLOCATION.value == "Allocation"
        assert EventIntentEnum.CASH_FLOW.value == "CashFlow"
        assert EventIntentEnum.CLEARING.value == "Clearing"
        assert EventIntentEnum.COMPRESSION.value == "Compression"

    def test_new_members(self) -> None:
        assert EventIntentEnum.CONTRACT_FORMATION.value == "ContractFormation"
        assert EventIntentEnum.CONTRACT_TERMS_AMENDMENT.value == "ContractTermsAmendment"
        assert EventIntentEnum.CORPORATE_ACTION_ADJUSTMENT.value == "CorporateActionAdjustment"
        assert EventIntentEnum.CREDIT_EVENT.value == "CreditEvent"
        assert EventIntentEnum.DECREASE.value == "Decrease"
        assert EventIntentEnum.EARLY_TERMINATION_PROVISION.value == "EarlyTerminationProvision"
        assert EventIntentEnum.NOTIONAL_RESET.value == "NotionalReset"
        assert EventIntentEnum.NOTIONAL_STEP.value == "NotionalStep"
        assert EventIntentEnum.OBSERVATION_RECORD.value == "ObservationRecord"
        assert EventIntentEnum.OPTION_EXERCISE.value == "OptionExercise"
        assert EventIntentEnum.OPTIONAL_CANCELLATION.value == "OptionalCancellation"
        assert EventIntentEnum.OPTIONAL_EXTENSION.value == "OptionalExtension"
        assert EventIntentEnum.PORTFOLIO_REBALANCING.value == "PortfolioRebalancing"
        assert EventIntentEnum.PRINCIPAL_EXCHANGE.value == "PrincipalExchange"
        assert EventIntentEnum.REALLOCATION.value == "Reallocation"
        assert EventIntentEnum.REPURCHASE.value == "Repurchase"

    def test_all_names(self) -> None:
        expected = {
            "ALLOCATION", "CASH_FLOW", "CLEARING", "COMPRESSION",
            "CONTRACT_FORMATION", "CONTRACT_TERMS_AMENDMENT",
            "CORPORATE_ACTION_ADJUSTMENT", "CREDIT_EVENT",
            "DECREASE", "EARLY_TERMINATION_PROVISION",
            "INCREASE", "INDEX_TRANSITION",
            "NOTIONAL_RESET", "NOTIONAL_STEP",
            "NOVATION", "OBSERVATION_RECORD",
            "OPTION_EXERCISE", "OPTIONAL_CANCELLATION",
            "OPTIONAL_EXTENSION", "PORTFOLIO_REBALANCING",
            "PRINCIPAL_EXCHANGE", "REALLOCATION", "REPURCHASE",
        }
        assert {e.name for e in EventIntentEnum} == expected


# ---------------------------------------------------------------------------
# CorporateActionTypeEnum
# ---------------------------------------------------------------------------


class TestCorporateActionTypeEnum:
    def test_count(self) -> None:
        assert len(CorporateActionTypeEnum) == 20

    def test_pascal_case_values(self) -> None:
        assert CorporateActionTypeEnum.CASH_DIVIDEND.value == "CashDividend"
        assert CorporateActionTypeEnum.STOCK_SPLIT.value == "StockSplit"
        assert CorporateActionTypeEnum.MERGER.value == "Merger"

    def test_new_members(self) -> None:
        assert CorporateActionTypeEnum.DELISTING.value == "Delisting"
        assert CorporateActionTypeEnum.STOCK_NAME_CHANGE.value == "StockNameChange"
        assert CorporateActionTypeEnum.STOCK_IDENTIFIER_CHANGE.value == "StockIdentifierChange"
        assert CorporateActionTypeEnum.RIGHTS_ISSUE.value == "RightsIssue"
        assert CorporateActionTypeEnum.TAKEOVER.value == "Takeover"
        assert CorporateActionTypeEnum.STOCK_RECLASSIFICATION.value == "StockReclassification"
        assert CorporateActionTypeEnum.BONUS_ISSUE.value == "BonusIssue"
        assert CorporateActionTypeEnum.CLASS_ACTION.value == "ClassAction"
        assert CorporateActionTypeEnum.EARLY_REDEMPTION.value == "EarlyRedemption"
        assert CorporateActionTypeEnum.LIQUIDATION.value == "Liquidation"
        assert CorporateActionTypeEnum.BANKRUPTCY_OR_INSOLVENCY.value == "BankruptcyOrInsolvency"
        assert CorporateActionTypeEnum.ISSUER_NATIONALIZATION.value == "IssuerNationalization"
        assert CorporateActionTypeEnum.RELISTING.value == "Relisting"
        assert CorporateActionTypeEnum.BESPOKE_EVENT.value == "BespokeEvent"


# ---------------------------------------------------------------------------
# ActionEnum
# ---------------------------------------------------------------------------


class TestActionEnum:
    def test_count(self) -> None:
        assert len(ActionEnum) == 3

    def test_pascal_case_values(self) -> None:
        assert ActionEnum.NEW.value == "New"
        assert ActionEnum.CORRECT.value == "Correct"
        assert ActionEnum.CANCEL.value == "Cancel"


# ---------------------------------------------------------------------------
# CreditEventTypeEnum
# ---------------------------------------------------------------------------


class TestCreditEventTypeEnum:
    def test_count(self) -> None:
        assert len(CreditEventTypeEnum) == 13

    def test_pascal_case_values(self) -> None:
        assert CreditEventTypeEnum.BANKRUPTCY.value == "Bankruptcy"
        assert CreditEventTypeEnum.FAILURE_TO_PAY.value == "FailureToPay"
        assert CreditEventTypeEnum.RESTRUCTURING.value == "Restructuring"

    def test_new_members(self) -> None:
        drd = CreditEventTypeEnum.DISTRESSED_RATINGS_DOWNGRADE
        assert drd.value == "DistressedRatingsDowngrade"
        assert CreditEventTypeEnum.FAILURE_TO_PAY_INTEREST.value == "FailureToPayInterest"
        assert CreditEventTypeEnum.FAILURE_TO_PAY_PRINCIPAL.value == "FailureToPayPrincipal"
        assert CreditEventTypeEnum.IMPLIED_WRITEDOWN.value == "ImpliedWritedown"
        assert CreditEventTypeEnum.MATURITY_EXTENSION.value == "MaturityExtension"
        assert CreditEventTypeEnum.OBLIGATION_ACCELERATION.value == "ObligationAcceleration"
        assert CreditEventTypeEnum.WRITEDOWN.value == "Writedown"

    def test_all_names(self) -> None:
        expected = {
            "BANKRUPTCY", "DISTRESSED_RATINGS_DOWNGRADE",
            "FAILURE_TO_PAY", "FAILURE_TO_PAY_INTEREST",
            "FAILURE_TO_PAY_PRINCIPAL", "GOVERNMENTAL_INTERVENTION",
            "IMPLIED_WRITEDOWN", "MATURITY_EXTENSION",
            "OBLIGATION_ACCELERATION", "OBLIGATION_DEFAULT",
            "REPUDIATION_MORATORIUM", "RESTRUCTURING", "WRITEDOWN",
        }
        assert {e.name for e in CreditEventTypeEnum} == expected


# ---------------------------------------------------------------------------
# ExecutionTypeEnum (new)
# ---------------------------------------------------------------------------


class TestExecutionTypeEnum:
    def test_count(self) -> None:
        assert len(ExecutionTypeEnum) == 3

    def test_values(self) -> None:
        assert ExecutionTypeEnum.ELECTRONIC.value == "Electronic"
        assert ExecutionTypeEnum.OFF_FACILITY.value == "OffFacility"
        assert ExecutionTypeEnum.ON_VENUE.value == "OnVenue"


# ---------------------------------------------------------------------------
# ConfirmationStatusEnum (new)
# ---------------------------------------------------------------------------


class TestConfirmationStatusEnum:
    def test_count(self) -> None:
        assert len(ConfirmationStatusEnum) == 2

    def test_values(self) -> None:
        assert ConfirmationStatusEnum.CONFIRMED.value == "Confirmed"
        assert ConfirmationStatusEnum.UNCONFIRMED.value == "Unconfirmed"


# ---------------------------------------------------------------------------
# AffirmationStatusEnum (new)
# ---------------------------------------------------------------------------


class TestAffirmationStatusEnum:
    def test_count(self) -> None:
        assert len(AffirmationStatusEnum) == 2

    def test_values(self) -> None:
        assert AffirmationStatusEnum.AFFIRMED.value == "Affirmed"
        assert AffirmationStatusEnum.UNAFFIRMED.value == "Unaffirmed"
