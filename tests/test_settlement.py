"""Tests for attestor.ledger.settlement — T+2 settlement transaction creation."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.settlement import create_settlement_transaction
from attestor.ledger.transactions import Account, AccountType, ExecuteResult

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _order(
    price: str = "175.50", qty: str = "100", side: OrderSide = OrderSide.BUY,
) -> CanonicalOrder:
    return unwrap(CanonicalOrder.create(
        order_id="ORD-001", instrument_id="AAPL", isin=None,
        side=side, quantity=Decimal(qty), price=Decimal(price),
        currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XNYS", timestamp=_TS,
    ))


def _acct(aid: str, atype: AccountType = AccountType.CASH) -> Account:
    return Account(account_id=NonEmptyStr(value=aid), account_type=atype)


# ---------------------------------------------------------------------------
# Valid settlement
# ---------------------------------------------------------------------------


class TestValidSettlement:
    def test_creates_two_moves(self) -> None:
        order = _order()
        result = create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        )
        assert isinstance(result, Ok)
        tx = result.value
        assert len(tx.moves) == 2

    def test_cash_amount_equals_price_times_quantity(self) -> None:
        order = _order(price="175.50", qty="100")
        tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        ))
        cash_move = tx.moves[0]
        assert cash_move.quantity.value == Decimal("17550.00")
        assert cash_move.source == "BUYER_CASH"
        assert cash_move.destination == "SELLER_CASH"
        assert cash_move.unit == "USD"

    def test_securities_move(self) -> None:
        order = _order(qty="100")
        tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        ))
        sec_move = tx.moves[1]
        assert sec_move.quantity.value == Decimal("100")
        assert sec_move.source == "SELLER_SEC"
        assert sec_move.destination == "BUYER_SEC"
        assert sec_move.unit == "AAPL"

    def test_tx_id_and_timestamp(self) -> None:
        order = _order()
        tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        ))
        assert tx.tx_id == "STL-001"
        assert tx.timestamp == order.timestamp


# ---------------------------------------------------------------------------
# Full lifecycle with LedgerEngine
# ---------------------------------------------------------------------------


class TestSettlementWithEngine:
    def test_execute_settlement_sigma_preserved(self) -> None:
        """Register accounts → execute settlement → verify sigma == 0."""
        engine = LedgerEngine()
        for a in ("BUYER_CASH", "SELLER_CASH", "BUYER_SEC", "SELLER_SEC"):
            engine.register_account(_acct(a))

        order = _order(price="175.50", qty="100")
        tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        ))
        result = engine.execute(tx)
        assert isinstance(result, Ok)
        assert result.value is ExecuteResult.APPLIED

        # 4 balance changes
        assert engine.get_balance("BUYER_CASH", "USD") == Decimal("-17550.00")
        assert engine.get_balance("SELLER_CASH", "USD") == Decimal("17550.00")
        assert engine.get_balance("SELLER_SEC", "AAPL") == Decimal("-100")
        assert engine.get_balance("BUYER_SEC", "AAPL") == Decimal("100")

        # Conservation
        assert engine.total_supply("USD") == Decimal(0)
        assert engine.total_supply("AAPL") == Decimal(0)

    def test_positions_after_settlement(self) -> None:
        engine = LedgerEngine()
        for a in ("BUYER_CASH", "SELLER_CASH", "BUYER_SEC", "SELLER_SEC"):
            engine.register_account(_acct(a))
        order = _order()
        tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        ))
        engine.execute(tx)
        positions = engine.positions()
        assert len(positions) == 4

    def test_inv_l04_settlement_zero_sum(self) -> None:
        """INV-L04: net of settlement is zero per unit."""
        engine = LedgerEngine()
        for a in ("BUYER_CASH", "SELLER_CASH", "BUYER_SEC", "SELLER_SEC"):
            engine.register_account(_acct(a))
        order = _order(price="50.25", qty="200")
        tx = unwrap(create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-002",
        ))
        engine.execute(tx)
        # Cash: buyer loses 10050, seller gains 10050 → net 0
        assert engine.total_supply("USD") == Decimal(0)
        # Securities: seller loses 200, buyer gains 200 → net 0
        assert engine.total_supply("AAPL") == Decimal(0)


# ---------------------------------------------------------------------------
# Invalid settlement
# ---------------------------------------------------------------------------


class TestInvalidSettlement:
    def test_empty_buyer_cash_account(self) -> None:
        order = _order()
        result = create_settlement_transaction(
            order, "", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-001",
        )
        assert isinstance(result, Err)

    def test_empty_tx_id(self) -> None:
        order = _order()
        result = create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "",
        )
        assert isinstance(result, Err)

    def test_zero_price_rejected(self) -> None:
        """Cash amount = 0 * qty = 0, which is not PositiveDecimal."""
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-002", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=Decimal("100"), price=Decimal("0"),
            currency="USD", order_type=OrderType.MARKET,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))
        result = create_settlement_transaction(
            order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", "STL-003",
        )
        assert isinstance(result, Err)
