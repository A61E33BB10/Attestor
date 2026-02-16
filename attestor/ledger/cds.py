"""CDS ledger functions -- premium leg, credit event settlement, maturity close.

All functions produce Transaction objects that the LedgerEngine executes.
Conservation: sigma(currency) unchanged after every transaction.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import assert_never, final

from dateutil.relativedelta import relativedelta

from attestor.core.calendar import day_count_fraction
from attestor.core.errors import ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.instrument.fx_types import DayCountConvention, PaymentFrequency
from attestor.ledger._validation import create_move, create_tx, parse_positive, val_err
from attestor.ledger.transactions import Move, Transaction

# ---------------------------------------------------------------------------
# Helpers (shared with irs.py pattern)
# ---------------------------------------------------------------------------


def _frequency_months(freq: PaymentFrequency) -> int:
    """Map PaymentFrequency to number of months per period (exhaustive)."""
    match freq:
        case PaymentFrequency.MONTHLY:
            return 1
        case PaymentFrequency.QUARTERLY:
            return 3
        case PaymentFrequency.SEMI_ANNUAL:
            return 6
        case PaymentFrequency.ANNUAL:
            return 12
        case _never:
            assert_never(_never)


def _generate_period_dates(
    start: date, end: date, freq: PaymentFrequency,
) -> list[tuple[date, date]]:
    """Generate (period_start, period_end) pairs for a date range."""
    months = _frequency_months(freq)
    periods: list[tuple[date, date]] = []
    current = start
    while current < end:
        next_date = current + relativedelta(months=months)
        period_end = min(next_date, end)
        periods.append((current, period_end))
        current = next_date
    return periods


# ---------------------------------------------------------------------------
# ScheduledCDSPremium
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ScheduledCDSPremium:
    """A single scheduled CDS premium payment."""

    payment_date: date
    amount: Decimal
    currency: NonEmptyStr
    period_start: date
    period_end: date
    day_count_fraction: Decimal


# ---------------------------------------------------------------------------
# Premium schedule generation
# ---------------------------------------------------------------------------


def generate_cds_premium_schedule(
    notional: Decimal,
    spread: Decimal,
    effective_date: date,
    maturity_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[tuple[ScheduledCDSPremium, ...]] | Err[str]:
    """Generate periodic CDS premium payments.

    For each period:
        day_count_fraction = day_count_fraction(period_start, period_end, convention)
        amount = notional * spread * dcf
    """
    if effective_date >= maturity_date:
        return Err(
            f"effective_date ({effective_date}) must be < maturity_date ({maturity_date})"
        )
    if notional <= 0:
        return Err(f"notional must be > 0, got {notional}")
    if spread <= 0:
        return Err(f"spread must be > 0, got {spread}")
    match NonEmptyStr.parse(currency):
        case Err(e):
            return Err(f"currency: {e}")
        case Ok(cur):
            pass

    periods = _generate_period_dates(effective_date, maturity_date, payment_frequency)
    premiums: list[ScheduledCDSPremium] = []
    for p_start, p_end in periods:
        dcf = day_count_fraction(p_start, p_end, day_count)
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            amount = notional * spread * dcf
        premiums.append(ScheduledCDSPremium(
            payment_date=p_end,
            amount=amount,
            currency=cur,
            period_start=p_start,
            period_end=p_end,
            day_count_fraction=dcf,
        ))

    return Ok(tuple(premiums))


# ---------------------------------------------------------------------------
# Premium transaction
# ---------------------------------------------------------------------------


def create_cds_premium_transaction(
    buyer_account: str,
    seller_account: str,
    premium: ScheduledCDSPremium,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a transaction for a single CDS premium payment.

    One Move: buyer_account -> seller_account, unit = premium.currency,
    quantity = premium.amount.
    Conservation: sigma(currency) unchanged.
    """
    _fn = "create_cds_premium_transaction"
    _src = f"ledger.cds.{_fn}"

    match PositiveDecimal.parse(premium.amount):
        case Err(pe):
            return val_err(
                f"{_fn}: premium amount must be > 0: {pe}",
                "INVALID_PREMIUM_AMOUNT", timestamp, _src,
            )
        case Ok(amount_pd):
            pass

    match create_move(
        buyer_account, seller_account,
        premium.currency.value, amount_pd, tx_id,
        _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(cash_move):
            pass

    return create_tx(tx_id, (cash_move,), timestamp, _fn, _src)


# ---------------------------------------------------------------------------
# CDS trade transaction (position opening at inception)
# ---------------------------------------------------------------------------


def create_cds_trade_transaction(
    buyer_position_account: str,
    seller_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Open a CDS position at inception.

    One Move: seller_position_account -> buyer_position_account.
    sigma(contract_unit) == 0.
    """
    _fn = "create_cds_trade_transaction"
    _src = f"ledger.cds.{_fn}"

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    match create_move(
        seller_position_account, buyer_position_account,
        contract_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(position_move):
            pass

    return create_tx(tx_id, (position_move,), timestamp, _fn, _src)


# ---------------------------------------------------------------------------
# Credit event settlement
# ---------------------------------------------------------------------------


def create_cds_credit_event_settlement(
    buyer_account: str,
    seller_account: str,
    notional: Decimal,
    auction_price: Decimal,
    currency: str,
    tx_id: str,
    timestamp: UtcDatetime,
    *,
    accrued_premium: Decimal | None = None,
    buyer_position_account: str | None = None,
    seller_position_account: str | None = None,
    contract_unit: str | None = None,
    position_quantity: Decimal | None = None,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a credit event settlement transaction.

    Protection payment = notional * (1 - auction_price).

    Moves (atomic, single Transaction):
      1. Protection payment: seller -> buyer (cash)
      2. Accrued premium: buyer -> seller (cash) -- if accrued_premium > 0
      3. Position close: buyer_position -> seller_position -- if position params provided

    Conservation: sigma(currency) unchanged, sigma(contract_unit) unchanged.

    Validations:
    - 0 <= auction_price <= 1
    - auction_price == 1 (100% recovery) -> Err (zero protection payment)
    - If any position param is set, all must be set
    """
    _fn = "create_cds_credit_event_settlement"
    _src = f"ledger.cds.{_fn}"

    if auction_price < 0:
        return val_err(
            f"auction_price must be >= 0, got {auction_price}",
            "INVALID_AUCTION_PRICE", timestamp, _src,
        )
    if auction_price > 1:
        return val_err(
            f"auction_price must be <= 1, got {auction_price}",
            "INVALID_AUCTION_PRICE", timestamp, _src,
        )

    with localcontext(ATTESTOR_DECIMAL_CONTEXT):
        protection_payment = notional * (Decimal("1") - auction_price)

    if protection_payment == 0:
        return val_err(
            "no protection payment at 100% recovery",
            "ZERO_PROTECTION_PAYMENT", timestamp, _src,
        )

    # Validate position params: all-or-nothing
    pos_params = (
        buyer_position_account, seller_position_account,
        contract_unit, position_quantity,
    )
    pos_count = sum(1 for p in pos_params if p is not None)
    if pos_count not in (0, 4):
        return val_err(
            f"{_fn}: position close requires all 4 params "
            "(buyer_position_account, seller_position_account, "
            "contract_unit, position_quantity)",
            "INCOMPLETE_POSITION_PARAMS", timestamp, _src,
        )

    # Move 1: Protection payment (seller -> buyer)
    match PositiveDecimal.parse(protection_payment):
        case Err(pe):
            return val_err(
                f"{_fn}: protection payment must be > 0: {pe}",
                "INVALID_PROTECTION_PAYMENT", timestamp, _src,
            )
        case Ok(payment_pd):
            pass

    match create_move(
        seller_account, buyer_account,
        currency, payment_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(protection_move):
            pass

    moves: list[Move] = [protection_move]

    # Move 2: Accrued premium (buyer -> seller) -- optional
    if accrued_premium is not None and accrued_premium > 0:
        match PositiveDecimal.parse(accrued_premium):
            case Err(pe2):
                return val_err(
                    f"{_fn}: accrued premium: {pe2}",
                    "INVALID_ACCRUED_PREMIUM", timestamp, _src,
                )
            case Ok(accrued_pd):
                pass

        match create_move(
            buyer_account, seller_account,
            currency, accrued_pd, tx_id,
            _fn, timestamp, _src, label="accrued move",
        ):
            case Err(e):
                return Err(e)
            case Ok(accrued_move):
                moves.append(accrued_move)

    # Move 3: Position close (buyer_position -> seller_position) -- optional
    if pos_count == 4:
        assert buyer_position_account is not None
        assert seller_position_account is not None
        assert contract_unit is not None
        assert position_quantity is not None

        match parse_positive(position_quantity, "position_quantity", _fn, timestamp, _src):
            case Err(e):
                return Err(e)
            case Ok(pos_qty_pd):
                pass

        match create_move(
            buyer_position_account, seller_position_account,
            contract_unit, pos_qty_pd, tx_id,
            _fn, timestamp, _src, label="position move",
        ):
            case Err(e):
                return Err(e)
            case Ok(position_move):
                moves.append(position_move)

    return create_tx(tx_id, tuple(moves), timestamp, _fn, _src)


# ---------------------------------------------------------------------------
# Maturity close
# ---------------------------------------------------------------------------


def create_cds_maturity_close(
    buyer_position_account: str,
    seller_position_account: str,
    contract_unit: str,
    quantity: Decimal,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Close a CDS position at maturity.

    One Move: buyer_position_account -> seller_position_account.
    sigma(contract_unit) returns to 0.
    """
    _fn = "create_cds_maturity_close"
    _src = f"ledger.cds.{_fn}"

    match parse_positive(quantity, "quantity", _fn, timestamp, _src):
        case Err(e):
            return Err(e)
        case Ok(qty_pd):
            pass

    match create_move(
        buyer_position_account, seller_position_account,
        contract_unit, qty_pd, tx_id, _fn, timestamp, _src,
    ):
        case Err(e):
            return Err(e)
        case Ok(position_move):
            pass

    return create_tx(tx_id, (position_move,), timestamp, _fn, _src)
