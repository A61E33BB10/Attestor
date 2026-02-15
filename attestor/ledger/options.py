"""Option ledger functions — premium, exercise, expiry.

All functions produce Transaction objects that the LedgerEngine executes.
The engine is never modified — parametric polymorphism (Principle V).
"""

from __future__ import annotations

from decimal import Decimal, localcontext

from attestor.core.errors import ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.derivative_types import OptionDetail, OptionType, SettlementType
from attestor.ledger.transactions import Move, Transaction


def _option_detail_or_err(
    order: CanonicalOrder, fn_name: str,
) -> Ok[OptionDetail] | Err[ValidationError]:
    """Extract OptionDetail from order, or return Err."""
    if not isinstance(order.instrument_detail, OptionDetail):
        return Err(ValidationError(
            message=f"{fn_name}: order.instrument_detail must be OptionDetail",
            code="INVALID_INSTRUMENT_TYPE",
            timestamp=order.timestamp,
            source=f"ledger.options.{fn_name}",
            fields=(),
        ))
    return Ok(order.instrument_detail)


def create_premium_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,
    seller_position_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Option trade: premium payment AND position opening.

    Premium = price * quantity * multiplier
    Move 1: Cash (premium) buyer -> seller
    Move 2: Option position (qty) seller -> buyer
    """
    match _option_detail_or_err(order, "create_premium_transaction"):
        case Err(e):
            return Err(e)
        case Ok(detail):
            pass

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        premium = order.price * order.quantity.value * detail.multiplier.value

    contract_unit = (
        f"OPT-{detail.underlying_id.value}-{detail.option_type.value}"
        f"-{detail.strike.value}-{detail.expiry_date.isoformat()}"
    )

    match PositiveDecimal.parse(premium):
        case Err(pe):
            return Err(ValidationError(
                message=f"create_premium_transaction: premium must be > 0: {pe}",
                code="INVALID_PREMIUM",
                timestamp=order.timestamp,
                source="ledger.options.create_premium_transaction",
                fields=(),
            ))
        case Ok(premium_pd):
            pass

    # Move 1: Cash premium buyer -> seller
    match Move.create(buyer_cash_account, seller_cash_account,
                      order.currency.value, premium_pd, tx_id):
        case Err(me):
            return Err(ValidationError(
                message=f"create_premium_transaction: {me}",
                code="INVALID_MOVE",
                timestamp=order.timestamp,
                source="ledger.options.create_premium_transaction",
                fields=(),
            ))
        case Ok(cash_move):
            pass

    # Move 2: Option position seller -> buyer
    match Move.create(seller_position_account, buyer_position_account,
                      contract_unit, order.quantity, tx_id):
        case Err(me2):
            return Err(ValidationError(
                message=f"create_premium_transaction: {me2}",
                code="INVALID_MOVE",
                timestamp=order.timestamp,
                source="ledger.options.create_premium_transaction",
                fields=(),
            ))
        case Ok(position_move):
            pass

    match Transaction.create(tx_id, (cash_move, position_move), order.timestamp):
        case Err(te):
            return Err(ValidationError(
                message=f"create_premium_transaction: {te}",
                code="INVALID_TRANSACTION",
                timestamp=order.timestamp,
                source="ledger.options.create_premium_transaction",
                fields=(),
            ))
        case Ok(tx):
            return Ok(tx)


def create_exercise_transaction(
    order: CanonicalOrder,
    holder_cash_account: str,
    holder_securities_account: str,
    writer_cash_account: str,
    writer_securities_account: str,
    holder_position_account: str,
    writer_position_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Physical exercise: close option position + deliver underlying.

    CALL: holder pays strike*qty*multiplier cash, receives securities
    PUT: holder delivers securities, receives strike*qty*multiplier cash
    Both: option position (qty) holder -> writer (close position)
    """
    match _option_detail_or_err(order, "create_exercise_transaction"):
        case Err(e):
            return Err(e)
        case Ok(detail):
            pass

    if detail.settlement_type != SettlementType.PHYSICAL:
        return Err(ValidationError(
            message="create_exercise_transaction: settlement_type must be PHYSICAL",
            code="INVALID_SETTLEMENT_TYPE",
            timestamp=order.timestamp,
            source="ledger.options.create_exercise_transaction",
            fields=(),
        ))

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        cash_amount = detail.strike.value * order.quantity.value * detail.multiplier.value
        securities_qty = order.quantity.value * detail.multiplier.value

    contract_unit = (
        f"OPT-{detail.underlying_id.value}-{detail.option_type.value}"
        f"-{detail.strike.value}-{detail.expiry_date.isoformat()}"
    )

    cash_pd = PositiveDecimal(value=cash_amount)
    sec_pd = PositiveDecimal(value=securities_qty)

    moves: list[Move] = []
    if detail.option_type == OptionType.CALL:
        # Holder pays cash, receives securities
        moves.append(Move(holder_cash_account, writer_cash_account,
                          order.currency.value, cash_pd, tx_id))
        moves.append(Move(writer_securities_account, holder_securities_account,
                          detail.underlying_id.value, sec_pd, tx_id))
    else:
        # PUT: Holder delivers securities, receives cash
        moves.append(Move(holder_securities_account, writer_securities_account,
                          detail.underlying_id.value, sec_pd, tx_id))
        moves.append(Move(writer_cash_account, holder_cash_account,
                          order.currency.value, cash_pd, tx_id))

    # Close option position: holder -> writer
    moves.append(Move(holder_position_account, writer_position_account,
                       contract_unit, order.quantity, tx_id))

    match Transaction.create(tx_id, tuple(moves), order.timestamp):
        case Err(te):
            return Err(ValidationError(
                message=f"create_exercise_transaction: {te}",
                code="INVALID_TRANSACTION",
                timestamp=order.timestamp,
                source="ledger.options.create_exercise_transaction",
                fields=(),
            ))
        case Ok(tx):
            return Ok(tx)


