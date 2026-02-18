"""Lifecycle state machine and PrimitiveInstruction variants.

EQUITY_TRANSITIONS / DERIVATIVE_TRANSITIONS / FX_TRANSITIONS / IRS_TRANSITIONS /
CDS_TRANSITIONS / SWAPTION_TRANSITIONS define valid state transitions.
PrimitiveInstruction covers equities, options, futures, FX, IRS, CDS, and swaptions.

Phase D additions: ClosedStateEnum, TransferStatusEnum, EventIntentEnum,
CorporateActionTypeEnum, ActionEnum, QuantityChangePI, PartyChangePI,
SplitPI, TermsChangePI, IndexTransitionPI, ClosedState, Trade, TradeState,
enriched BusinessEvent.

NS7c additions: 16 CDM event-common enums (valuation, position-event,
margin/collateral, performance-transfer, etc.) and 5 deep types
(CreditEvent, CorporateAction, ObservationEvent, Valuation, Reset).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.errors import IllegalTransitionError
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import FrozenMap, PayerReceiver, UtcDatetime
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import CreditEventTypeEnum, MarginType
from attestor.instrument.types import PositionStatusEnum
from attestor.oracle.observable import FloatingRateIndex

# ---------------------------------------------------------------------------
# Phase D: Enums
# ---------------------------------------------------------------------------


class ClosedStateEnum(Enum):
    """Reason a trade was closed.

    CDM: ClosedStateEnum (7 values).
    """

    ALLOCATED = "Allocated"
    CANCELLED = "Cancelled"
    EXERCISED = "Exercised"
    EXPIRED = "Expired"
    MATURED = "Matured"
    NOVATED = "Novated"
    TERMINATED = "Terminated"


class TransferStatusEnum(Enum):
    """Settlement transfer lifecycle status.

    CDM: TransferStatusEnum (5 values).
    """

    DISPUTED = "Disputed"
    INSTRUCTED = "Instructed"
    NETTED = "Netted"
    PENDING = "Pending"
    SETTLED = "Settled"


class EventIntentEnum(Enum):
    """Business intent of a lifecycle event.

    CDM: EventIntentEnum (23 values).
    """

    ALLOCATION = "Allocation"
    CASH_FLOW = "CashFlow"
    CLEARING = "Clearing"
    COMPRESSION = "Compression"
    CONTRACT_FORMATION = "ContractFormation"
    CONTRACT_TERMS_AMENDMENT = "ContractTermsAmendment"
    CORPORATE_ACTION_ADJUSTMENT = "CorporateActionAdjustment"
    CREDIT_EVENT = "CreditEvent"
    DECREASE = "Decrease"
    EARLY_TERMINATION_PROVISION = "EarlyTerminationProvision"
    INCREASE = "Increase"
    INDEX_TRANSITION = "IndexTransition"
    NOTIONAL_RESET = "NotionalReset"
    NOTIONAL_STEP = "NotionalStep"
    NOVATION = "Novation"
    OBSERVATION_RECORD = "ObservationRecord"
    OPTION_EXERCISE = "OptionExercise"
    OPTIONAL_CANCELLATION = "OptionalCancellation"
    OPTIONAL_EXTENSION = "OptionalExtension"
    PORTFOLIO_REBALANCING = "PortfolioRebalancing"
    PRINCIPAL_EXCHANGE = "PrincipalExchange"
    REALLOCATION = "Reallocation"
    REPURCHASE = "Repurchase"


class CorporateActionTypeEnum(Enum):
    """Corporate action classification.

    CDM: CorporateActionTypeEnum (20 values).
    """

    BANKRUPTCY_OR_INSOLVENCY = "BankruptcyOrInsolvency"
    BESPOKE_EVENT = "BespokeEvent"
    BONUS_ISSUE = "BonusIssue"
    CASH_DIVIDEND = "CashDividend"
    CLASS_ACTION = "ClassAction"
    DELISTING = "Delisting"
    EARLY_REDEMPTION = "EarlyRedemption"
    ISSUER_NATIONALIZATION = "IssuerNationalization"
    LIQUIDATION = "Liquidation"
    MERGER = "Merger"
    RELISTING = "Relisting"
    REVERSE_STOCK_SPLIT = "ReverseStockSplit"
    RIGHTS_ISSUE = "RightsIssue"
    SPIN_OFF = "SpinOff"
    STOCK_DIVIDEND = "StockDividend"
    STOCK_IDENTIFIER_CHANGE = "StockIdentifierChange"
    STOCK_NAME_CHANGE = "StockNameChange"
    STOCK_RECLASSIFICATION = "StockReclassification"
    STOCK_SPLIT = "StockSplit"
    TAKEOVER = "Takeover"


class ActionEnum(Enum):
    """Message action type for trade reporting.

    CDM: ActionEnum (3 values).
    """

    CANCEL = "Cancel"
    CORRECT = "Correct"
    NEW = "New"


class ExecutionTypeEnum(Enum):
    """How a contract was executed.

    CDM: ExecutionTypeEnum (3 values).
    """

    ELECTRONIC = "Electronic"
    OFF_FACILITY = "OffFacility"
    ON_VENUE = "OnVenue"


class ConfirmationStatusEnum(Enum):
    """Confirmation status of a trade.

    CDM: ConfirmationStatusEnum (2 values).
    """

    CONFIRMED = "Confirmed"
    UNCONFIRMED = "Unconfirmed"


class AffirmationStatusEnum(Enum):
    """Affirmation status of a trade.

    CDM: AffirmationStatusEnum (2 values).
    """

    AFFIRMED = "Affirmed"
    UNAFFIRMED = "Unaffirmed"


# ---------------------------------------------------------------------------
# NS7c: Valuation enums
# ---------------------------------------------------------------------------


class ValuationTypeEnum(Enum):
    """Method used for valuation.

    CDM: ValuationTypeEnum (2 values).
    """

    MARK_TO_MARKET = "MarkToMarket"
    MARK_TO_MODEL = "MarkToModel"


class ValuationSourceEnum(Enum):
    """Source of valuation.

    CDM: ValuationSourceEnum (1 value).
    """

    CENTRAL_COUNTERPARTY = "CentralCounterparty"


class ValuationScopeEnum(Enum):
    """Scope of the valuation.

    CDM: ValuationScopeEnum (2 values).
    """

    COLLATERAL = "Collateral"
    TRADE = "Trade"


class PriceTimingEnum(Enum):
    """When a price was sourced during a business day.

    CDM: PriceTimingEnum (2 values).
    """

    CLOSING_PRICE = "ClosingPrice"
    OPENING_PRICE = "OpeningPrice"


# ---------------------------------------------------------------------------
# NS7c: Position / instruction / transfer enums
# ---------------------------------------------------------------------------


class PositionEventIntentEnum(Enum):
    """Intent associated with a position-level event.

    CDM: PositionEventIntentEnum (7 values).
    """

    POSITION_CREATION = "PositionCreation"
    CORPORATE_ACTION_ADJUSTMENT = "CorporateActionAdjustment"
    DECREASE = "Decrease"
    INCREASE = "Increase"
    TRANSFER = "Transfer"
    OPTION_EXERCISE = "OptionExercise"
    VALUATION = "Valuation"


class RecordAmountTypeEnum(Enum):
    """Account level for billing summary.

    CDM: RecordAmountTypeEnum (3 values).
    """

    ACCOUNT_TOTAL = "AccountTotal"
    GRAND_TOTAL = "GrandTotal"
    PARENT_TOTAL = "ParentTotal"


class InstructionFunctionEnum(Enum):
    """BusinessEvent function associated with input instructions.

    CDM: InstructionFunctionEnum (5 values).
    """

    EXECUTION = "Execution"
    CONTRACT_FORMATION = "ContractFormation"
    QUANTITY_CHANGE = "QuantityChange"
    RENEGOTIATION = "Renegotiation"
    COMPRESSION = "Compression"


class PerformanceTransferTypeEnum(Enum):
    """Origin of a performance transfer.

    CDM: PerformanceTransferTypeEnum (7 values).
    """

    COMMODITY = "Commodity"
    CORRELATION = "Correlation"
    DIVIDEND = "Dividend"
    EQUITY = "Equity"
    INTEREST = "Interest"
    VOLATILITY = "Volatility"
    VARIANCE = "Variance"


class AssetTransferTypeEnum(Enum):
    """Qualification of asset transfer type.

    CDM: AssetTransferTypeEnum (1 value).
    """

    FREE_OF_PAYMENT = "FreeOfPayment"


# ---------------------------------------------------------------------------
# NS7c: Margin / collateral enums
# ---------------------------------------------------------------------------


class CallTypeEnum(Enum):
    """Intended status of margin call message.

    CDM: CallTypeEnum (3 values).
    """

    MARGIN_CALL = "MarginCall"
    NOTIFICATION = "Notification"
    EXPECTED_CALL = "ExpectedCall"


class MarginCallActionEnum(Enum):
    """Collateral action instruction.

    CDM: MarginCallActionEnum (2 values).
    """

    DELIVERY = "Delivery"
    RETURN = "Return"


class CollateralStatusEnum(Enum):
    """Settlement status of collateral.

    CDM: CollateralStatusEnum (3 values).
    """

    FULL_AMOUNT = "FullAmount"
    SETTLED_AMOUNT = "SettledAmount"
    IN_TRANSIT_AMOUNT = "InTransitAmount"


class MarginCallResponseTypeEnum(Enum):
    """Response type to a margin call.

    CDM: MarginCallResponseTypeEnum (3 values).
    """

    AGREE_IN_FULL = "AgreeinFull"
    PARTIALLY_AGREE = "PartiallyAgree"
    DISPUTE = "Dispute"


class RegMarginTypeEnum(Enum):
    """Margin type in relation to regulatory obligation.

    CDM: RegMarginTypeEnum (3 values).
    """

    VM = "VM"
    REG_IM = "RegIM"
    NON_REG_IM = "NonRegIM"


class RegIMRoleEnum(Enum):
    """Party role in regulatory initial margin call.

    CDM: RegIMRoleEnum (2 values).
    """

    PLEDGOR = "Pledgor"
    SECURED = "Secured"


class HaircutIndicatorEnum(Enum):
    """Whether asset valuation includes haircut.

    CDM: HaircutIndicatorEnum (2 values).
    """

    PRE_HAIRCUT = "PreHaircut"
    POST_HAIRCUT = "PostHaircut"


# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

type TransitionTable = frozenset[tuple[PositionStatusEnum, PositionStatusEnum]]

EQUITY_TRANSITIONS: TransitionTable = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),
})

# Options and futures share the same transition edges as equities.
DERIVATIVE_TRANSITIONS: TransitionTable = EQUITY_TRANSITIONS

# FX instruments (spot, forward, NDF) share equity transition edges.
FX_TRANSITIONS: TransitionTable = EQUITY_TRANSITIONS

# IRS instruments share equity transition edges.
IRS_TRANSITIONS: TransitionTable = EQUITY_TRANSITIONS

# CDS instruments share equity transition edges.
CDS_TRANSITIONS: TransitionTable = EQUITY_TRANSITIONS

# Swaption instruments share equity transition edges.
SWAPTION_TRANSITIONS: TransitionTable = EQUITY_TRANSITIONS


def check_transition(
    from_state: PositionStatusEnum,
    to_state: PositionStatusEnum,
    transitions: TransitionTable = EQUITY_TRANSITIONS,
) -> Ok[None] | Err[IllegalTransitionError]:
    """Validate a state transition against a transition table."""
    if (from_state, to_state) in transitions:
        return Ok(None)
    return Err(IllegalTransitionError(
        message=f"Invalid transition: {from_state.value} -> {to_state.value}",
        code="ILLEGAL_TRANSITION",
        timestamp=UtcDatetime.now(),
        source="instrument.lifecycle.check_transition",
        from_state=from_state.value,
        to_state=to_state.value,
    ))


# ---------------------------------------------------------------------------
# PrimitiveInstruction variants (Phase 1 subset)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ExecutePI:
    """Execute a new trade."""

    order: CanonicalOrder


@final
@dataclass(frozen=True, slots=True)
class TransferPI:
    """Settlement transfer — cash and securities."""

    instrument_id: NonEmptyStr
    quantity: PositiveDecimal
    cash_amount: Money
    from_account: NonEmptyStr
    to_account: NonEmptyStr


@final
@dataclass(frozen=True, slots=True)
class DividendPI:
    """Dividend payment instruction."""

    instrument_id: NonEmptyStr
    amount_per_share: PositiveDecimal
    ex_date: date
    payment_date: date
    currency: NonEmptyStr


@final
@dataclass(frozen=True, slots=True)
class ExercisePI:
    """Option exercise instruction.

    settlement_type comes from order.instrument_detail (contract-level).
    """

    order: CanonicalOrder


@final
@dataclass(frozen=True, slots=True)
class AssignPI:
    """Option assignment instruction (counterparty side of exercise)."""

    order: CanonicalOrder


@final
@dataclass(frozen=True, slots=True)
class ExpiryPI:
    """Option/futures expiry instruction."""

    instrument_id: NonEmptyStr
    expiry_date: date


@final
@dataclass(frozen=True, slots=True)
class MarginPI:
    """Margin call/return instruction."""

    instrument_id: NonEmptyStr
    margin_amount: Money
    margin_type: MarginType


# ---------------------------------------------------------------------------
# Phase 3 PrimitiveInstruction variants — FX / IRS
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FixingPI:
    """Rate fixing instruction (FX NDF fixing or IRS rate reset)."""

    instrument_id: NonEmptyStr
    fixing_date: date
    fixing_rate: Decimal
    fixing_source: NonEmptyStr


@final
@dataclass(frozen=True, slots=True)
class NettingPI:
    """Netting instruction — aggregate offsetting FX positions."""

    instrument_ids: tuple[NonEmptyStr, ...]
    netting_date: date
    net_amount: Money


@final
@dataclass(frozen=True, slots=True)
class MaturityPI:
    """Maturity instruction — IRS or FX forward reaching end of life."""

    instrument_id: NonEmptyStr
    maturity_date: date


# ---------------------------------------------------------------------------
# Phase 4 PrimitiveInstruction variants — CDS / Swaptions / Collateral
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CreditEventPI:
    """Credit event declaration -- triggers protection leg."""

    instrument_id: NonEmptyStr
    event_type: CreditEventTypeEnum
    determination_date: date
    auction_price: Decimal | None  # None before auction, populated after


@final
@dataclass(frozen=True, slots=True)
class SwaptionCashSettlement:
    """Cash settlement details for swaption exercise."""

    settlement_amount: Money


@final
@dataclass(frozen=True, slots=True)
class SwaptionPhysicalSettlement:
    """Physical settlement details for swaption exercise."""

    underlying_irs_id: NonEmptyStr


@final
@dataclass(frozen=True, slots=True)
class SwaptionExercisePI:
    """Swaption exercise -- converts swaption into underlying IRS."""

    instrument_id: NonEmptyStr
    exercise_date: date
    settlement: SwaptionCashSettlement | SwaptionPhysicalSettlement


@final
@dataclass(frozen=True, slots=True)
class CollateralCallPI:
    """Collateral margin call instruction."""

    agreement_id: NonEmptyStr
    call_amount: Money
    call_date: date
    collateral_type: NonEmptyStr  # "CASH" or instrument ID


# ---------------------------------------------------------------------------
# Phase D PrimitiveInstruction variants
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class QuantityChangePI:
    """Partial termination or notional decrease.

    CDM: QuantityChangePrimitive = before + after quantities.
    We model as a delta: negative = decrease, must be non-zero.
    """

    instrument_id: NonEmptyStr
    quantity_change: Decimal
    effective_date: date

    def __post_init__(self) -> None:
        if (
            not isinstance(self.quantity_change, Decimal)
            or not self.quantity_change.is_finite()
        ):
            raise TypeError(
                "QuantityChangePI.quantity_change must be finite Decimal, "
                f"got {self.quantity_change!r}"
            )
        if self.quantity_change == 0:
            raise TypeError("QuantityChangePI.quantity_change must be non-zero")


@final
@dataclass(frozen=True, slots=True)
class PartyChangePI:
    """Novation: transfer of obligations from old party to new party.

    CDM: PartyChangePrimitive = old_party + new_party.
    Invariant: old_party != new_party.
    """

    instrument_id: NonEmptyStr
    old_party: NonEmptyStr
    new_party: NonEmptyStr
    effective_date: date

    def __post_init__(self) -> None:
        if self.old_party == self.new_party:
            raise TypeError(
                "PartyChangePI: old_party must differ from new_party, "
                f"both are {self.old_party!r}"
            )


@final
@dataclass(frozen=True, slots=True)
class SplitPI:
    """Trade allocation: split into sub-trades.

    CDM: SplitPrimitive = list of resulting trades.
    Invariant: at least 2 resulting trade IDs (splitting into 1 is a no-op).
    """

    instrument_id: NonEmptyStr
    split_into: tuple[NonEmptyStr, ...]
    effective_date: date

    def __post_init__(self) -> None:
        if len(self.split_into) < 2:
            raise TypeError(
                "SplitPI.split_into must contain at least 2 trade IDs, "
                f"got {len(self.split_into)}"
            )
        if len(set(self.split_into)) != len(self.split_into):
            raise TypeError(
                "SplitPI.split_into must contain distinct trade IDs"
            )


@final
@dataclass(frozen=True, slots=True)
class TermsChangePI:
    """Amendment to trade terms.

    CDM: TermsChangePrimitive = before + after terms.
    We model as a map of changed field names to new values.
    Invariant: at least one field must be changed.
    """

    instrument_id: NonEmptyStr
    changed_fields: FrozenMap[str, str]
    effective_date: date

    def __post_init__(self) -> None:
        if len(self.changed_fields) == 0:
            raise TypeError(
                "TermsChangePI.changed_fields must contain at least one entry"
            )


@final
@dataclass(frozen=True, slots=True)
class IndexTransitionPI:
    """IBOR fallback transition.

    CDM: IndexTransitionInstruction = old_index + new_index + spread_adjustment.
    Invariant: old_index != new_index.
    """

    instrument_id: NonEmptyStr
    old_index: FloatingRateIndex
    new_index: FloatingRateIndex
    spread_adjustment: Decimal
    effective_date: date

    def __post_init__(self) -> None:
        if (
            not isinstance(self.spread_adjustment, Decimal)
            or not self.spread_adjustment.is_finite()
        ):
            raise TypeError(
                "IndexTransitionPI.spread_adjustment must be finite Decimal, "
                f"got {self.spread_adjustment!r}"
            )
        if self.old_index == self.new_index:
            raise TypeError(
                "IndexTransitionPI: old_index must differ from new_index"
            )


PrimitiveInstruction = (
    ExecutePI | TransferPI | DividendPI
    | ExercisePI | AssignPI | ExpiryPI | MarginPI
    | FixingPI | NettingPI | MaturityPI
    | CreditEventPI | SwaptionExercisePI | CollateralCallPI
    | QuantityChangePI | PartyChangePI | SplitPI
    | TermsChangePI | IndexTransitionPI
)


# ---------------------------------------------------------------------------
# Phase D: ClosedState, Trade, TradeState
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ClosedState:
    """Reason and date a trade was closed.

    CDM: ClosedState = state + activityDate + effectiveDate + lastPaymentDate.
    """

    state: ClosedStateEnum
    activity_date: date
    effective_date: date | None = None
    last_payment_date: date | None = None


@final
@dataclass(frozen=True, slots=True)
class Trade:
    """A trade with counterparty role assignments.

    CDM: Trade = tradeIdentifier + tradeDate + party + partyRole + product
    + executionDetails + contractDetails + clearedDate.
    """

    trade_id: NonEmptyStr
    trade_date: date
    payer_receiver: PayerReceiver
    product_id: NonEmptyStr
    currency: NonEmptyStr
    legal_agreement_id: NonEmptyStr | None = None
    # NS7b: CDM executionDetails fields
    execution_type: ExecutionTypeEnum | None = None
    execution_venue: NonEmptyStr | None = None
    cleared_date: date | None = None

    def __post_init__(self) -> None:
        # CDM: execution_venue is nested inside ExecutionDetails with execution_type
        if self.execution_venue is not None and self.execution_type is None:
            raise TypeError(
                "Trade: execution_venue requires execution_type"
            )
        # CDM condition ExecutionVenue: Electronic requires venue
        if (
            self.execution_type == ExecutionTypeEnum.ELECTRONIC
            and self.execution_venue is None
        ):
            raise TypeError(
                "Trade: ELECTRONIC execution_type requires execution_venue"
            )


@final
@dataclass(frozen=True, slots=True)
class TradeState:
    """Immutable snapshot of a trade's current state.

    CDM: TradeState = trade + state + resetHistory + transferHistory.
    State evolution: (TradeState, BusinessEvent) -> TradeState.
    This is a snapshot, not a mutable container.
    """

    trade: Trade
    status: PositionStatusEnum
    closed_state: ClosedState | None = None
    reset_history: tuple[UtcDatetime, ...] = ()
    transfer_history: tuple[UtcDatetime, ...] = ()
    # NS7b: CDM observationHistory + valuationHistory
    observation_history: tuple[UtcDatetime, ...] = ()
    valuation_history: tuple[UtcDatetime, ...] = ()

    def __post_init__(self) -> None:
        # If closed, must have a closed_state
        if self.status == PositionStatusEnum.CLOSED and self.closed_state is None:
            raise TypeError(
                "TradeState: closed_state is required when status is CLOSED"
            )
        # If not closed, closed_state must be None
        if self.status != PositionStatusEnum.CLOSED and self.closed_state is not None:
            raise TypeError(
                "TradeState: closed_state must be None when status is not CLOSED, "
                f"got status={self.status!r}"
            )


# ---------------------------------------------------------------------------
# BusinessEvent (Phase D enrichment)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class BusinessEvent:
    """A business event wrapping a primitive instruction.

    CDM: BusinessEvent extends EventInstruction.
    EventInstruction = instruction + before + intent + eventDate
    + effectiveDate + corporateActionIntent.
    BusinessEvent adds eventQualifier + after (0..*).
    """

    instruction: PrimitiveInstruction
    timestamp: UtcDatetime
    attestation_id: str | None = None
    before: TradeState | None = None
    after: tuple[TradeState, ...] = ()
    event_intent: EventIntentEnum | None = None
    action: ActionEnum = ActionEnum.NEW
    event_ref: NonEmptyStr | None = None
    # NS7b: CDM EventInstruction + BusinessEvent fields
    event_date: date | None = None
    effective_date: date | None = None
    event_qualifier: NonEmptyStr | None = None
    corporate_action_intent: CorporateActionTypeEnum | None = None

    def __post_init__(self) -> None:
        # CDM condition CorporateAction: if corporateActionIntent exists
        # then intent = EventIntentEnum -> CorporateActionAdjustment
        if (
            self.corporate_action_intent is not None
            and self.event_intent != EventIntentEnum.CORPORATE_ACTION_ADJUSTMENT
        ):
            raise TypeError(
                "BusinessEvent: corporate_action_intent requires "
                "event_intent=CORPORATE_ACTION_ADJUSTMENT"
            )


# ---------------------------------------------------------------------------
# NS7c: Deep event-common types
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CreditEvent:
    """Relevant data for a credit event.

    CDM: CreditEvent — creditEventType + determination date + auction
    + recovery + referenceInformation.
    """

    credit_event_type: CreditEventTypeEnum
    event_determination_date: date
    reference_entity: NonEmptyStr
    auction_date: date | None = None
    recovery_percent: Decimal | None = None

    def __post_init__(self) -> None:
        if self.recovery_percent is not None and not (
            Decimal("0") <= self.recovery_percent <= Decimal("1")
        ):
            raise TypeError(
                "CreditEvent: recovery_percent must be in [0, 1], "
                f"got {self.recovery_percent}"
            )


@final
@dataclass(frozen=True, slots=True)
class CorporateAction:
    """Relevant data for a corporate action.

    CDM: CorporateAction — type + ex/pay/record/announcement dates
    + underlier.  CDM condition: bespoke_event_description required
    when type is BESPOKE_EVENT.
    """

    corporate_action_type: CorporateActionTypeEnum
    ex_date: date
    pay_date: date
    underlier: NonEmptyStr
    record_date: date | None = None
    announcement_date: date | None = None
    bespoke_event_description: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        if (
            self.corporate_action_type == CorporateActionTypeEnum.BESPOKE_EVENT
            and self.bespoke_event_description is None
        ):
            raise TypeError(
                "CorporateAction: bespoke_event_description required "
                "when corporate_action_type is BESPOKE_EVENT"
            )


@final
@dataclass(frozen=True, slots=True)
class ObservationEvent:
    """An observation event — credit event or corporate action.

    CDM: ObservationEvent with one-of condition.
    """

    credit_event: CreditEvent | None = None
    corporate_action: CorporateAction | None = None

    def __post_init__(self) -> None:
        has_credit = self.credit_event is not None
        has_corp = self.corporate_action is not None
        if has_credit == has_corp:
            raise TypeError(
                "ObservationEvent: exactly one of credit_event or "
                "corporate_action must be set"
            )


@final
@dataclass(frozen=True, slots=True)
class Valuation:
    """Value of an investment, asset, or security.

    CDM: Valuation — amount + timestamp + method/source + scope.
    CDM condition: required choice method, source (exactly one).
    """

    amount: Money
    timestamp: UtcDatetime
    scope: ValuationScopeEnum
    method: ValuationTypeEnum | None = None
    source: ValuationSourceEnum | None = None
    delta: Decimal | None = None
    valuation_timing: PriceTimingEnum | None = None

    def __post_init__(self) -> None:
        has_method = self.method is not None
        has_source = self.source is not None
        if has_method == has_source:
            raise TypeError(
                "Valuation: exactly one of method or source must be set"
            )


@final
@dataclass(frozen=True, slots=True)
class Reset:
    """Reset/fixing value produced in cashflow calculations.

    CDM: Reset — resetValue (price) + resetDate + rateRecordDate.
    """

    reset_value: Decimal
    reset_date: date
    rate_record_date: date | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.reset_value, Decimal) or not self.reset_value.is_finite():
            raise TypeError(
                f"Reset: reset_value must be finite Decimal, got {self.reset_value!r}"
            )
