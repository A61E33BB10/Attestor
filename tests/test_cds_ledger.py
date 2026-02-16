"""Tests for attestor.ledger.cds -- premium, credit event, maturity close."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal, localcontext

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.instrument.fx_types import DayCountConvention, PaymentFrequency
from attestor.ledger.cds import (
    ScheduledCDSPremium,
    create_cds_credit_event_settlement,
    create_cds_maturity_close,
    create_cds_premium_transaction,
    create_cds_trade_transaction,
    generate_cds_premium_schedule,
)
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.transactions import Account, AccountType, ExecuteResult

_TS = UtcDatetime(value=datetime(2025, 9, 20, 14, 0, 0, tzinfo=UTC))
_CDS_ID = "CDS-ITRAXX-EUR-S42-5Y"


def _setup_engine() -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in [
        ("BUYER-CASH", AccountType.CASH),
        ("SELLER-CASH", AccountType.CASH),
        ("BUYER-POS", AccountType.DERIVATIVES),
        ("SELLER-POS", AccountType.DERIVATIVES),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


def _make_premium(
    amount: Decimal = Decimal("12500"),
    currency: str = "USD",
) -> ScheduledCDSPremium:
    return ScheduledCDSPremium(
        payment_date=date(2025, 12, 20),
        amount=amount,
        currency=NonEmptyStr(value=currency),
        period_start=date(2025, 9, 20),
        period_end=date(2025, 12, 20),
        day_count_fraction=Decimal("91") / Decimal("360"),
    )


# ---------------------------------------------------------------------------
# Premium schedule generation
# ---------------------------------------------------------------------------


class TestGenerateCDSPremiumSchedule:
    def test_quarterly_schedule_count(self) -> None:
        """5Y CDS with quarterly payments -> 20 periods."""
        result = generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2030, 3, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        schedule = unwrap(result)
        assert len(schedule) == 20

    def test_amount_equals_notional_times_spread_times_dcf(self) -> None:
        """Each premium = notional * spread * dcf."""
        result = generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="EUR",
        )
        schedule = unwrap(result)
        assert len(schedule) == 1
        premium = schedule[0]
        # 2025-03-20 to 2025-06-20 = 92 days
        expected_dcf = Decimal("92") / Decimal("360")
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            expected_amount = Decimal("10000000") * Decimal("0.01") * expected_dcf
        assert premium.amount == expected_amount
        assert premium.day_count_fraction == expected_dcf

    def test_payment_date_is_period_end(self) -> None:
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("5000000"),
            spread=Decimal("0.005"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2026, 3, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        for p in schedule:
            assert p.payment_date == p.period_end

    def test_semi_annual_schedule_count(self) -> None:
        """2Y CDS with semi-annual -> 4 periods."""
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("1000000"),
            spread=Decimal("0.02"),
            effective_date=date(2025, 1, 1),
            maturity_date=date(2027, 1, 1),
            day_count=DayCountConvention.ACT_365,
            payment_frequency=PaymentFrequency.SEMI_ANNUAL,
            currency="GBP",
        ))
        assert len(schedule) == 4

    def test_err_effective_after_maturity(self) -> None:
        result = generate_cds_premium_schedule(
            notional=Decimal("1000000"),
            spread=Decimal("0.01"),
            effective_date=date(2030, 1, 1),
            maturity_date=date(2025, 1, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(result, Err)

    def test_err_negative_notional(self) -> None:
        result = generate_cds_premium_schedule(
            notional=Decimal("-100"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 1, 1),
            maturity_date=date(2026, 1, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(result, Err)

    def test_err_negative_spread(self) -> None:
        result = generate_cds_premium_schedule(
            notional=Decimal("1000000"),
            spread=Decimal("-0.01"),
            effective_date=date(2025, 1, 1),
            maturity_date=date(2026, 1, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(result, Err)

    def test_err_empty_currency(self) -> None:
        result = generate_cds_premium_schedule(
            notional=Decimal("1000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 1, 1),
            maturity_date=date(2026, 1, 1),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="",
        )
        assert isinstance(result, Err)

    def test_periods_cover_full_range(self) -> None:
        """First period starts at effective_date, last ends at maturity_date."""
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("1000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2030, 3, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert schedule[0].period_start == date(2025, 3, 20)
        assert schedule[-1].period_end == date(2030, 3, 20)


# ---------------------------------------------------------------------------
# Premium transaction
# ---------------------------------------------------------------------------


class TestCDSPremiumTransaction:
    def test_single_move_buyer_to_seller(self) -> None:
        tx = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            _make_premium(), "TX-CDS-P1", _TS,
        ))
        assert len(tx.moves) == 1
        move = tx.moves[0]
        assert move.source == "BUYER-CASH"
        assert move.destination == "SELLER-CASH"

    def test_premium_amount_correct(self) -> None:
        tx = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            _make_premium(amount=Decimal("25000")), "TX-CDS-P2", _TS,
        ))
        assert tx.moves[0].quantity.value == Decimal("25000")

    def test_premium_currency_unit(self) -> None:
        tx = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            _make_premium(currency="EUR"), "TX-CDS-P3", _TS,
        ))
        assert tx.moves[0].unit == "EUR"

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            _make_premium(), "TX-CDS-P4", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED
        assert engine.total_supply("USD") == Decimal(0)

    def test_zero_amount_err(self) -> None:
        result = create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            _make_premium(amount=Decimal("0")), "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)

    def test_same_account_err(self) -> None:
        result = create_cds_premium_transaction(
            "BUYER-CASH", "BUYER-CASH",
            _make_premium(), "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Credit event settlement
# ---------------------------------------------------------------------------


class TestCDSCreditEventSettlement:
    def test_protection_payment_amount(self) -> None:
        """payment = notional * (1 - auction_price) = 10M * (1 - 0.40) = 6M."""
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CE1",
            timestamp=_TS,
        ))
        assert len(tx.moves) == 1
        assert tx.moves[0].quantity.value == Decimal("6000000")

    def test_seller_to_buyer_direction(self) -> None:
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("1000000"),
            auction_price=Decimal("0.30"),
            currency="USD",
            tx_id="TX-CE2",
            timestamp=_TS,
        ))
        assert tx.moves[0].source == "SELLER-CASH"
        assert tx.moves[0].destination == "BUYER-CASH"

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("5000000"),
            auction_price=Decimal("0.25"),
            currency="USD",
            tx_id="TX-CE-CON",
            timestamp=_TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)

    def test_auction_price_above_one_err(self) -> None:
        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("1000000"),
            auction_price=Decimal("1.5"),
            currency="USD",
            tx_id="TX-FAIL",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_AUCTION_PRICE"

    def test_auction_price_negative_err(self) -> None:
        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("1000000"),
            auction_price=Decimal("-0.1"),
            currency="USD",
            tx_id="TX-FAIL",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "INVALID_AUCTION_PRICE"

    def test_100_percent_recovery_err(self) -> None:
        """auction_price == 1 -> zero protection payment -> Err."""
        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("1000000"),
            auction_price=Decimal("1"),
            currency="USD",
            tx_id="TX-FAIL",
            timestamp=_TS,
        )
        assert isinstance(result, Err)
        assert result.error.code == "ZERO_PROTECTION_PAYMENT"

    def test_zero_recovery_full_notional(self) -> None:
        """auction_price == 0 -> payment == full notional."""
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0"),
            currency="USD",
            tx_id="TX-CE-FULL",
            timestamp=_TS,
        ))
        assert tx.moves[0].quantity.value == Decimal("10000000")


# ---------------------------------------------------------------------------
# Maturity close
# ---------------------------------------------------------------------------


class TestCDSMaturityClose:
    def test_single_move_buyer_to_seller(self) -> None:
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_maturity_close(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-MAT1", _TS,
        ))
        assert len(tx.moves) == 1
        assert tx.moves[0].source == "BUYER-POS"
        assert tx.moves[0].destination == "SELLER-POS"
        assert tx.moves[0].unit == contract

    def test_conservation_sigma_zero(self) -> None:
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_maturity_close(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-MAT2", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)

    def test_zero_quantity_err(self) -> None:
        result = create_cds_maturity_close(
            "BUYER-POS", "SELLER-POS",
            "CDS-X", Decimal("0"), "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Trade transaction (position opening at inception)
# ---------------------------------------------------------------------------


class TestCDSTradeTransaction:
    def test_single_move_seller_to_buyer(self) -> None:
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-TRADE1", _TS,
        ))
        assert len(tx.moves) == 1
        assert tx.moves[0].source == "SELLER-POS"
        assert tx.moves[0].destination == "BUYER-POS"
        assert tx.moves[0].unit == contract

    def test_conservation_sigma_zero(self) -> None:
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-TRADE2", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply(contract) == Decimal(0)

    def test_buyer_gets_positive_position(self) -> None:
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-TRADE3", _TS,
        ))
        unwrap(engine.execute(tx))
        assert engine.get_balance("BUYER-POS", contract) == Decimal("1")
        assert engine.get_balance("SELLER-POS", contract) == Decimal("-1")

    def test_zero_quantity_err(self) -> None:
        result = create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            "CDS-X", Decimal("0"), "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)

    def test_same_account_err(self) -> None:
        result = create_cds_trade_transaction(
            "BUYER-POS", "BUYER-POS",
            "CDS-X", Decimal("1"), "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Credit event settlement with accrued premium + position close
# ---------------------------------------------------------------------------


class TestCDSCreditEventSettlementFull:
    def test_three_moves_complete(self) -> None:
        """Full settlement: protection + accrued premium + position close."""
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CE-FULL",
            timestamp=_TS,
            accrued_premium=Decimal("25000"),
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=f"CDS-{_CDS_ID}",
            position_quantity=Decimal("1"),
        ))
        assert len(tx.moves) == 3
        # Move 1: protection payment seller -> buyer
        assert tx.moves[0].source == "SELLER-CASH"
        assert tx.moves[0].destination == "BUYER-CASH"
        assert tx.moves[0].quantity.value == Decimal("6000000")
        # Move 2: accrued premium buyer -> seller
        assert tx.moves[1].source == "BUYER-CASH"
        assert tx.moves[1].destination == "SELLER-CASH"
        assert tx.moves[1].quantity.value == Decimal("25000")
        # Move 3: position close buyer_pos -> seller_pos
        assert tx.moves[2].source == "BUYER-POS"
        assert tx.moves[2].destination == "SELLER-POS"
        assert tx.moves[2].unit == f"CDS-{_CDS_ID}"

    def test_full_settlement_conservation(self) -> None:
        """All 3 moves in one transaction: sigma(USD)==0, sigma(contract)==0."""
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"

        # Open position first
        open_tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-OPEN", _TS,
        ))
        unwrap(engine.execute(open_tx))

        # Full credit event settlement
        ce_tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("5000000"),
            auction_price=Decimal("0.25"),
            currency="USD",
            tx_id="TX-CE-FULL-CON",
            timestamp=_TS,
            accrued_premium=Decimal("10000"),
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=contract,
            position_quantity=Decimal("1"),
        ))
        unwrap(engine.execute(ce_tx))

        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)
        # Position is fully closed
        assert engine.get_balance("BUYER-POS", contract) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract) == Decimal(0)

    def test_without_accrued_creates_two_moves(self) -> None:
        """Protection + position close, no accrued premium."""
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CE-2MOVE",
            timestamp=_TS,
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=f"CDS-{_CDS_ID}",
            position_quantity=Decimal("1"),
        ))
        assert len(tx.moves) == 2

    def test_incomplete_position_params_err(self) -> None:
        """Providing only some position params -> Err."""
        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-FAIL",
            timestamp=_TS,
            buyer_position_account="BUYER-POS",
            # Missing seller_position_account, contract_unit, position_quantity
        )
        assert isinstance(result, Err)
        assert result.error.code == "INCOMPLETE_POSITION_PARAMS"

    def test_backward_compat_no_extras(self) -> None:
        """Without the new keyword args, creates 1 move as before."""
        tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CE-COMPAT",
            timestamp=_TS,
        ))
        assert len(tx.moves) == 1


# ---------------------------------------------------------------------------
# Full lifecycle: schedule -> premium -> credit event -> close
# ---------------------------------------------------------------------------


class TestCDSFullLifecycle:
    def test_premium_then_credit_event_conservation(self) -> None:
        engine = _setup_engine()

        # 1. Pay one premium
        premium = _make_premium(amount=Decimal("25000"))
        prem_tx = unwrap(create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            premium, "TX-PREM-1", _TS,
        ))
        unwrap(engine.execute(prem_tx))
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.get_balance("BUYER-CASH", "USD") == Decimal("-25000")
        assert engine.get_balance("SELLER-CASH", "USD") == Decimal("25000")

        # 2. Credit event: seller pays buyer protection
        ce_tx = unwrap(create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=Decimal("10000000"),
            auction_price=Decimal("0.40"),
            currency="USD",
            tx_id="TX-CE-LIFE",
            timestamp=_TS,
        ))
        unwrap(engine.execute(ce_tx))
        assert engine.total_supply("USD") == Decimal(0)

    def test_generated_schedule_all_accepted_by_engine(self) -> None:
        engine = _setup_engine()
        schedule = unwrap(generate_cds_premium_schedule(
            notional=Decimal("10000000"),
            spread=Decimal("0.01"),
            effective_date=date(2025, 3, 20),
            maturity_date=date(2026, 3, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        ))
        assert len(schedule) == 4
        for i, premium in enumerate(schedule):
            tx = unwrap(create_cds_premium_transaction(
                "BUYER-CASH", "SELLER-CASH",
                premium, f"TX-SCHED-{i}", _TS,
            ))
            result = engine.execute(tx)
            assert isinstance(result, Ok)
            assert unwrap(result) == ExecuteResult.APPLIED
        assert engine.total_supply("USD") == Decimal(0)


# ---------------------------------------------------------------------------
# Hypothesis: conservation property
# ---------------------------------------------------------------------------


class TestCDSConservationProperty:
    @given(
        notional=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        auction_price=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("0.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_credit_event_conservation_property(
        self, notional: Decimal, auction_price: Decimal,
    ) -> None:
        """For any valid (notional, auction_price), sigma(USD) == 0 after execute."""
        engine = _setup_engine()
        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=notional,
            auction_price=auction_price,
            currency="USD",
            tx_id="TX-HYP",
            timestamp=_TS,
        )
        # Must be Ok for valid inputs
        assert isinstance(result, Ok), f"Unexpected Err: {result}"
        tx = unwrap(result)
        exec_result = engine.execute(tx)
        assert isinstance(exec_result, Ok)
        assert engine.total_supply("USD") == Decimal(0)

    @given(
        notional=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        spread=st.decimals(
            min_value=Decimal("0.0001"),
            max_value=Decimal("0.10"),
            places=4,
            allow_nan=False,
            allow_infinity=False,
        ).filter(lambda d: d > 0),
    )
    @settings(max_examples=200, deadline=None)
    def test_premium_conservation_property(
        self, notional: Decimal, spread: Decimal,
    ) -> None:
        """For any valid (notional, spread), sigma(USD) == 0 after premium."""
        engine = _setup_engine()
        schedule_result = generate_cds_premium_schedule(
            notional=notional,
            spread=spread,
            effective_date=date(2025, 3, 20),
            maturity_date=date(2025, 6, 20),
            day_count=DayCountConvention.ACT_360,
            payment_frequency=PaymentFrequency.QUARTERLY,
            currency="USD",
        )
        assert isinstance(schedule_result, Ok)
        schedule = unwrap(schedule_result)
        assert len(schedule) >= 1
        premium = schedule[0]
        tx_result = create_cds_premium_transaction(
            "BUYER-CASH", "SELLER-CASH",
            premium, "TX-HYP-PREM", _TS,
        )
        assert isinstance(tx_result, Ok)
        tx = unwrap(tx_result)
        exec_result = engine.execute(tx)
        assert isinstance(exec_result, Ok)
        assert engine.total_supply("USD") == Decimal(0)

    @given(
        quantity=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("1000"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_trade_transaction_conservation_property(
        self, quantity: Decimal,
    ) -> None:
        """For any quantity, sigma(contract_unit) == 0 after trade booking."""
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, quantity, "TX-HYP-TRADE", _TS,
        ))
        exec_result = engine.execute(tx)
        assert isinstance(exec_result, Ok)
        assert engine.total_supply(contract) == Decimal(0)

    @given(
        notional=st.decimals(
            min_value=Decimal("1000"),
            max_value=Decimal("100000000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        auction_price=st.decimals(
            min_value=Decimal("0"),
            max_value=Decimal("0.99"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
        accrued=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("100000"),
            places=2,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_full_settlement_conservation_property(
        self, notional: Decimal, auction_price: Decimal, accrued: Decimal,
    ) -> None:
        """Full credit event settlement: sigma(USD)==0 and sigma(contract)==0."""
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"

        # Open position
        open_tx = unwrap(create_cds_trade_transaction(
            "BUYER-POS", "SELLER-POS",
            contract, Decimal("1"), "TX-HYP-OPEN", _TS,
        ))
        unwrap(engine.execute(open_tx))

        # Full settlement with accrued + position close
        result = create_cds_credit_event_settlement(
            "BUYER-CASH", "SELLER-CASH",
            notional=notional,
            auction_price=auction_price,
            currency="USD",
            tx_id="TX-HYP-CE",
            timestamp=_TS,
            accrued_premium=accrued,
            buyer_position_account="BUYER-POS",
            seller_position_account="SELLER-POS",
            contract_unit=contract,
            position_quantity=Decimal("1"),
        )
        assert isinstance(result, Ok), f"Unexpected Err: {result}"
        unwrap(engine.execute(unwrap(result)))
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)

    @given(
        quantity=st.decimals(
            min_value=Decimal("1"),
            max_value=Decimal("1000"),
            places=0,
            allow_nan=False,
            allow_infinity=False,
        ),
    )
    @settings(max_examples=200, deadline=None)
    def test_maturity_close_conservation_property(
        self, quantity: Decimal,
    ) -> None:
        """For any quantity, sigma(contract_unit) == 0 after maturity close."""
        engine = _setup_engine()
        contract = f"CDS-{_CDS_ID}"
        tx = unwrap(create_cds_maturity_close(
            "BUYER-POS", "SELLER-POS",
            contract, quantity, "TX-HYP-MAT", _TS,
        ))
        exec_result = engine.execute(tx)
        assert isinstance(exec_result, Ok)
        assert engine.total_supply(contract) == Decimal(0)
