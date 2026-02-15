"""Lifecycle state machine and PrimitiveInstruction variants.

EQUITY_TRANSITIONS defines the valid state transitions for cash equities.
PrimitiveInstruction is the Phase 1 subset: ExecutePI | TransferPI | DividendPI.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import final

from attestor.core.errors import IllegalTransitionError
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.types import PositionStatusEnum

# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

EQUITY_TRANSITIONS: frozenset[tuple[PositionStatusEnum, PositionStatusEnum]] = frozenset({
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.FORMED),
    (PositionStatusEnum.PROPOSED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.SETTLED),
    (PositionStatusEnum.FORMED, PositionStatusEnum.CANCELLED),
    (PositionStatusEnum.SETTLED, PositionStatusEnum.CLOSED),
})


def check_transition(
    from_state: PositionStatusEnum,
    to_state: PositionStatusEnum,
) -> Ok[None] | Err[IllegalTransitionError]:
    """Validate a state transition against the equity transition table."""
    if (from_state, to_state) in EQUITY_TRANSITIONS:
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


# Phase 1 instruction union
PrimitiveInstruction = ExecutePI | TransferPI | DividendPI


@final
@dataclass(frozen=True, slots=True)
class BusinessEvent:
    """A business event wrapping a primitive instruction."""

    instruction: PrimitiveInstruction
    timestamp: UtcDatetime
    attestation_id: str | None = None