def create_cash_settlement_exercise_transaction(
    order: CanonicalOrder,
    holder_cash_account: str,
    writer_cash_account: str,
    holder_position_account: str,
    writer_position_account: str,
    tx_id: str,
    settlement_price: Decimal,
) -> Ok[Transaction] | Err[ValidationError]:
    """Cash-settled exercise.

    CALL: writer pays (settlement_price - strike) * qty * multiplier to holder
    PUT: writer pays (strike - settlement_price) * qty * multiplier to holder
    + close option position (holder -> writer)
    OTM exercise is rejected.
    """
    match _option_detail_or_err(order, "create_cash_settlement_exercise_transaction"):
        case Err(e):
            return Err(e)
        case Ok(detail):
            pass

    if detail.settlement_type != SettlementType.CASH:
        return Err(ValidationError(
            message="create_cash_settlement_exercise_transaction: settlement_type must be CASH",
            code="INVALID_SETTLEMENT_TYPE",
            timestamp=order.timestamp,
            source="ledger.options.create_cash_settlement_exercise_transaction",
            fields=(),
        ))

    # OTM rejection
    if detail.option_type == OptionType.CALL and settlement_price <= detail.strike.value:
        return Err(ValidationError(
            message=(
                f"CALL exercise rejected: settlement_price ({settlement_price}) "
                f"<= strike ({detail.strike.value})"
            ),
            code="OTM_EXERCISE",
            timestamp=order.timestamp,
            source="ledger.options.create_cash_settlement_exercise_transaction",
            fields=(),
        ))
    if detail.option_type == OptionType.PUT and settlement_price >= detail.strike.value:
        return Err(ValidationError(
            message=(
                f"PUT exercise rejected: settlement_price ({settlement_price}) "
                f">= strike ({detail.strike.value})"
            ),
            code="OTM_EXERCISE",
            timestamp=order.timestamp,
            source="ledger.options.create_cash_settlement_exercise_transaction",
            fields=(),
        ))

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        qty_mul = order.quantity.value * detail.multiplier.value
        if detail.option_type == OptionType.CALL:
            intrinsic = (settlement_price - detail.strike.value) * qty_mul
        else:
            intrinsic = (detail.strike.value - settlement_price) * qty_mul

    contract_unit = (
        f"OPT-{detail.underlying_id.value}-{detail.option_type.value}"
        f"-{detail.strike.value}-{detail.expiry_date.isoformat()}"
    )

    intrinsic_pd = PositiveDecimal(value=intrinsic)

    # Cash: writer -> holder
    cash_move = Move(writer_cash_account, holder_cash_account,
                     order.currency.value, intrinsic_pd, tx_id)
    # Close position: holder -> writer
    position_move = Move(holder_position_account, writer_position_account,
                         contract_unit, order.quantity, tx_id)

    match Transaction.create(tx_id, (cash_move, position_move), order.timestamp):
        case Err(te):
            return Err(ValidationError(
                message=f"create_cash_settlement_exercise_transaction: {te}",
                code="INVALID_TRANSACTION",
                timestamp=order.timestamp,
                source="ledger.options.create_cash_settlement_exercise_transaction",
                fields=(),
            ))
        case Ok(tx):
            return Ok(tx)


def create_expiry_transaction(
    instrument_id: str,
    holder_position_account: str,
    writer_position_account: str,
    quantity: Decimal,
    contract_unit: str,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """OTM expiry: close derivative position, no cash movement.

    Move: option position (qty) holder -> writer (close position)
    sigma(contract_unit) returns to 0.
    """
    match PositiveDecimal.parse(quantity):
        case Err(pe):
            return Err(ValidationError(
                message=f"create_expiry_transaction: quantity must be > 0: {pe}",
                code="INVALID_QUANTITY",
                timestamp=timestamp,
                source="ledger.options.create_expiry_transaction",
                fields=(),
            ))
        case Ok(qty_pd):
            pass

    match Move.create(holder_position_account, writer_position_account,
                      contract_unit, qty_pd, tx_id):
        case Err(me):
            return Err(ValidationError(
                message=f"create_expiry_transaction: {me}",
                code="INVALID_MOVE",
                timestamp=timestamp,
                source="ledger.options.create_expiry_transaction",
                fields=(),
            ))
        case Ok(position_move):
            pass

    match Transaction.create(tx_id, (position_move,), timestamp):
        case Err(te):
            return Err(ValidationError(
                message=f"create_expiry_transaction: {te}",
                code="INVALID_TRANSACTION",
                timestamp=timestamp,
                source="ledger.options.create_expiry_transaction",
                fields=(),
            ))
        case Ok(tx):
            return Ok(tx)
