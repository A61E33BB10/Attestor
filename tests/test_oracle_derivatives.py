"""Tests for attestor.oracle.derivative_ingest — option quotes, futures."""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

from attestor.core.result import Err, Ok, unwrap
from attestor.instrument.derivative_types import OptionTypeEnum
from attestor.oracle.derivative_ingest import (
    FuturesSettlement,
    OptionQuote,
    ingest_futures_settlement,
    ingest_option_quote,
)

_TS = datetime(2025, 6, 15, 10, 0, 0, tzinfo=UTC)


class TestIngestOptionQuote:
    def test_valid(self) -> None:
        result = ingest_option_quote(
            instrument_id="AAPL251219C00150000",
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL,
            bid=Decimal("5.00"), ask=Decimal("5.50"),
            currency="USD", venue="CBOE", timestamp=_TS,
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, OptionQuote)
        assert att.value.bid == Decimal("5.00")

    def test_with_implied_vol(self) -> None:
        result = ingest_option_quote(
            instrument_id="AAPL251219C00150000",
            underlying_id="AAPL", strike=Decimal("150"),
            expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL,
            bid=Decimal("5.00"), ask=Decimal("5.50"),
            currency="USD", venue="CBOE", timestamp=_TS,
            implied_vol_bid=Decimal("0.25"),
            implied_vol_ask=Decimal("0.27"),
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert att.value.implied_vol_bid == Decimal("0.25")

    def test_empty_instrument_err(self) -> None:
        result = ingest_option_quote(
            instrument_id="", underlying_id="AAPL",
            strike=Decimal("150"), expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL,
            bid=Decimal("5.00"), ask=Decimal("5.50"),
            currency="USD", venue="CBOE", timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_empty_underlying_err(self) -> None:
        result = ingest_option_quote(
            instrument_id="OPT-1", underlying_id="",
            strike=Decimal("150"), expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL,
            bid=Decimal("5.00"), ask=Decimal("5.50"),
            currency="USD", venue="CBOE", timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_naive_timestamp_err(self) -> None:
        result = ingest_option_quote(
            instrument_id="OPT-1", underlying_id="AAPL",
            strike=Decimal("150"), expiry_date=date(2025, 12, 19),
            option_type=OptionTypeEnum.CALL,
            bid=Decimal("5.00"), ask=Decimal("5.50"),
            currency="USD", venue="CBOE",
            timestamp=datetime(2025, 6, 15, 10, 0, 0),  # naive
        )
        assert isinstance(result, Err)


class TestIngestFuturesSettlement:
    def test_valid(self) -> None:
        result = ingest_futures_settlement(
            instrument_id="ESZ5", settlement_price=Decimal("5200"),
            currency="USD", settlement_date=date(2025, 6, 15),
            exchange="CME", timestamp=_TS, exchange_ref="CME-ESZ5-20250615",
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, FuturesSettlement)
        assert att.value.settlement_price == Decimal("5200")

    def test_zero_price_err(self) -> None:
        result = ingest_futures_settlement(
            instrument_id="ESZ5", settlement_price=Decimal("0"),
            currency="USD", settlement_date=date(2025, 6, 15),
            exchange="CME", timestamp=_TS, exchange_ref="REF-1",
        )
        assert isinstance(result, Err)

    def test_negative_price_err(self) -> None:
        result = ingest_futures_settlement(
            instrument_id="ESZ5", settlement_price=Decimal("-100"),
            currency="USD", settlement_date=date(2025, 6, 15),
            exchange="CME", timestamp=_TS, exchange_ref="REF-1",
        )
        assert isinstance(result, Err)

    def test_empty_instrument_err(self) -> None:
        result = ingest_futures_settlement(
            instrument_id="", settlement_price=Decimal("5200"),
            currency="USD", settlement_date=date(2025, 6, 15),
            exchange="CME", timestamp=_TS, exchange_ref="REF-1",
        )
        assert isinstance(result, Err)
