"""Tests for attestor.gateway.parser — parse_order, order_to_dict."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given, settings
from hypothesis import strategies as st

from attestor.core.result import Err, Ok, unwrap
from attestor.gateway.parser import order_to_dict, parse_order
from attestor.gateway.types import OrderSide, OrderType

# ---------------------------------------------------------------------------
# Valid raw order fixture
# ---------------------------------------------------------------------------

_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _valid_raw() -> dict[str, object]:
    return {
        "order_id": "ORD-001",
        "instrument_id": "AAPL",
        "isin": None,
        "side": "BUY",
        "quantity": "100",
        "price": "175.50",
        "currency": "USD",
        "order_type": "LIMIT",
        "counterparty_lei": _LEI_A,
        "executing_party_lei": _LEI_B,
        "trade_date": "2025-06-15",
        "settlement_date": "2025-06-17",
        "venue": "XNYS",
        "timestamp": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
    }


# ---------------------------------------------------------------------------
# Valid parsing
# ---------------------------------------------------------------------------


class TestParseOrderValid:
    def test_parse_valid_order(self) -> None:
        result = parse_order(_valid_raw())
        assert isinstance(result, Ok)
        order = result.value
        assert order.order_id.value == "ORD-001"
        assert order.side is OrderSide.BUY
        assert order.quantity.value == Decimal("100")

    def test_settlement_date_computed_from_trade_date(self) -> None:
        raw = _valid_raw()
        del raw["settlement_date"]
        raw["trade_date"] = "2025-06-16"  # Monday
        result = parse_order(raw)
        assert isinstance(result, Ok)
        assert result.value.settlement_date == date(2025, 6, 18)  # Wednesday (T+2)

    def test_settlement_date_skips_weekends(self) -> None:
        raw = _valid_raw()
        del raw["settlement_date"]
        raw["trade_date"] = "2025-06-19"  # Thursday
        result = parse_order(raw)
        assert isinstance(result, Ok)
        assert result.value.settlement_date == date(2025, 6, 23)  # Monday (skip Sat/Sun)

    def test_sell_order(self) -> None:
        raw = _valid_raw()
        raw["side"] = "SELL"
        result = parse_order(raw)
        assert isinstance(result, Ok)
        assert result.value.side is OrderSide.SELL

    def test_market_order(self) -> None:
        raw = _valid_raw()
        raw["order_type"] = "MARKET"
        result = parse_order(raw)
        assert isinstance(result, Ok)
        assert result.value.order_type is OrderType.MARKET

    def test_numeric_quantity(self) -> None:
        raw = _valid_raw()
        raw["quantity"] = 50  # int, not string
        result = parse_order(raw)
        assert isinstance(result, Ok)
        assert result.value.quantity.value == Decimal("50")


# ---------------------------------------------------------------------------
# Invalid parsing
# ---------------------------------------------------------------------------


class TestParseOrderInvalid:
    def test_missing_order_id(self) -> None:
        raw = _valid_raw()
        del raw["order_id"]
        result = parse_order(raw)
        assert isinstance(result, Err)
        assert any(f.path == "order_id" for f in result.error.fields)

    def test_missing_side(self) -> None:
        raw = _valid_raw()
        del raw["side"]
        result = parse_order(raw)
        assert isinstance(result, Err)

    def test_invalid_side_value(self) -> None:
        raw = _valid_raw()
        raw["side"] = "HOLD"
        result = parse_order(raw)
        assert isinstance(result, Err)
        assert any(f.path == "side" for f in result.error.fields)

    def test_missing_price(self) -> None:
        raw = _valid_raw()
        del raw["price"]
        result = parse_order(raw)
        assert isinstance(result, Err)

    def test_non_numeric_quantity(self) -> None:
        raw = _valid_raw()
        raw["quantity"] = "abc"
        result = parse_order(raw)
        assert isinstance(result, Err)

    def test_missing_timestamp(self) -> None:
        raw = _valid_raw()
        del raw["timestamp"]
        result = parse_order(raw)
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# INV-G01: Parse Idempotency
# ---------------------------------------------------------------------------


class TestParseIdempotency:
    def test_roundtrip(self) -> None:
        """parse(to_dict(parse(raw))) == parse(raw)."""
        raw = _valid_raw()
        order1 = unwrap(parse_order(raw))
        raw2 = order_to_dict(order1)
        order2 = unwrap(parse_order(raw2))
        assert order1.order_id == order2.order_id
        assert order1.instrument_id == order2.instrument_id
        assert order1.side == order2.side
        assert order1.quantity == order2.quantity
        assert order1.price == order2.price
        assert order1.settlement_date == order2.settlement_date


# ---------------------------------------------------------------------------
# INV-G02: Parse Totality — never panics (Hypothesis fuzz)
# ---------------------------------------------------------------------------


class TestParseTotality:
    @settings(max_examples=200)
    @given(st.dictionaries(
        st.text(min_size=0, max_size=20),
        st.one_of(
            st.none(),
            st.text(min_size=0, max_size=50),
            st.integers(min_value=-1000, max_value=1000),
            st.booleans(),
        ),
        max_size=20,
    ))
    def test_never_panics(self, raw: dict[str, object]) -> None:
        """parse_order always returns Ok or Err, never raises."""
        result = parse_order(raw)
        assert isinstance(result, (Ok, Err))
