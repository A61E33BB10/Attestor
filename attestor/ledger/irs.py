"""IRS cashflow scheduling and transaction creation.

Generates fixed/float leg schedules, applies rate fixings, and creates
transactions for cashflow exchanges. Conservation: sigma(currency) unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import final

from dateutil.relativedelta import relativedelta

from attestor.core.calendar import day_count_fraction
from attestor.core.errors import FieldViolation, ValidationError
from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, NonEmptyStr, PositiveDecimal
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.instrument.fx_types import (
    DayCountConvention,
    PaymentFrequency,
    SwapLegType,
)
from attestor.ledger.transactions import Move, Transaction


def _frequency_months(freq: PaymentFrequency) -> int:
    match freq:
        case PaymentFrequency.MONTHLY:
            return 1
        case PaymentFrequency.QUARTERLY:
            return 3
        case PaymentFrequency.SEMI_ANNUAL:
            return 6
        case PaymentFrequency.ANNUAL:
            return 12


def _generate_period_dates(
    start: date, end: date, freq: PaymentFrequency,
) -> list[tuple[date, date]]:
    """Generate (period_start, period_end) pairs."""
    months = _frequency_months(freq)
    periods: list[tuple[date, date]] = []
    current = start
    while current < end:
        next_date = current + relativedelta(months=months)
        period_end = min(next_date, end)
        periods.append((current, period_end))
        current = next_date
    return periods


@final
@dataclass(frozen=True, slots=True)
class ScheduledCashflow:
    """A single scheduled cashflow."""

    payment_date: date
    amount: Decimal  # positive = receive, negative = pay; 0 if unfixed
    currency: NonEmptyStr
    leg_type: SwapLegType
    period_start: date
    period_end: date
    day_count_fraction: Decimal


@final
@dataclass(frozen=True, slots=True)
class CashflowSchedule:
    """Scheduled cashflows for one leg of an IRS."""

    cashflows: tuple[ScheduledCashflow, ...]


def generate_fixed_leg_schedule(
    notional: Decimal,
    fixed_rate: Decimal,
    start_date: date,
    end_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[CashflowSchedule] | Err[str]:
    """Generate fixed leg cashflow schedule."""
    if start_date >= end_date:
        return Err(f"start_date ({start_date}) must be < end_date ({end_date})")
    if notional <= 0:
        return Err(f"notional must be > 0, got {notional}")
    match NonEmptyStr.parse(currency):
        case Err(e):
            return Err(f"currency: {e}")
        case Ok(cur):
            pass

    periods = _generate_period_dates(start_date, end_date, payment_frequency)
    cashflows: list[ScheduledCashflow] = []
    for p_start, p_end in periods:
        dcf = day_count_fraction(p_start, p_end, day_count)
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            amount = notional * fixed_rate * dcf
        cashflows.append(ScheduledCashflow(
            payment_date=p_end,
            amount=amount,
            currency=cur,
            leg_type=SwapLegType.FIXED,
            period_start=p_start,
            period_end=p_end,
            day_count_fraction=dcf,
        ))

    return Ok(CashflowSchedule(cashflows=tuple(cashflows)))


def generate_float_leg_schedule(
    notional: Decimal,
    start_date: date,
    end_date: date,
    day_count: DayCountConvention,
    payment_frequency: PaymentFrequency,
    currency: str,
) -> Ok[CashflowSchedule] | Err[str]:
    """Generate float leg schedule (amounts initially zero until fixing)."""
    if start_date >= end_date:
        return Err(f"start_date ({start_date}) must be < end_date ({end_date})")
    if notional <= 0:
        return Err(f"notional must be > 0, got {notional}")
    match NonEmptyStr.parse(currency):
        case Err(e):
            return Err(f"currency: {e}")
        case Ok(cur):
            pass

    periods = _generate_period_dates(start_date, end_date, payment_frequency)
    cashflows: list[ScheduledCashflow] = []
    for p_start, p_end in periods:
        dcf = day_count_fraction(p_start, p_end, day_count)
        cashflows.append(ScheduledCashflow(
            payment_date=p_end,
            amount=Decimal("0"),
            currency=cur,
            leg_type=SwapLegType.FLOAT,
            period_start=p_start,
            period_end=p_end,
            day_count_fraction=dcf,
        ))

    return Ok(CashflowSchedule(cashflows=tuple(cashflows)))


def apply_rate_fixing(
    schedule: CashflowSchedule,
    notional: Decimal,
    fixing_rate: Decimal,
    fixing_date: date,
) -> Ok[CashflowSchedule] | Err[str]:
    """Apply a rate fixing to float leg, computing cashflow amounts.

    Updates the first unfixed period whose period_start <= fixing_date < period_end.
    """
    updated: list[ScheduledCashflow] = []
    fixed_one = False
    for cf in schedule.cashflows:
        if (
            not fixed_one
            and cf.amount == Decimal("0")
            and cf.period_start <= fixing_date < cf.period_end
        ):
            with localcontext(ATTESTOR_DECIMAL_CONTEXT):
                amount = notional * fixing_rate * cf.day_count_fraction
            updated.append(ScheduledCashflow(
                payment_date=cf.payment_date,
                amount=amount,
                currency=cf.currency,
                leg_type=cf.leg_type,
                period_start=cf.period_start,
                period_end=cf.period_end,
                day_count_fraction=cf.day_count_fraction,
            ))
            fixed_one = True
        else:
            updated.append(cf)

    if not fixed_one:
        return Err(f"No unfixed period found for fixing_date={fixing_date}")

    return Ok(CashflowSchedule(cashflows=tuple(updated)))


def create_irs_cashflow_transaction(
    instrument_id: str,
    payer_account: str,
    receiver_account: str,
    cashflow: ScheduledCashflow,
    tx_id: str,
    timestamp: UtcDatetime,
) -> Ok[Transaction] | Err[ValidationError]:
    """Create a transaction for a single IRS cashflow exchange.

    Move: cash from payer -> receiver.
    Conservation: sigma(currency) unchanged.
    """
    violations: list[FieldViolation] = []
    if not instrument_id:
        violations.append(FieldViolation(
            path="instrument_id", constraint="must be non-empty", actual_value="",
        ))
    if not payer_account:
        violations.append(FieldViolation(
            path="payer_account", constraint="must be non-empty", actual_value="",
        ))
    if not receiver_account:
        violations.append(FieldViolation(
            path="receiver_account", constraint="must be non-empty", actual_value="",
        ))
    if not tx_id:
        violations.append(FieldViolation(
            path="tx_id", constraint="must be non-empty", actual_value="",
        ))
    if violations:
        return Err(ValidationError(
            message="IRS cashflow validation failed",
            code="IRS_CASHFLOW_VALIDATION",
            timestamp=UtcDatetime.now(),
            source="ledger.irs.create_irs_cashflow_transaction",
            fields=tuple(violations),
        ))

    abs_amount = abs(cashflow.amount)
    match PositiveDecimal.parse(abs_amount):
        case Err(_):
            return Err(ValidationError(
                message=f"Cashflow amount must be non-zero, got {cashflow.amount}",
                code="IRS_CASHFLOW_VALIDATION",
                timestamp=UtcDatetime.now(),
                source="ledger.irs.create_irs_cashflow_transaction",
                fields=(FieldViolation(
                    path="amount", constraint="must be non-zero",
                    actual_value=str(cashflow.amount),
                ),),
            ))
        case Ok(qty):
            pass

    # Positive amount = receiver gets; negative = payer gets
    if cashflow.amount > 0:
        src, dst = payer_account, receiver_account
    else:
        src, dst = receiver_account, payer_account

    move = Move(
        source=src, destination=dst,
        unit=cashflow.currency.value,
        quantity=qty,
        contract_id=instrument_id,
    )
    return Ok(Transaction(tx_id=tx_id, moves=(move,), timestamp=timestamp))
