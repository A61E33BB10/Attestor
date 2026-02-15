"""Tests for attestor.gateway.types — CanonicalOrder, OrderSide, OrderType."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.core.serialization import canonical_bytes
from attestor.core.types import UtcDatetime
from attestor.gateway.types import CanonicalOrder, OrderSide, OrderType

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_TS = UtcDatetime(value=datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC))
_TRADE_DATE = date(2025, 6, 15)
_SETTLE_DATE = date(2025, 6, 17)
_LEI_A = "529900HNOAA1KXQJUQ27"  # Valid 20-char alnum
_LEI_B = "529900ODI3JL1O4COU11"


def _valid_order_kwargs() -> dict[str, object]:
    return {
        "order_id": "ORD-001",
        "instrument_id": "AAPL",
        "isin": None,
        "side": OrderSide.BUY,
        "quantity": Decimal("100"),
        "price": Decimal("175.50"),
        "currency": "USD",
        "order_type": OrderType.LIMIT,
        "counterparty_lei": _LEI_A,
        "executing_party_lei": _LEI_B,
        "trade_date": _TRADE_DATE,
        "settlement_date": _SETTLE_DATE,
        "venue": "XNYS",
        "timestamp": _TS,
    }


# ---------------------------------------------------------------------------
# Valid creation
# ---------------------------------------------------------------------------


class TestCanonicalOrderCreation:
    def test_valid_buy_order(self) -> None:
        result = CanonicalOrder.create(**_valid_order_kwargs())  # type: ignore[arg-type]
        assert isinstance(result, Ok)
        order = result.value
        assert order.order_id.value == "ORD-001"
        assert order.instrument_id.value == "AAPL"
        assert order.side is OrderSide.BUY
        assert order.quantity.value == Decimal("100")
        assert order.price == Decimal("175.50")
        assert order.currency.value == "USD"

    def test_valid_sell_order(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["side"] = OrderSide.SELL
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Ok)
        assert result.value.side is OrderSide.SELL

    def test_valid_with_isin(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["isin"] = "US0378331005"  # Apple ISIN
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Ok)
        assert result.value.isin is not None
        assert result.value.isin.value == "US0378331005"

    def test_market_order_type(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["order_type"] = OrderType.MARKET
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Ok)
        assert result.value.order_type is OrderType.MARKET


# ---------------------------------------------------------------------------
# Invalid creation
# ---------------------------------------------------------------------------


class TestCanonicalOrderRejection:
    def test_empty_order_id(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["order_id"] = ""
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert any(f.path == "order_id" for f in result.error.fields)

    def test_empty_instrument_id(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["instrument_id"] = ""
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert any(f.path == "instrument_id" for f in result.error.fields)

    def test_zero_quantity(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["quantity"] = Decimal("0")
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert any(f.path == "quantity" for f in result.error.fields)

    def test_negative_quantity(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["quantity"] = Decimal("-10")
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)

    def test_settlement_before_trade(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["settlement_date"] = date(2025, 6, 14)  # Before trade_date
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert any(f.path == "settlement_date" for f in result.error.fields)

    def test_invalid_lei(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["counterparty_lei"] = "INVALID"
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert any(f.path == "counterparty_lei" for f in result.error.fields)

    def test_invalid_isin(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["isin"] = "INVALID"
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert any(f.path == "isin" for f in result.error.fields)

    def test_multiple_violations_collected(self) -> None:
        kwargs = _valid_order_kwargs()
        kwargs["order_id"] = ""
        kwargs["instrument_id"] = ""
        kwargs["quantity"] = Decimal("0")
        result = CanonicalOrder.create(**kwargs)  # type: ignore[arg-type]
        assert isinstance(result, Err)
        assert len(result.error.fields) >= 3


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


class TestCanonicalOrderSerialization:
    def test_canonical_bytes_deterministic(self) -> None:
        order = unwrap(CanonicalOrder.create(**_valid_order_kwargs()))  # type: ignore[arg-type]
        b1 = unwrap(canonical_bytes(order))
        b2 = unwrap(canonical_bytes(order))
        assert b1 == b2

    def test_frozen(self) -> None:
        import dataclasses

        import pytest
        order = unwrap(CanonicalOrder.create(**_valid_order_kwargs()))  # type: ignore[arg-type]
        with pytest.raises(dataclasses.FrozenInstanceError):
            order.price = Decimal("200")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class TestEnums:
    def test_order_side_values(self) -> None:
        assert OrderSide.BUY.value == "BUY"
        assert OrderSide.SELL.value == "SELL"

    def test_order_type_values(self) -> None:
        assert OrderType.MARKET.value == "MARKET"
        assert OrderType.LIMIT.value == "LIMIT"
