"""Lifecycle state machine and PrimitiveInstruction variants.

EQUITY_TRANSITIONS / DERIVATIVE_TRANSITIONS / FX_TRANSITIONS / IRS_TRANSITIONS /
CDS_TRANSITIONS / SWAPTION_TRANSITIONS define valid state transitions.
PrimitiveInstruction covers equities, options, futures, FX, IRS, CDS, and swaptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import final

from attestor.core.errors import IllegalTransitionError
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import CreditEventType, MarginType
from attestor.instrument.types import PositionStatusEnum

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
    event_type: CreditEventType
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


PrimitiveInstruction = (
    ExecutePI | TransferPI | DividendPI
    | ExercisePI | AssignPI | ExpiryPI | MarginPI
    | FixingPI | NettingPI | MaturityPI
    | CreditEventPI | SwaptionExercisePI | CollateralCallPI
)


@final
@dataclass(frozen=True, slots=True)
class BusinessEvent:
    """A business event wrapping a primitive instruction."""

    instruction: PrimitiveInstruction
    timestamp: UtcDatetime
    attestation_id: str | None = None
