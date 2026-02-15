"""Futures ledger functions — position open, variation margin, expiry.

All functions produce Transaction objects that the LedgerEngine executes.
The engine is never modified — parametric polymorphism (Principle V).
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from attestor.core.errors import ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.ledger.transactions import Move, Transaction


def create_futures_open_transaction(
    instrument_id: str,
    long_position_account: str,
    short_position_account: str,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Open futures position at trade time.

    Move: position (qty) short -> long. No cash exchange.
    """
    match PositiveDecimal.parse(quantity):
        case Err(pe):
            return Err(ValidationError(
                message=f"create_futures_open_transaction: {pe}",
                code="INVALID_QUANTITY",
                timestamp=timestamp,
                source="ledger.futures.create_futures_open_transaction",
                fields=(),
            ))
        case Ok(qty_pd):
            pass

    match Move.create(
        short_position_account, long_position_account,
        contract_unit, qty_pd, tx_id,
    ):
        case Err(me):
            return Err(ValidationError(
                message=f"create_futures_open_transaction: {me}",
                code="INVALID_MOVE",
                timestamp=timestamp,
                source="ledger.futures.create_futures_open_transaction",
                fields=(),
            ))
        case Ok(position_move):
            pass

    match Transaction.create(tx_id, (position_move,), timestamp):
        case Err(te):
            return Err(ValidationError(
                message=f"create_futures_open_transaction: {te}",
                code="INVALID_TRANSACTION",
                timestamp=timestamp,
                source="ledger.futures.create_futures_open_transaction",
                fields=(),
            ))
        case Ok(tx):
            return Ok(tx)


def create_variation_margin_transaction(
    instrument_id: str,
    long_margin_account: str,
    short_margin_account: str,
    settlement_price: Decimal,
    previous_settlement_price: Decimal,
    contract_size: Decimal,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[str]:
    """Daily variation margin settlement.

    margin_flow = (settlement - prev_settlement) * contract_size * qty
    Positive: short pays long. Negative: long pays short.
    Zero flow returns Err (Formalis C-03).
    """
    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        margin_flow = (
            (settlement_price - previous_settlement_price)
            * contract_size * quantity
        )

    if margin_flow == Decimal(0):
        return Err("No margin flow: prices unchanged")

    if margin_flow > 0:
        source, destination = short_margin_account, long_margin_account
    else:
        source, destination = long_margin_account, short_margin_account
        margin_flow = -margin_flow  # make positive for Move

    match PositiveDecimal.parse(margin_flow):
        case Err(pe):
            return Err(f"create_variation_margin_transaction: {pe}")
        case Ok(flow_pd):
            pass

    match Move.create(source, destination, "USD", flow_pd, tx_id):
        case Err(me):
            return Err(f"create_variation_margin_transaction: {me}")
        case Ok(margin_move):
            pass

    match Transaction.create(tx_id, (margin_move,), timestamp):
        case Err(te):
            return Err(f"create_variation_margin_transaction: {te}")
        case Ok(tx):
            return Ok(tx)


def create_futures_expiry_transaction(
    instrument_id: str,
    long_cash_account: str,
    short_cash_account: str,
    long_position_account: str,
    short_position_account: str,
    final_settlement_price: Decimal,
    last_margin_price: Decimal,
    contract_size: Decimal,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Futures expiry: final margin settlement + close position.

    Move 1: Final margin (if non-zero)
    Move 2: Position close (long -> short)
    """
    match PositiveDecimal.parse(quantity):
        case Err(pe):
            return Err(ValidationError(
                message=f"create_futures_expiry_transaction: {pe}",
                code="INVALID_QUANTITY",
                timestamp=timestamp,
                source="ledger.futures.create_futures_expiry_transaction",
                fields=(),
            ))
        case Ok(qty_pd):
            pass

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        final_margin = (
            (final_settlement_price - last_margin_price)
            * contract_size * quantity
        )

    moves: list[Move] = []

    # Final margin move (if non-zero)
    if final_margin != Decimal(0):
        if final_margin > 0:
            src, dst = short_cash_account, long_cash_account
        else:
            src, dst = long_cash_account, short_cash_account
            final_margin = -final_margin
        margin_pd = PositiveDecimal(value=final_margin)
        moves.append(Move(src, dst, "USD", margin_pd, tx_id))

    # Position close: long -> short
    moves.append(Move(
        long_position_account, short_position_account,
        contract_unit, qty_pd, tx_id,
    ))

    match Transaction.create(tx_id, tuple(moves), timestamp):
        case Err(te):
            return Err(ValidationError(
                message=f"create_futures_expiry_transaction: {te}",
                code="INVALID_TRANSACTION",
                timestamp=timestamp,
                source="ledger.futures.create_futures_expiry_transaction",
                fields=(),
            ))
        case Ok(tx):
            return Ok(tx)
