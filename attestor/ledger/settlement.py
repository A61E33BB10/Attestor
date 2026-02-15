"""Settlement transaction creation — T+2 cash equity settlement.

Creates a Transaction with 2 Moves (4 balance changes):
  Move 1: Cash from buyer_cash → seller_cash (price * quantity)
  Move 2: Securities from seller_securities → buyer_securities (quantity)

Conservation holds because each Move adds to destination exactly what it removes
from source.
"""

from __future__ import annotations

from decimal import localcontext
from typing import TYPE_CHECKING

from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.ledger.transactions import Move, Transaction

if TYPE_CHECKING:
    from attestor.gateway.types import CanonicalOrder


def create_settlement_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    buyer_securities_account: str,
    seller_cash_account: str,
    seller_securities_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a T+2 settlement transaction with 2 balanced Moves.

    Move 1: Cash from buyer_cash → seller_cash (price * quantity)
    Move 2: Securities from seller_securities → buyer_securities (quantity)

    INV-L04: cash_transferred + securities_transferred = 0 (net per settlement).
    """
    violations: list[FieldViolation] = []
    if not buyer_cash_account:
        violations.append(FieldViolation(
            path="buyer_cash_account", constraint="must be non-empty", actual_value="",
        ))
    if not buyer_securities_account:
        violations.append(FieldViolation(
            path="buyer_securities_account", constraint="must be non-empty", actual_value="",
        ))
    if not seller_cash_account:
        violations.append(FieldViolation(
            path="seller_cash_account", constraint="must be non-empty", actual_value="",
        ))
    if not seller_securities_account:
        violations.append(FieldViolation(
            path="seller_securities_account", constraint="must be non-empty", actual_value="",
        ))
    if not tx_id:
        violations.append(FieldViolation(
            path="tx_id", constraint="must be non-empty", actual_value="",
        ))
    if violations:
        return Err(ValidationError(
            message="Settlement validation failed",
            code="SETTLEMENT_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.settlement.create_settlement_transaction",
            fields=tuple(violations),
        ))

    # Compute cash amount = price * quantity under ATTESTOR_DECIMAL_CONTEXT
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        cash_amount = order.price * order.quantity.value

    match PositiveDecimal.parse(cash_amount):
        case Err(_):
            return Err(ValidationError(
                message=f"Cash amount must be positive, got {cash_amount}",
                code="SETTLEMENT_VALIDATION",
                timestamp=UtcDatetime.now(),
                source="ledger.settlement.create_settlement_transaction",
                fields=(FieldViolation(
                    path="cash_amount", constraint="must be > 0",
                    actual_value=str(cash_amount),
                ),),
            ))
        case Ok(cash_qty):
            pass

    contract_id = order.order_id.value
    instrument_id = order.instrument_id.value
    currency = order.currency.value

    moves = (
        Move(
            source=buyer_cash_account,
            destination=seller_cash_account,
            unit=currency,
            quantity=cash_qty,
            contract_id=contract_id,
        ),
        Move(
            source=seller_securities_account,
            destination=buyer_securities_account,
            unit=instrument_id,
            quantity=order.quantity,
            contract_id=contract_id,
        ),
    )

    return Ok(Transaction(
        tx_id=tx_id,
        moves=moves,
        timestamp=order.timestamp,
    ))
