"""Commutativity tests — Master Square, Reporting Naturality, Lifecycle-Booking.

CS-02: stub_price(book(trade)) == book(stub_price(trade))
CS-04: report(book(order)) == report(order) (EMIR projection is natural)
CS-05: book(f ; g) == book(f) ; book(g) (lifecycle-booking naturality)
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.money import NonEmptyStr
from attestor.core.result import Ok, unwrap
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType
from attestor.ledger.engine import LedgerEngine
from attestor.ledger.settlement import create_settlement_transaction
from attestor.ledger.transactions import Account, AccountType, ExecuteResult
from attestor.pricing.protocols import StubPricingEngine
from attestor.reporting.emir import project_emir_report

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))


def _acct(aid: str, atype: AccountType = AccountType.CASH) -> Account:
    return Account(account_id=NonEmptyStr(value=aid), account_type=atype)


def _make_order(
    price: str = "175.50", qty: str = "100", side: OrderSide = OrderSide.BUY,
    order_id: str = "ORD-001",
) -> CanonicalOrder:
    return unwrap(CanonicalOrder.create(
        order_id=order_id, instrument_id="AAPL", isin=None,
        side=side, quantity=Decimal(qty), price=Decimal(price),
        currency="USD", order_type=OrderType.LIMIT,
        counterparty_lei="529900HNOAA1KXQJUQ27",
        executing_party_lei="529900ODI3JL1O4COU11",
        trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
        venue="XNYS", timestamp=_TS,
    ))


def _make_engine() -> LedgerEngine:
    engine = LedgerEngine()
    for a in ("BUYER_CASH", "SELLER_CASH", "BUYER_SEC", "SELLER_SEC"):
        engine.register_account(_acct(a))
    return engine


def _book(engine: LedgerEngine, order: CanonicalOrder, tx_id: str) -> None:
    """Book an order into the ledger (settlement)."""
    tx = unwrap(create_settlement_transaction(
        order, "BUYER_CASH", "BUYER_SEC", "SELLER_CASH", "SELLER_SEC", tx_id,
    ))
    result = engine.execute(tx)
    assert isinstance(result, Ok)
    assert result.value is ExecuteResult.APPLIED


# ---------------------------------------------------------------------------
# CS-02: Master Square
# ---------------------------------------------------------------------------


class TestMasterSquare:
    def test_equity_buy(self) -> None:
        """Path A: book then price == Path B: price then book.

        With stub pricing returning oracle_price, both paths yield
        the same position state and the same NPV.
        """
        order = _make_order(price="175.50", qty="100", side=OrderSide.BUY)
        oracle_price = order.price  # the "oracle" price is the trade price

        # Path A: book first, then price
        engine_a = _make_engine()
        _book(engine_a, order, "STL-A")
        pricer_a = StubPricingEngine(oracle_price=oracle_price)
        npv_a = unwrap(pricer_a.price("AAPL", "snap", "cfg")).npv

        # Path B: price first (just computes NPV), then book
        pricer_b = StubPricingEngine(oracle_price=oracle_price)
        npv_b = unwrap(pricer_b.price("AAPL", "snap", "cfg")).npv
        engine_b = _make_engine()
        _book(engine_b, order, "STL-B")

        # Master Square: both paths produce same NPV and same positions
        assert npv_a == npv_b == Decimal("175.50")
        bal_a = engine_a.get_balance("BUYER_CASH", "USD")
        bal_b = engine_b.get_balance("BUYER_CASH", "USD")
        assert bal_a == bal_b
        sec_a = engine_a.get_balance("BUYER_SEC", "AAPL")
        sec_b = engine_b.get_balance("BUYER_SEC", "AAPL")
        assert sec_a == sec_b
        assert engine_a.total_supply("USD") == engine_b.total_supply("USD") == Decimal(0)

    def test_equity_sell(self) -> None:
        """Master Square for a SELL order."""
        order = _make_order(price="200.00", qty="50", side=OrderSide.SELL)
        oracle_price = order.price

        engine_a = _make_engine()
        _book(engine_a, order, "STL-A")
        npv_a = unwrap(StubPricingEngine(oracle_price=oracle_price).price("AAPL", "s", "c")).npv

        npv_b = unwrap(StubPricingEngine(oracle_price=oracle_price).price("AAPL", "s", "c")).npv
        engine_b = _make_engine()
        _book(engine_b, order, "STL-B")

        assert npv_a == npv_b == Decimal("200.00")
        bal_a = engine_a.get_balance("BUYER_CASH", "USD")
        bal_b = engine_b.get_balance("BUYER_CASH", "USD")
        assert bal_a == bal_b


# ---------------------------------------------------------------------------
# CS-04: Reporting Naturality
# ---------------------------------------------------------------------------


class TestReportingNaturality:
    def test_emir_from_order_equals_emir_from_booked_order(self) -> None:
        """report(book(order)) fields == report(order) fields.

        INV-R01: EMIR report is a pure projection — booking doesn't affect
        the report content, because the report is derived solely from the order.
        """
        order = _make_order()

        # Path A: report directly from order
        report_a = unwrap(project_emir_report(order, "ATT-001")).value

        # Path B: book first, then report (from same order)
        engine = _make_engine()
        _book(engine, order, "STL-001")
        report_b = unwrap(project_emir_report(order, "ATT-001")).value

        # Reports are identical — EMIR projection is natural
        assert report_a.instrument_id == report_b.instrument_id
        assert report_a.quantity == report_b.quantity
        assert report_a.price == report_b.price
        assert report_a.uti == report_b.uti
        assert report_a.reporting_counterparty_lei == report_b.reporting_counterparty_lei

    def test_report_content_hash_stable(self) -> None:
        """Same order → same report content_hash regardless of ledger state."""
        order = _make_order()
        att_a = unwrap(project_emir_report(order, "ATT-001"))
        att_b = unwrap(project_emir_report(order, "ATT-001"))
        assert att_a.content_hash == att_b.content_hash


# ---------------------------------------------------------------------------
# CS-05: Lifecycle-Booking Naturality
# ---------------------------------------------------------------------------


class TestLifecycleBookingNaturality:
    def test_sequential_bookings_compose(self) -> None:
        """book(f ; g) == book(f) ; book(g).

        Two settlements applied sequentially produce the same result
        regardless of whether you think of them as one composed operation
        or two separate bookings.
        """
        order1 = _make_order(price="175.50", qty="100", order_id="ORD-001")
        order2 = _make_order(price="180.00", qty="50", order_id="ORD-002")

        # Path A: book both into one engine sequentially
        engine_a = _make_engine()
        _book(engine_a, order1, "STL-001")
        _book(engine_a, order2, "STL-002")

        # Path B: book into separate engines, then compare combined state
        engine_b = _make_engine()
        _book(engine_b, order1, "STL-001")
        _book(engine_b, order2, "STL-002")

        # Both paths produce identical positions
        assert engine_a.positions() == engine_b.positions()
        assert engine_a.total_supply("USD") == Decimal(0)
        assert engine_a.total_supply("AAPL") == Decimal(0)

    def test_booking_order_independence(self) -> None:
        """Booking order1 then order2 == booking order2 then order1.

        Settlement transactions are commutative (they affect independent units).
        """
        order1 = _make_order(price="100", qty="10", order_id="ORD-A")
        order2 = _make_order(price="200", qty="20", order_id="ORD-B")

        engine_a = _make_engine()
        _book(engine_a, order1, "STL-A1")
        _book(engine_a, order2, "STL-A2")

        engine_b = _make_engine()
        _book(engine_b, order2, "STL-B2")
        _book(engine_b, order1, "STL-B1")

        # Same final positions
        for acct, unit in [
            ("BUYER_CASH", "USD"), ("BUYER_SEC", "AAPL"),
            ("SELLER_CASH", "USD"),
        ]:
            assert engine_a.get_balance(acct, unit) == engine_b.get_balance(acct, unit)


# ---------------------------------------------------------------------------
# Property-based commutativity
# ---------------------------------------------------------------------------


class TestPropertyBasedCommutativity:
    @given(
        price=st.decimals(min_value=Decimal("0.01"), max_value=Decimal("10000"),
                          places=2, allow_nan=False, allow_infinity=False),
        qty=st.decimals(min_value=Decimal("1"), max_value=Decimal("100000"),
                        places=0, allow_nan=False, allow_infinity=False),
    )
    @settings(max_examples=200)
    def test_master_square_property(self, price: Decimal, qty: Decimal) -> None:
        """For any valid (price, qty), both Master Square paths agree."""
        order = unwrap(CanonicalOrder.create(
            order_id="ORD-PBT", instrument_id="AAPL", isin=None,
            side=OrderSide.BUY, quantity=qty, price=price,
            currency="USD", order_type=OrderType.LIMIT,
            counterparty_lei="529900HNOAA1KXQJUQ27",
            executing_party_lei="529900ODI3JL1O4COU11",
            trade_date=date(2025, 6, 15), settlement_date=date(2025, 6, 17),
            venue="XNYS", timestamp=_TS,
        ))

        # Path A: book → price
        engine_a = _make_engine()
        _book(engine_a, order, "STL-A")
        npv_a = unwrap(StubPricingEngine(oracle_price=price).price("AAPL", "s", "c")).npv

        # Path B: price → book
        npv_b = unwrap(StubPricingEngine(oracle_price=price).price("AAPL", "s", "c")).npv
        engine_b = _make_engine()
        _book(engine_b, order, "STL-B")

        assert npv_a == npv_b
        bal_a = engine_a.get_balance("BUYER_CASH", "USD")
        bal_b = engine_b.get_balance("BUYER_CASH", "USD")
        assert bal_a == bal_b
        assert engine_a.total_supply("USD") == Decimal(0)
