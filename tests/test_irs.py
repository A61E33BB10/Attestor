"""Tests for attestor.ledger.irs — IRS cashflow scheduling and transactions."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from attestor.core.calendar import day_count_fraction
from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, unwrap
from attestor.core.types import UtcDatetime
from attestor.instrument.fx_types import DayCountConvention, PaymentFrequency, SwapLegType
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.irs import (
    ScheduledCashflow,
    apply_rate_fixing,
    create_irs_cashflow_transaction,
    generate_fixed_leg_schedule,
    generate_float_leg_schedule,
)

# ---------------------------------------------------------------------------
# day_count_fraction
# ---------------------------------------------------------------------------


class TestDayCountFraction:
    def test_act_360(self) -> None:
        dcf = day_count_fraction(
            date(2025, 1, 1), date(2025, 4, 1), DayCountConvention.ACT_360,
        )
        assert dcf == Decimal("90") / Decimal("360")

    def test_act_365(self) -> None:
        dcf = day_count_fraction(
            date(2025, 1, 1), date(2025, 4, 1), DayCountConvention.ACT_365,
        )
        assert dcf == Decimal("90") / Decimal("365")

    def test_thirty_360(self) -> None:
        dcf = day_count_fraction(
            date(2025, 1, 15), date(2025, 4, 15), DayCountConvention.THIRTY_360,
        )
        assert dcf == Decimal("90") / Decimal("360")


# ---------------------------------------------------------------------------
# Fixed leg schedule
# ---------------------------------------------------------------------------


class TestFixedLegSchedule:
    def test_quarterly_periods(self) -> None:
        sched = unwrap(generate_fixed_leg_schedule(
            notional=Decimal("10000000"),
            fixed_rate=Decimal("0.035"),
            start_date=date(2025, 6, 15),
            end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(sched.cashflows) == 4

    def test_all_amounts_positive(self) -> None:
        sched = unwrap(generate_fixed_leg_schedule(
            notional=Decimal("10000000"),
            fixed_rate=Decimal("0.035"),
            start_date=date(2025, 6, 15),
            end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        for cf in sched.cashflows:
            assert cf.amount > 0
            assert cf.leg_type == SwapLegType.FIXED

    def test_start_after_end_err(self) -> None:
        result = generate_fixed_leg_schedule(
            notional=Decimal("10000000"),
            fixed_rate=Decimal("0.035"),
            start_date=date(2026, 6, 15),
            end_date=date(2025, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(result, Err)

    def test_amount_computation(self) -> None:
        """First quarterly period: amount = 10M * 0.035 * dcf."""
        sched = unwrap(generate_fixed_leg_schedule(
            notional=Decimal("10000000"),
            fixed_rate=Decimal("0.035"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 4, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        cf = sched.cashflows[0]
        expected = Decimal("10000000") * Decimal("0.035") * (Decimal("90") / Decimal("360"))
        assert cf.amount == expected


# ---------------------------------------------------------------------------
# Float leg schedule
# ---------------------------------------------------------------------------


class TestFloatLegSchedule:
    def test_amounts_initially_zero(self) -> None:
        sched = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 6, 15),
            end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        for cf in sched.cashflows:
            assert cf.amount == Decimal("0")
            assert cf.leg_type == SwapLegType.FLOAT

    def test_same_period_count_as_fixed(self) -> None:
        fixed = unwrap(generate_fixed_leg_schedule(
            notional=Decimal("10000000"),
            fixed_rate=Decimal("0.035"),
            start_date=date(2025, 6, 15),
            end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        floating = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 6, 15),
            end_date=date(2026, 6, 15),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(floating.cashflows) == len(fixed.cashflows)


# ---------------------------------------------------------------------------
# Rate fixing
# ---------------------------------------------------------------------------


class TestApplyRateFixing:
    def test_fixes_first_period(self) -> None:
        sched = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 7, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        fixed = unwrap(apply_rate_fixing(
            sched, notional=Decimal("10000000"),
            fixing_rate=Decimal("0.053"),
            fixing_date=date(2025, 1, 15),
        ))
        assert fixed.cashflows[0].amount != Decimal("0")
        assert fixed.cashflows[1].amount == Decimal("0")  # not yet fixed

    def test_computes_correct_amount(self) -> None:
        sched = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 4, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        fixed = unwrap(apply_rate_fixing(
            sched, notional=Decimal("10000000"),
            fixing_rate=Decimal("0.053"),
            fixing_date=date(2025, 1, 1),
        ))
        expected = Decimal("10000000") * Decimal("0.053") * (Decimal("90") / Decimal("360"))
        assert fixed.cashflows[0].amount == expected

    def test_no_matching_period_err(self) -> None:
        sched = unwrap(generate_float_leg_schedule(
            notional=Decimal("10000000"),
            start_date=date(2025, 1, 1),
            end_date=date(2025, 4, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        result = apply_rate_fixing(
            sched, notional=Decimal("10000000"),
            fixing_rate=Decimal("0.053"),
            fixing_date=date(2024, 1, 1),  # before schedule
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# IRS Cashflow Transaction
# ---------------------------------------------------------------------------


class TestIRSCashflowTransaction:
    def _sample_cashflow(self) -> ScheduledCashflow:
        return ScheduledCashflow(
            payment_date=date(2025, 4, 1),
            amount=Decimal("87500"),
            currency=NonEmptyStr(value="USD"),
            leg_type=SwapLegType.FIXED,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 4, 1),
            day_count_fraction=Decimal("0.25"),
        )

    def test_single_move(self) -> None:
        cf = self._sample_cashflow()
        ts = UtcDatetime.now()
        tx = unwrap(create_irs_cashflow_transaction(
            instrument_id="IRS-001",
            payer_account="PAYER-CASH",
            receiver_account="RECEIVER-CASH",
            cashflow=cf,
            tx_id="TX-IRS-001",
            timestamp=ts,
        ))
        assert len(tx.moves) == 1
        assert tx.moves[0].unit == "USD"

    def test_conservation(self) -> None:
        cf = self._sample_cashflow()
        ts = UtcDatetime.now()
        tx = unwrap(create_irs_cashflow_transaction(
            instrument_id="IRS-001",
            payer_account="PAYER",
            receiver_account="RECEIVER",
            cashflow=cf,
            tx_id="TX-IRS-001",
            timestamp=ts,
        ))
        engine = LedgerEngine()
        engine.execute(tx)
        assert engine.total_supply("USD") == Decimal("0")

    def test_empty_instrument_id_err(self) -> None:
        cf = self._sample_cashflow()
        result = create_irs_cashflow_transaction(
            instrument_id="",
            payer_account="PAYER",
            receiver_account="RECEIVER",
            cashflow=cf,
            tx_id="TX-IRS-001",
            timestamp=UtcDatetime.now(),
        )
        assert isinstance(result, Err)

    def test_zero_amount_err(self) -> None:
        cf = ScheduledCashflow(
            payment_date=date(2025, 4, 1),
            amount=Decimal("0"),
            currency=NonEmptyStr(value="USD"),
            leg_type=SwapLegType.FLOAT,
            period_start=date(2025, 1, 1),
            period_end=date(2025, 4, 1),
            day_count_fraction=Decimal("0.25"),
        )
        result = create_irs_cashflow_transaction(
            instrument_id="IRS-001",
            payer_account="PAYER",
            receiver_account="RECEIVER",
            cashflow=cf,
            tx_id="TX-IRS-001",
            timestamp=UtcDatetime.now(),
        )
        assert isinstance(result, Err)
