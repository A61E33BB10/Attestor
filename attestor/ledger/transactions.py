"""Ledger domain types: DeltaValue, StateDelta, DistinctAccountPair, Move, Transaction, etc.

Double-entry bookkeeping invariants enforced by construction, not runtime checks.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, final

from attestor.core.money import NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime

# ---------------------------------------------------------------------------
# DeltaValue sum type (6 variants)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class DeltaDecimal:
    value: Decimal


@final
@dataclass(frozen=True, slots=True)
class DeltaStr:
    value: str


@final
@dataclass(frozen=True, slots=True)
class DeltaBool:
    value: bool


@final
@dataclass(frozen=True, slots=True)
class DeltaDate:
    value: date


@final
@dataclass(frozen=True, slots=True)
class DeltaDatetime:
    value: datetime


@final
@dataclass(frozen=True, slots=True)
class DeltaNull:
    """Represents absence of a value."""


type DeltaValue = DeltaDecimal | DeltaStr | DeltaBool | DeltaDate | DeltaDatetime | DeltaNull


# ---------------------------------------------------------------------------
# AccountType, Account, Position (GAP-33)
# ---------------------------------------------------------------------------


class AccountType(Enum):
    CASH = "CASH"
    SECURITIES = "SECURITIES"
    DERIVATIVES = "DERIVATIVES"
    COLLATERAL = "COLLATERAL"
    MARGIN = "MARGIN"
    ACCRUALS = "ACCRUALS"
    PNL = "PNL"


class ExecuteResult(Enum):
    APPLIED = "APPLIED"
    ALREADY_APPLIED = "ALREADY_APPLIED"
    REJECTED = "REJECTED"


@final
@dataclass(frozen=True, slots=True)
class Account:
    account_id: NonEmptyStr
    account_type: AccountType


@final
@dataclass(frozen=True, slots=True)
class Position:
    account: NonEmptyStr
    instrument: NonEmptyStr
    quantity: Decimal


# ---------------------------------------------------------------------------
# StateDelta, DistinctAccountPair, Move, Transaction, LedgerEntry
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class StateDelta:
    """Records a field-level change for replay/unwind."""

    unit: str
    field: str
    old_value: DeltaValue
    new_value: DeltaValue


@final
@dataclass(frozen=True, slots=True)
class DistinctAccountPair:
    """Debit/credit pair. debit != credit enforced at construction."""

    debit: str
    credit: str

    @staticmethod
    def create(debit: str, credit: str) -> Ok[DistinctAccountPair] | Err[str]:
        if not debit:
            return Err("DistinctAccountPair: debit must be non-empty")
        if not credit:
            return Err("DistinctAccountPair: credit must be non-empty")
        if debit == credit:
            return Err(f"DistinctAccountPair: debit and credit must differ, both are '{debit}'")
        return Ok(DistinctAccountPair(debit=debit, credit=credit))


@final
@dataclass(frozen=True, slots=True)
class Move:
    """Atomic balance transfer — one leg of a transaction."""

    source: str
    destination: str
    unit: str
    quantity: PositiveDecimal
    contract_id: str


@final
@dataclass(frozen=True, slots=True)
class Transaction:
    """Atomic batch of moves."""

    tx_id: str
    moves: tuple[Move, ...]
    timestamp: UtcDatetime
    state_deltas: tuple[StateDelta, ...] = ()


@final
@dataclass(frozen=True, slots=True)
class LedgerEntry:
    """Double-entry enforced by types: debit != credit by construction."""

    accounts: DistinctAccountPair
    instrument: str
    amount: PositiveDecimal
    timestamp: UtcDatetime
    attestation: Any | None = None  # Attestation[object] | None — avoid circular import

    @property
    def debit_account(self) -> str:
        return self.accounts.debit

    @property
    def credit_account(self) -> str:
        return self.accounts.credit
