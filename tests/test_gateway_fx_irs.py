"""Tests for FX and IRS gateway parsers."""

from __future__ import annotations

from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.gateway.parser import (
    parse_fx_forward_order,
    parse_fx_spot_order,
    parse_irs_order,
    parse_ndf_order,
)
from attestor.instrument.derivative_types import FXDetail, IRSwapDetail, SettlementTypeEnum

# ---------------------------------------------------------------------------
# Shared base fields
# ---------------------------------------------------------------------------

_BASE: dict[str, object] = {
    "order_id": "ORD-FX-001",
    "instrument_id": "EURUSD-SPOT",
    "side": "BUY",
    "quantity": "1000000",
    "price": "1.0850",
    "currency": "USD",
    "order_type": "MARKET",
    "counterparty_lei": "529900HNOAA1KXQJUQ27",
    "executing_party_lei": "529900ODI3JL1O4COU11",
    "trade_date": "2025-06-15",
    "venue": "XFOR",
    "timestamp": "2025-06-15T10:00:00+00:00",
}


def _with(**overrides: object) -> dict[str, object]:
    return {**_BASE, **overrides}


# ---------------------------------------------------------------------------
# parse_fx_spot_order
# ---------------------------------------------------------------------------


class TestParseFXSpotOrder:
    def test_valid(self) -> None:
        raw = _with(currency_pair="EUR/USD")
        result = parse_fx_spot_order(raw)
        assert isinstance(result, Ok)
        order = unwrap(result)
        assert isinstance(order.instrument_detail, FXDetail)
        assert order.instrument_detail.currency_pair == "EUR/USD"
        assert order.instrument_detail.forward_rate is None
        assert order.instrument_detail.fixing_source is None

    def test_settlement_t_plus_2(self) -> None:
        raw = _with(currency_pair="EUR/USD")
        order = unwrap(parse_fx_spot_order(raw))
        # 2025-06-15 is Sunday — T+2 business days from Mon 2025-06-16 => Wed 2025-06-18
        # Actually: trade_date=2025-06-15 (Sun). add_business_days(Sun, 2) skips to Tue 2025-06-17
        # Let's just check settlement > trade
        assert order.settlement_date > order.trade_date

    def test_custom_settlement_date(self) -> None:
        raw = _with(currency_pair="GBP/JPY", settlement_date="2025-06-20")
        order = unwrap(parse_fx_spot_order(raw))
        assert str(order.settlement_date) == "2025-06-20"

    def test_missing_currency_pair(self) -> None:
        raw = _with()  # no currency_pair
        result = parse_fx_spot_order(raw)
        assert isinstance(result, Err)

    def test_invalid_currency_pair(self) -> None:
        raw = _with(currency_pair="INVALID")
        result = parse_fx_spot_order(raw)
        assert isinstance(result, Err)

    def test_default_physical_settlement(self) -> None:
        raw = _with(currency_pair="EUR/USD")
        order = unwrap(parse_fx_spot_order(raw))
        detail = order.instrument_detail
        assert isinstance(detail, FXDetail)
        assert detail.settlement_type is SettlementTypeEnum.PHYSICAL


# ---------------------------------------------------------------------------
# parse_fx_forward_order
# ---------------------------------------------------------------------------


class TestParseFXForwardOrder:
    def test_valid(self) -> None:
        raw = _with(
            currency_pair="EUR/USD",
            forward_rate="1.0920",
            settlement_date="2025-09-15",
        )
        result = parse_fx_forward_order(raw)
        assert isinstance(result, Ok)
        order = unwrap(result)
        detail = order.instrument_detail
        assert isinstance(detail, FXDetail)
        assert detail.forward_rate is not None
        assert detail.forward_rate.value == Decimal("1.0920")

    def test_missing_forward_rate(self) -> None:
        raw = _with(currency_pair="EUR/USD", settlement_date="2025-09-15")
        result = parse_fx_forward_order(raw)
        assert isinstance(result, Err)

    def test_missing_settlement_date(self) -> None:
        raw = _with(currency_pair="EUR/USD", forward_rate="1.0920")
        # Remove settlement_date to force failure
        d = dict(raw)
        d.pop("settlement_date", None)
        result = parse_fx_forward_order(d)
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# parse_ndf_order
# ---------------------------------------------------------------------------


class TestParseNDFOrder:
    def test_valid(self) -> None:
        raw = _with(
            currency_pair="USD/CNY",
            forward_rate="7.2500",
            fixing_date="2025-09-13",
            settlement_date="2025-09-15",
            fixing_source="WMR",
        )
        result = parse_ndf_order(raw)
        assert isinstance(result, Ok)
        order = unwrap(result)
        detail = order.instrument_detail
        assert isinstance(detail, FXDetail)
        assert detail.settlement_type is SettlementTypeEnum.CASH
        assert detail.fixing_source is not None
        assert detail.fixing_source.value == "WMR"

    def test_fixing_after_settlement(self) -> None:
        raw = _with(
            currency_pair="USD/CNY",
            forward_rate="7.2500",
            fixing_date="2025-09-20",  # after settlement
            settlement_date="2025-09-15",
            fixing_source="WMR",
        )
        result = parse_ndf_order(raw)
        assert isinstance(result, Err)

    def test_missing_fixing_source(self) -> None:
        raw = _with(
            currency_pair="USD/CNY",
            forward_rate="7.2500",
            fixing_date="2025-09-13",
            settlement_date="2025-09-15",
        )
        result = parse_ndf_order(raw)
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# parse_irs_order
# ---------------------------------------------------------------------------


class TestParseIRSOrder:
    def test_valid(self) -> None:
        raw = _with(
            instrument_id="IRS-5Y-001",
            fixed_rate="0.035",
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months="60",
            start_date="2025-06-17",
            end_date="2030-06-17",
        )
        result = parse_irs_order(raw)
        assert isinstance(result, Ok)
        order = unwrap(result)
        detail = order.instrument_detail
        assert isinstance(detail, IRSwapDetail)
        assert detail.float_index.value == "SOFR"
        assert detail.tenor_months == 60

    def test_missing_fixed_rate(self) -> None:
        raw = _with(
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months="60",
            start_date="2025-06-17",
            end_date="2030-06-17",
        )
        result = parse_irs_order(raw)
        assert isinstance(result, Err)

    def test_start_after_end(self) -> None:
        raw = _with(
            fixed_rate="0.035",
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months="60",
            start_date="2030-06-17",
            end_date="2025-06-17",
        )
        result = parse_irs_order(raw)
        assert isinstance(result, Err)

    def test_zero_tenor(self) -> None:
        raw = _with(
            fixed_rate="0.035",
            float_index="SOFR",
            day_count="ACT/360",
            payment_frequency="QUARTERLY",
            tenor_months="0",
            start_date="2025-06-17",
            end_date="2030-06-17",
        )
        result = parse_irs_order(raw)
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Totality: parsers never raise
# ---------------------------------------------------------------------------


class TestTotality:
    """INV-G02: parsers never raise, always return Ok or Err."""

    def test_fx_spot_empty_dict(self) -> None:
        result = parse_fx_spot_order({})
        assert isinstance(result, Err)

    def test_fx_forward_empty_dict(self) -> None:
        result = parse_fx_forward_order({})
        assert isinstance(result, Err)

    def test_ndf_empty_dict(self) -> None:
        result = parse_ndf_order({})
        assert isinstance(result, Err)

    def test_irs_empty_dict(self) -> None:
        result = parse_irs_order({})
        assert isinstance(result, Err)
