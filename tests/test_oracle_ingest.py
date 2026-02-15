"""Tests for attestor.oracle.ingest — equity fill and quote ingestion."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from attestor.core.result import Err, Ok
from attestor.oracle.attestation import FirmConfidence, QuotedConfidence
from attestor.oracle.ingest import ingest_equity_fill, ingest_equity_quote

_TS = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# Firm attestation from fill
# ---------------------------------------------------------------------------


class TestIngestEquityFill:
    def test_valid_fill(self) -> None:
        result = ingest_equity_fill(
            instrument_id="AAPL", price=Decimal("175.50"),
            currency="USD", exchange="XNYS",
            timestamp=_TS, exchange_ref="FILL-12345",
        )
        assert isinstance(result, Ok)
        att = result.value
        assert att.value.instrument_id.value == "AAPL"
        assert att.value.price == Decimal("175.50")
        assert att.value.currency.value == "USD"
        assert isinstance(att.confidence, FirmConfidence)
        assert att.source.value == "XNYS"

    def test_content_hash_stable(self) -> None:
        a1 = ingest_equity_fill(
            "AAPL", Decimal("175.50"), "USD", "XNYS", _TS, "FILL-001",
        )
        a2 = ingest_equity_fill(
            "AAPL", Decimal("175.50"), "USD", "XNYS", _TS, "FILL-001",
        )
        assert isinstance(a1, Ok) and isinstance(a2, Ok)
        assert a1.value.content_hash == a2.value.content_hash

    def test_attestation_id_differs_for_different_sources(self) -> None:
        """GAP-01: different sources → different attestation_id."""
        a1 = ingest_equity_fill(
            "AAPL", Decimal("175.50"), "USD", "XNYS", _TS, "FILL-001",
        )
        a2 = ingest_equity_fill(
            "AAPL", Decimal("175.50"), "USD", "XNAS", _TS, "FILL-002",
        )
        assert isinstance(a1, Ok) and isinstance(a2, Ok)
        assert a1.value.attestation_id != a2.value.attestation_id

    def test_negative_price_rejected(self) -> None:
        result = ingest_equity_fill(
            "AAPL", Decimal("-10"), "USD", "XNYS", _TS, "FILL-003",
        )
        assert isinstance(result, Err)

    def test_zero_price_rejected(self) -> None:
        result = ingest_equity_fill(
            "AAPL", Decimal("0"), "USD", "XNYS", _TS, "FILL-004",
        )
        assert isinstance(result, Err)

    def test_empty_instrument_rejected(self) -> None:
        result = ingest_equity_fill(
            "", Decimal("100"), "USD", "XNYS", _TS, "FILL-005",
        )
        assert isinstance(result, Err)

    def test_naive_timestamp_rejected(self) -> None:
        result = ingest_equity_fill(
            "AAPL", Decimal("100"), "USD", "XNYS",
            datetime(2025, 6, 15, 10, 0, 0),  # naive — no tzinfo
            "FILL-006",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# Quoted attestation from quote
# ---------------------------------------------------------------------------


class TestIngestEquityQuote:
    def test_valid_quote(self) -> None:
        result = ingest_equity_quote(
            instrument_id="AAPL", bid=Decimal("175.00"), ask=Decimal("176.00"),
            currency="USD", venue="XNYS", timestamp=_TS,
        )
        assert isinstance(result, Ok)
        att = result.value
        assert att.value.price == Decimal("175.5")  # mid
        assert isinstance(att.confidence, QuotedConfidence)

    def test_mid_price_computed(self) -> None:
        result = ingest_equity_quote(
            "AAPL", bid=Decimal("100"), ask=Decimal("102"),
            currency="USD", venue="XNYS", timestamp=_TS,
        )
        assert isinstance(result, Ok)
        assert result.value.value.price == Decimal("101")

    def test_bid_greater_than_ask_rejected(self) -> None:
        result = ingest_equity_quote(
            "AAPL", bid=Decimal("200"), ask=Decimal("100"),
            currency="USD", venue="XNYS", timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_empty_venue_rejected(self) -> None:
        result = ingest_equity_quote(
            "AAPL", bid=Decimal("100"), ask=Decimal("102"),
            currency="USD", venue="", timestamp=_TS,
        )
        assert isinstance(result, Err)
