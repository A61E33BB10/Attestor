"""Tests for derivative gateway parsing — parse_option_order, parse_futures_order."""

from __future__ import annotations

from datetime import UTC, datetime

from attestor.core.result import Err, Ok, unwrap
from attestor.gateway.parser import parse_futures_order, parse_option_order
from attestor.instrument.derivative_types import (
    EquityDetail,
    FuturesDetail,
    OptionDetail,
    OptionTypeEnum,
)

_LEI_A = "529900HNOAA1KXQJUQ27"
_LEI_B = "529900ODI3JL1O4COU11"


def _valid_option_raw() -> dict[str, object]:
    return {
        "order_id": "OPT-001",
        "instrument_id": "AAPL251219C00150000",
        "side": "BUY",
        "quantity": "10",
        "price": "5.50",
        "currency": "USD",
        "order_type": "LIMIT",
        "counterparty_lei": _LEI_A,
        "executing_party_lei": _LEI_B,
        "trade_date": "2025-06-15",
        "venue": "CBOE",
        "timestamp": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
        # Option-specific
        "strike": "150",
        "expiry_date": "2025-12-19",
        "option_type": "Call",
        "option_style": "American",
        "settlement_type": "PHYSICAL",
        "underlying_id": "AAPL",
    }


def _valid_futures_raw() -> dict[str, object]:
    return {
        "order_id": "FUT-001",
        "instrument_id": "ESZ5",
        "side": "BUY",
        "quantity": "5",
        "price": "5200",
        "currency": "USD",
        "order_type": "MARKET",
        "counterparty_lei": _LEI_A,
        "executing_party_lei": _LEI_B,
        "trade_date": "2025-06-15",
        "venue": "CME",
        "timestamp": datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC).isoformat(),
        # Futures-specific
        "expiry_date": "2025-12-19",
        "contract_size": "50",
        "settlement_type": "CASH",
        "underlying_id": "ES",
    }


# ---------------------------------------------------------------------------
# parse_option_order
# ---------------------------------------------------------------------------


class TestParseOptionOrder:
    def test_valid(self) -> None:
        result = parse_option_order(_valid_option_raw())
        assert isinstance(result, Ok)
        order = unwrap(result)
        assert isinstance(order.instrument_detail, OptionDetail)
        assert order.instrument_detail.option_type == OptionTypeEnum.CALL

    def test_settlement_date_defaults_to_t_plus_1(self) -> None:
        raw = _valid_option_raw()
        # No explicit settlement_date — should be T+1
        assert "settlement_date" not in raw
        order = unwrap(parse_option_order(raw))
        # trade_date is 2025-06-15 (Sunday? No — let's check: June 15, 2025 is Sunday)
        # Actually T+1 from Sunday... the parser delegates to parse_order which uses
        # add_business_days(trade_date, 2) for equities but we override to T+1.
        # June 15 2025 is a Sunday. But trade_date as string "2025-06-15"
        # add_business_days(date(2025,6,15), 1) = Monday 2025-06-16
        from datetime import date
        assert order.settlement_date == date(2025, 6, 16)

    def test_explicit_settlement_date_preserved(self) -> None:
        raw = _valid_option_raw()
        raw["settlement_date"] = "2025-06-20"
        order = unwrap(parse_option_order(raw))
        from datetime import date
        assert order.settlement_date == date(2025, 6, 20)

    def test_missing_strike_err(self) -> None:
        raw = _valid_option_raw()
        del raw["strike"]
        result = parse_option_order(raw)
        assert isinstance(result, Err)

    def test_missing_option_type_err(self) -> None:
        raw = _valid_option_raw()
        del raw["option_type"]
        result = parse_option_order(raw)
        assert isinstance(result, Err)

    def test_invalid_option_style_err(self) -> None:
        raw = _valid_option_raw()
        raw["option_style"] = "BERMUDA"
        result = parse_option_order(raw)
        assert isinstance(result, Err)

    def test_missing_underlying_err(self) -> None:
        raw = _valid_option_raw()
        del raw["underlying_id"]
        result = parse_option_order(raw)
        assert isinstance(result, Err)

    def test_expiry_before_trade_date_err(self) -> None:
        raw = _valid_option_raw()
        raw["expiry_date"] = "2025-06-14"  # before trade_date
        result = parse_option_order(raw)
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# parse_futures_order
# ---------------------------------------------------------------------------


class TestParseFuturesOrder:
    def test_valid(self) -> None:
        result = parse_futures_order(_valid_futures_raw())
        assert isinstance(result, Ok)
        order = unwrap(result)
        assert isinstance(order.instrument_detail, FuturesDetail)

    def test_settlement_date_defaults_to_t_plus_0(self) -> None:
        raw = _valid_futures_raw()
        assert "settlement_date" not in raw
        order = unwrap(parse_futures_order(raw))
        from datetime import date
        assert order.settlement_date == date(2025, 6, 15)

    def test_missing_contract_size_err(self) -> None:
        raw = _valid_futures_raw()
        del raw["contract_size"]
        result = parse_futures_order(raw)
        assert isinstance(result, Err)

    def test_missing_settlement_type_err(self) -> None:
        raw = _valid_futures_raw()
        del raw["settlement_type"]
        result = parse_futures_order(raw)
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Backward compatibility: existing orders default to EquityDetail
# ---------------------------------------------------------------------------


class TestBackwardCompatibility:
    def test_existing_order_gets_equity_detail(self) -> None:
        from attestor.gateway.parser import parse_order

        raw: dict[str, object] = {
            "order_id": "ORD-001",
            "instrument_id": "AAPL",
            "side": "BUY",
            "quantity": "100",
            "price": "175.50",
            "currency": "USD",
            "order_type": "LIMIT",
            "counterparty_lei": _LEI_A,
            "executing_party_lei": _LEI_B,
            "trade_date": "2025-06-16",
            "settlement_date": "2025-06-18",
            "venue": "XNYS",
            "timestamp": datetime(2025, 6, 16, 10, 0, 0, tzinfo=UTC).isoformat(),
        }
        order = unwrap(parse_order(raw))
        assert isinstance(order.instrument_detail, EquityDetail)
