"""Swaption ledger functions -- premium, exercise into IRS, close, expiry.

All functions produce Transaction objects that the LedgerEngine executes.
The engine is never modified -- parametric polymorphism (Principle V).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext

from attestor.core.errors import ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder
from attestor.instrument.credit_types import SwaptionPayoutSpec
from attestor.instrument.derivative_types import SwaptionDetail
from attestor.instrument.types import Instrument, Party, create_irs_instrument
from attestor.ledger._validation import create_move, create_tx, parse_positive, val_err
from attestor.ledger.transactions import Transaction


def _swaption_detail_or_err(
    order: CanonicalOrder, fn_name: str,
) -> Ok[SwaptionDetail] | Err[ValidationError]:
    """Extract SwaptionDetail from order, or return Err."""
    if not isinstance(order.instrument_detail, SwaptionDetail):
        return val_err(
            f"{fn_name}: order.instrument_detail must be SwaptionDetail",
            "INVALID_INSTRUMENT_TYPE", order.timestamp,
            f"ledger.swaption.{fn_name}",
        )
    return Ok(order.instrument_detail)


def create_swaption_premium_transaction(
    order: CanonicalOrder,
    buyer_cash_account: str,
    seller_cash_account: str,
    buyer_position_account: str,
    seller_position_account: str,
    tx_id: str,
) -> Ok[Transaction] | Err[ValidationError]:
    """Book swaption premium payment + position opening.

    Premium = price * quantity (from order). No multiplier for swaptions.
    Move 1: Cash buyer -> seller (premium payment)
    Move 2: Swaption position seller -> buyer (position opened)
    """
    _fn = "create_swaption_premium_transaction"
    _src = f"ledger.swaption.{_fn}"

    match _swaption_detail_or_err(order, _fn):
        case Err(e):
            return Err(e)
        case Ok(detail):
            pass

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        premium = order.price * order.quantity.value

    contract_unit = (
        f"SWAPTION-{detail.swaption_type.name}-{detail.expiry_date.isoformat()}"
    )

    match PositiveDecimal.parse(premium):
        case Err(pe):
            return val_err(
                f"{_fn}: premium must be > 0: {pe}",
                "INVALID_PREMIUM", order.timestamp, _src,
            )
        case Ok(premium_pd):
            pass

    # Move 1: Cash premium buyer -> seller
    match create_move(
        buyer_cash_account, seller_cash_account,
        order.currency.value, premium_pd, tx_id,
        _fn, order.timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(cash_move):
            pass

    # Move 2: Swaption position seller -> buyer
    match create_move(
        seller_position_account, buyer_position_account,
        contract_unit, order.quantity, tx_id,
        _fn, order.timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(position_move):
            pass

    return create_tx(tx_id, (cash_move, position_move), order.timestamp, _fn, _src)


def exercise_swaption_into_irs(
    swaption_payout: SwaptionPayoutSpec,
    exercise_date: date,
    parties: tuple[Party, ...],
    irs_instrument_id: str,
) -> Ok[Instrument] | Err[str]:
    """Create the underlying IRS instrument from swaption terms.

    - fixed_rate = swaption strike
    - float_index, day_count, payment_frequency from underlying_swap
    - start_date = underlying_swap.start_date
    - end_date = underlying_swap.end_date
    - notional = swaption notional
    """
    underlying = swaption_payout.underlying_swap
    return create_irs_instrument(
        instrument_id=irs_instrument_id,
        fixed_rate=swaption_payout.strike.value,
        float_index=underlying.float_leg.float_index,
        day_count=underlying.fixed_leg.day_count,
        payment_frequency=underlying.fixed_leg.payment_frequency,
        notional=swaption_payout.notional.value,
        currency=swaption_payout.currency.value,
        start_date=underlying.start_date,
        end_date=underlying.end_date,
        parties=parties,
        trade_date=exercise_date,
        payer_receiver=underlying.fixed_leg.payer_receiver,
        spread=underlying.float_leg.spread,
    )


def create_swaption_exercise_close(
    holder_position_account: str,
    writer_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Close swaption position upon physical exercise.

    One Move: holder -> writer (return position). No cash.
    """
    _fn = "create_swaption_exercise_close"
    _src = f"ledger.swaption.{_fn}"

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    match create_move(
        holder_position_account, writer_position_account,
        contract_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(position_move):
            pass

    return create_tx(tx_id, (position_move,), timestamp, _fn, _src)


def create_swaption_cash_settlement(
    holder_cash_account: str,
    writer_cash_account: str,
    holder_position_account: str,
    writer_position_account: str,
    settlement_amount: Decimal,
    currency: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Cash-settled swaption exercise.

    Move 1: Cash writer -> holder (settlement payment)
    Move 2: Position holder -> writer (close position)
    """
    _fn = "create_swaption_cash_settlement"
    _src = f"ledger.swaption.{_fn}"

    match PositiveDecimal.parse(settlement_amount):
        case Err(pe):
            return val_err(
                f"{_fn}: settlement_amount must be > 0: {pe}",
                "INVALID_SETTLEMENT_AMOUNT", timestamp, _src,
            )
        case Ok(settle_pd):
            pass

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    # Move 1: Cash writer -> holder
    match create_move(
        writer_cash_account, holder_cash_account,
        currency, settle_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(cash_move):
            pass

    # Move 2: Position holder -> writer
    match create_move(
        holder_position_account, writer_position_account,
        contract_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(position_move):
            pass

    return create_tx(tx_id, (cash_move, position_move), timestamp, _fn, _src)


def create_swaption_expiry_close(
    holder_position_account: str,
    writer_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Expire unexercised swaption. Close position, no cash.

    One Move: holder -> writer (return position).
    """
    _fn = "create_swaption_expiry_close"
    _src = f"ledger.swaption.{_fn}"

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    match create_move(
        holder_position_account, writer_position_account,
        contract_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(position_move):
            pass

    return create_tx(tx_id, (position_move,), timestamp, _fn, _src)
