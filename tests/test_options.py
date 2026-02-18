"""Tests for attestor.ledger.options — premium, exercise, expiry transactions."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.instrument.derivative_types import (
    OptionDetail,
    OptionExerciseStyleEnum,
    OptionTypeEnum,
    SettlementTypeEnum,
)
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.options import (
    create_cash_settlement_exercise_transaction,
    create_exercise_transaction,
    create_expiry_transaction,
    create_premium_transaction,
)
from attestor.ledger.transactions import Account, AccountType, ExecuteResult

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _call_order(
    settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
) -> CanonicalOrder:
    detail = unwrap(OptionDetail.create(
        strike=Decimal("150"), expiry_date=date(2025, 12, 19),
        option_type=OptionTypeEnum.CALL, option_style=OptionExerciseStyleEnum.AMERICAN,
        settlement_type=settlement_type, underlying_id="AAPL",
    ))
    return unwrap(CanonicalOrder.create(
        order_id="OPT-001", instrument_id="AAPL251219C00150000",
        isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
        price=Decimal("5.50"), currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
        venue="CBOE", timestamp=_TS, instrument_detail=detail,
    ))


def _put_order(
    settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
) -> CanonicalOrder:
    detail = unwrap(OptionDetail.create(
        strike=Decimal("150"), expiry_date=date(2025, 12, 19),
        option_type=OptionTypeEnum.PUT, option_style=OptionExerciseStyleEnum.AMERICAN,
        settlement_type=settlement_type, underlying_id="AAPL",
    ))
    return unwrap(CanonicalOrder.create(
        order_id="OPT-002", instrument_id="AAPL251219P00150000",
        isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
        price=Decimal("3.00"), currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
        venue="CBOE", timestamp=_TS, instrument_detail=detail,
    ))


def _make_unsupported_order(
    option_type: OptionTypeEnum,
    settlement_type: SettlementTypeEnum = SettlementTypeEnum.PHYSICAL,
) -> CanonicalOrder:
    """Create an order with a non-CALL/PUT option type for rejection tests."""
    detail = unwrap(OptionDetail.create(
        strike=Decimal("150"), expiry_date=date(2025, 12, 19),
        option_type=option_type, option_style=OptionExerciseStyleEnum.EUROPEAN,
        settlement_type=settlement_type, underlying_id="AAPL",
    ))
    return unwrap(CanonicalOrder.create(
        order_id="OPT-UNS", instrument_id="AAPL251219X",
        isin=None, side=OrderSide.BUY, quantity=Decimal("10"),
        price=Decimal("5.00"), currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei=_LEI_A, executing_party_lei=_LEI_B,
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 16),
        venue="CBOE", timestamp=_TS, instrument_detail=detail,
    ))


def _setup_engine() -> LedgerEngine:
    engine = LedgerEngine()
    for name, atype in [
        ("BUYER-CASH", AccountType.CASH),
        ("SELLER-CASH", AccountType.CASH),
        ("BUYER-POS", AccountType.DERIVATIVES),
        ("SELLER-POS", AccountType.DERIVATIVES),
        ("BUYER-SEC", AccountType.SECURITIES),
        ("SELLER-SEC", AccountType.SECURITIES),
        ("HOLDER-CASH", AccountType.CASH),
        ("WRITER-CASH", AccountType.CASH),
        ("HOLDER-POS", AccountType.DERIVATIVES),
        ("WRITER-POS", AccountType.DERIVATIVES),
        ("HOLDER-SEC", AccountType.SECURITIES),
        ("WRITER-SEC", AccountType.SECURITIES),
    ]:
        engine.register_account(Account(
            account_id=unwrap(NonEmptyStr.parse(name)),
            account_type=atype,
        ))
    return engine


# ---------------------------------------------------------------------------
# Premium transaction
# ---------------------------------------------------------------------------


class TestPremiumTransaction:
    def test_creates_two_moves(self) -> None:
        tx = unwrap(create_premium_transaction(
            _call_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-P1",
        ))
        assert len(tx.moves) == 2

    def test_premium_amount(self) -> None:
        # Premium = 5.50 * 10 * 100 = 5500
        tx = unwrap(create_premium_transaction(
            _call_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-P2",
        ))
        cash_move = tx.moves[0]
        assert cash_move.quantity.value == Decimal("5500")

    def test_position_move_quantity(self) -> None:
        tx = unwrap(create_premium_transaction(
            _call_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-P3",
        ))
        pos_move = tx.moves[1]
        assert pos_move.quantity.value == Decimal("10")

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_premium_transaction(
            _call_order(), "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-P4",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert unwrap(result) == ExecuteResult.APPLIED
        # sigma(USD) == 0, sigma(option contract) == 0
        assert engine.total_supply("USD") == Decimal(0)
        contract = tx.moves[1].unit
        assert engine.total_supply(contract) == Decimal(0)

    def test_reject_non_option_order(self) -> None:
        # Use an equity order (default EquityDetail)
        order = unwrap(CanonicalOrder.create(
            order_id="EQ-001", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"),
            price=Decimal("175"), currency="USD",
            order_type=OrderType.LIMIT,
            counterparty_lei=_LEI_A,
            executing_party_lei=_LEI_B,
            trade_date=date(2025, 6, 15),
            settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        result = create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert "OptionDetail" in result.error.message


# ---------------------------------------------------------------------------
# Physical exercise
# ---------------------------------------------------------------------------


class TestExercisePhysical:
    def test_call_exercise_3_moves(self) -> None:
        tx = unwrap(create_exercise_transaction(
            _call_order(), "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-EX1",
        ))
        assert len(tx.moves) == 3

    def test_call_exercise_cash_amount(self) -> None:
        # Cash = strike * qty * multiplier = 150 * 10 * 100 = 150000
        tx = unwrap(create_exercise_transaction(
            _call_order(), "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-EX2",
        ))
        cash_move = tx.moves[0]
        assert cash_move.quantity.value == Decimal("150000")
        assert cash_move.source == "HOLDER-CASH"
        assert cash_move.destination == "WRITER-CASH"

    def test_call_exercise_securities(self) -> None:
        # Securities = qty * multiplier = 10 * 100 = 1000
        tx = unwrap(create_exercise_transaction(
            _call_order(), "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-EX3",
        ))
        sec_move = tx.moves[1]
        assert sec_move.quantity.value == Decimal("1000")
        assert sec_move.source == "WRITER-SEC"
        assert sec_move.destination == "HOLDER-SEC"

    def test_put_exercise_direction(self) -> None:
        tx = unwrap(create_exercise_transaction(
            _put_order(), "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-EX4",
        ))
        # PUT: holder delivers securities, receives cash
        sec_move = tx.moves[0]
        assert sec_move.source == "HOLDER-SEC"
        assert sec_move.destination == "WRITER-SEC"
        cash_move = tx.moves[1]
        assert cash_move.source == "WRITER-CASH"
        assert cash_move.destination == "HOLDER-CASH"

    def test_reject_cash_settled_order(self) -> None:
        result = create_exercise_transaction(
            _call_order(SettlementTypeEnum.CASH),
            "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert "PHYSICAL" in result.error.message

    def test_reject_election_settlement_type(self) -> None:
        order = _make_unsupported_order(
            OptionTypeEnum.CALL, SettlementTypeEnum.ELECTION,
        )
        result = create_exercise_transaction(
            order, "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert "PHYSICAL" in result.error.message

    def test_reject_cash_or_physical_settlement_type(self) -> None:
        order = _make_unsupported_order(
            OptionTypeEnum.CALL, SettlementTypeEnum.CASH_OR_PHYSICAL,
        )
        result = create_exercise_transaction(
            order, "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert "PHYSICAL" in result.error.message

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_exercise_transaction(
            _call_order(), "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-EX-CON",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("AAPL") == Decimal(0)

    def test_reject_payer_option_type(self) -> None:
        order = _make_unsupported_order(OptionTypeEnum.PAYER)
        result = create_exercise_transaction(
            order, "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert result.error.code == "UNSUPPORTED_OPTION_TYPE"

    def test_reject_receiver_option_type(self) -> None:
        order = _make_unsupported_order(OptionTypeEnum.RECEIVER)
        result = create_exercise_transaction(
            order, "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert result.error.code == "UNSUPPORTED_OPTION_TYPE"

    def test_reject_straddle_option_type(self) -> None:
        order = _make_unsupported_order(OptionTypeEnum.STRADDLE)
        result = create_exercise_transaction(
            order, "HOLDER-CASH", "HOLDER-SEC",
            "WRITER-CASH", "WRITER-SEC",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
        )
        assert isinstance(result, Err)
        assert result.error.code == "UNSUPPORTED_OPTION_TYPE"


# ---------------------------------------------------------------------------
# Cash settlement exercise
# ---------------------------------------------------------------------------


class TestCashSettlementExercise:
    def test_call_itm(self) -> None:
        order = _call_order(SettlementTypeEnum.CASH)
        # settlement_price=160 > strike=150 -> ITM, intrinsic = 10*10*100=10000
        tx = unwrap(create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-CS1",
            settlement_price=Decimal("160"),
        ))
        assert len(tx.moves) == 2
        cash_move = tx.moves[0]
        assert cash_move.quantity.value == Decimal("10000")
        assert cash_move.source == "WRITER-CASH"

    def test_put_itm(self) -> None:
        order = _put_order(SettlementTypeEnum.CASH)
        # settlement_price=140 < strike=150 -> ITM, intrinsic = 10*10*100=10000
        tx = unwrap(create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-CS2",
            settlement_price=Decimal("140"),
        ))
        cash_move = tx.moves[0]
        assert cash_move.quantity.value == Decimal("10000")

    def test_call_otm_rejected(self) -> None:
        order = _call_order(SettlementTypeEnum.CASH)
        result = create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
            settlement_price=Decimal("140"),  # below strike 150
        )
        assert isinstance(result, Err)
        assert "OTM" in result.error.code

    def test_put_otm_rejected(self) -> None:
        order = _put_order(SettlementTypeEnum.CASH)
        result = create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
            settlement_price=Decimal("160"),  # above strike 150
        )
        assert isinstance(result, Err)
        assert "OTM" in result.error.code

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        order = _call_order(SettlementTypeEnum.CASH)
        tx = unwrap(create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-CS-CON",
            settlement_price=Decimal("160"),
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert engine.total_supply("USD") == Decimal(0)

    def test_reject_payer_option_type(self) -> None:
        order = _make_unsupported_order(OptionTypeEnum.PAYER, SettlementTypeEnum.CASH)
        result = create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
            settlement_price=Decimal("160"),
        )
        assert isinstance(result, Err)
        assert result.error.code == "UNSUPPORTED_OPTION_TYPE"

    def test_reject_straddle_option_type(self) -> None:
        order = _make_unsupported_order(OptionTypeEnum.STRADDLE, SettlementTypeEnum.CASH)
        result = create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
            settlement_price=Decimal("160"),
        )
        assert isinstance(result, Err)
        assert result.error.code == "UNSUPPORTED_OPTION_TYPE"

    def test_reject_election_settlement_type(self) -> None:
        order = _make_unsupported_order(
            OptionTypeEnum.CALL, SettlementTypeEnum.ELECTION,
        )
        result = create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
            settlement_price=Decimal("160"),
        )
        assert isinstance(result, Err)
        assert "CASH" in result.error.message

    def test_reject_cash_or_physical_settlement_type(self) -> None:
        order = _make_unsupported_order(
            OptionTypeEnum.CALL, SettlementTypeEnum.CASH_OR_PHYSICAL,
        )
        result = create_cash_settlement_exercise_transaction(
            order, "HOLDER-CASH", "WRITER-CASH",
            "HOLDER-POS", "WRITER-POS", "TX-FAIL",
            settlement_price=Decimal("160"),
        )
        assert isinstance(result, Err)
        assert "CASH" in result.error.message


# ---------------------------------------------------------------------------
# Expiry transaction
# ---------------------------------------------------------------------------


class TestExpiryTransaction:
    def test_single_move(self) -> None:
        tx = unwrap(create_expiry_transaction(
            "AAPL251219C00150000", "HOLDER-POS", "WRITER-POS",
            Decimal("10"), "OPT-AAPL-CALL-150-2025-12-19",
            "TX-EXP1", _TS,
        ))
        assert len(tx.moves) == 1
        assert tx.moves[0].unit == "OPT-AAPL-CALL-150-2025-12-19"

    def test_conservation_in_engine(self) -> None:
        engine = _setup_engine()
        tx = unwrap(create_expiry_transaction(
            "AAPL251219C00150000", "HOLDER-POS", "WRITER-POS",
            Decimal("10"), "OPT-AAPL-CALL-150-2025-12-19",
            "TX-EXP2", _TS,
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        contract = "OPT-AAPL-CALL-150-2025-12-19"
        assert engine.total_supply(contract) == Decimal(0)

    def test_zero_quantity_err(self) -> None:
        result = create_expiry_transaction(
            "AAPL251219C00150000", "HOLDER-POS", "WRITER-POS",
            Decimal("0"), "OPT-AAPL-CALL-150-2025-12-19",
            "TX-FAIL", _TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Full lifecycle: premium -> expiry (conservation)
# ---------------------------------------------------------------------------


class TestFullLifecycle:
    def test_premium_then_expiry_sigma_zero(self) -> None:
        engine = _setup_engine()
        order = _call_order()
        contract = (
            "OPT-AAPL-CALL-150-2025-12-19"
        )

        # 1. Premium transaction
        premium_tx = unwrap(create_premium_transaction(
            order, "BUYER-CASH", "SELLER-CASH",
            "BUYER-POS", "SELLER-POS", "TX-PREM",
        ))
        unwrap(engine.execute(premium_tx))

        # Verify positions after premium
        assert engine.get_balance("BUYER-POS", contract) == Decimal("10")
        assert engine.get_balance("SELLER-POS", contract) == Decimal("-10")

        # 2. Expiry (OTM — just close positions)
        expiry_tx = unwrap(create_expiry_transaction(
            "AAPL251219C00150000", "BUYER-POS", "SELLER-POS",
            Decimal("10"), contract, "TX-EXP", _TS,
        ))
        unwrap(engine.execute(expiry_tx))

        # sigma for all units == 0
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply(contract) == Decimal(0)
        assert engine.get_balance("BUYER-POS", contract) == Decimal(0)
        assert engine.get_balance("SELLER-POS", contract) == Decimal(0)
