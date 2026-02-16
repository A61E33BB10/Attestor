"""Shared validation helpers for ledger transaction functions.

Reduces the ~10-line ValidationError wrapping pattern to a 1-liner.
"""

from __future__ import annotations

from decimal import Decimal

from attestor.core.errors import ValidationError
from attestor.core.money import PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.ledger.transactions import Move, Transaction


def val_err(
    message: str, code: str, timestamp: UtcDatetime, source: str,
) -> Err[ValidationError]:
    """Create Err[ValidationError] with empty fields tuple."""
    return Err(ValidationError(
        message=message, code=code,
        timestamp=timestamp, source=source, fields=(),
    ))


def parse_positive(
    value: Decimal,
    field_name: str,
    fn_name: str,
    timestamp: UtcDatetime,
    source: str,
) -> Ok[PositiveDecimal] | Err[ValidationError]:
    """Parse a Decimal as PositiveDecimal, wrapping errors as ValidationError."""
    match PositiveDecimal.parse(value):
        case Err(pe):
            return val_err(
                f"{fn_name}: {field_name} must be > 0: {pe}",
                "INVALID_QUANTITY", timestamp, source,
            )
        case Ok(pd):
            return Ok(pd)


def create_move(
    from_account: str,
    to_account: str,
    unit: str,
    quantity: PositiveDecimal,
    tx_id: str,
    fn_name: str,
    timestamp: UtcDatetime,
    source: str,
    *,
    label: str = "",
) -> Ok[Move] | Err[ValidationError]:
    """Create a Move, wrapping errors as ValidationError."""
    match Move.create(from_account, to_account, unit, quantity, tx_id):
        case Err(me):
            prefix = f"{fn_name}: {label}: " if label else f"{fn_name}: "
            return val_err(f"{prefix}{me}", "INVALID_MOVE", timestamp, source)
        case Ok(m):
            return Ok(m)


def create_tx(
    tx_id: str,
    moves: tuple[Move, ...],
    timestamp: UtcDatetime,
    fn_name: str,
    source: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a Transaction, wrapping errors as ValidationError."""
    match Transaction.create(tx_id, moves, timestamp):
        case Err(te):
            return val_err(
                f"{fn_name}: {te}", "INVALID_TRANSACTION", timestamp, source,
            )
        case Ok(tx):
            return Ok(tx)
