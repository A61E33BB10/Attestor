"""Tests for attestor.oracle.fx_ingest — FX rate and rate fixing ingestion."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from attestor.core.result import Err, Ok, unwrap
from attestor.oracle.attestation import FirmConfidence, QuotedConfidence
from attestor.oracle.fx_ingest import (
    FXRate,
    RateFixing,
    ingest_fx_rate,
    ingest_fx_rate_firm,
    ingest_rate_fixing,
)

_TS = datetime(2025, 6, 15, 14, 30, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# FXRate type
# ---------------------------------------------------------------------------


class TestFXRate:
    def test_frozen(self) -> None:
        r = unwrap(ingest_fx_rate(
            currency_pair="EUR/USD", bid=Decimal("1.0840"), ask=Decimal("1.0860"),
            venue="XFOR", timestamp=_TS,
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.value.rate = None  # type: ignore[misc]


class TestRateFixing:
    def test_frozen(self) -> None:
        r = unwrap(ingest_rate_fixing(
            index_name="SOFR", rate=Decimal("0.053"),
            fixing_date=date(2025, 6, 15), source="FED",
            timestamp=_TS, attestation_ref="FED-2025-06-15",
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            r.value.rate = Decimal("0")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ingest_fx_rate (Quoted)
# ---------------------------------------------------------------------------


class TestIngestFXRate:
    def test_valid_quote(self) -> None:
        result = ingest_fx_rate(
            currency_pair="EUR/USD",
            bid=Decimal("1.0840"),
            ask=Decimal("1.0860"),
            venue="XFOR",
            timestamp=_TS,
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, FXRate)
        assert att.value.currency_pair.value == "EUR/USD"
        assert att.value.rate.value == Decimal("1.0850")  # mid

    def test_quoted_confidence(self) -> None:
        att = unwrap(ingest_fx_rate(
            currency_pair="GBP/JPY",
            bid=Decimal("195.50"),
            ask=Decimal("195.60"),
            venue="XLON",
            timestamp=_TS,
        ))
        assert isinstance(att.confidence, QuotedConfidence)

    def test_content_hash_populated(self) -> None:
        att = unwrap(ingest_fx_rate(
            currency_pair="EUR/USD",
            bid=Decimal("1.0840"),
            ask=Decimal("1.0860"),
            venue="XFOR",
            timestamp=_TS,
        ))
        assert att.content_hash != ""

    def test_invalid_currency_pair(self) -> None:
        result = ingest_fx_rate(
            currency_pair="INVALID",
            bid=Decimal("1.0840"),
            ask=Decimal("1.0860"),
            venue="XFOR",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_bid_greater_than_ask(self) -> None:
        result = ingest_fx_rate(
            currency_pair="EUR/USD",
            bid=Decimal("1.09"),
            ask=Decimal("1.08"),
            venue="XFOR",
            timestamp=_TS,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# ingest_fx_rate_firm
# ---------------------------------------------------------------------------


class TestIngestFXRateFirm:
    def test_valid(self) -> None:
        result = ingest_fx_rate_firm(
            currency_pair="EUR/USD",
            rate=Decimal("1.0850"),
            source="ECB",
            timestamp=_TS,
            attestation_ref="ECB-FX-2025-06-15",
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, FXRate)
        assert att.value.rate.value == Decimal("1.0850")
        assert isinstance(att.confidence, FirmConfidence)

    def test_zero_rate_err(self) -> None:
        result = ingest_fx_rate_firm(
            currency_pair="EUR/USD",
            rate=Decimal("0"),
            source="ECB",
            timestamp=_TS,
            attestation_ref="ECB-FX-2025-06-15",
        )
        assert isinstance(result, Err)

    def test_invalid_pair(self) -> None:
        result = ingest_fx_rate_firm(
            currency_pair="XX/YY",
            rate=Decimal("1.0850"),
            source="ECB",
            timestamp=_TS,
            attestation_ref="ECB-FX-2025-06-15",
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# ingest_rate_fixing
# ---------------------------------------------------------------------------


class TestIngestRateFixing:
    def test_valid_sofr(self) -> None:
        result = ingest_rate_fixing(
            index_name="SOFR",
            rate=Decimal("0.053"),
            fixing_date=date(2025, 6, 15),
            source="FED",
            timestamp=_TS,
            attestation_ref="FED-SOFR-2025-06-15",
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, RateFixing)
        assert att.value.index_name.value == "SOFR"
        assert att.value.rate == Decimal("0.053")

    def test_negative_rate_allowed(self) -> None:
        """Negative interest rates (e.g. ECB deposit rate) are valid."""
        result = ingest_rate_fixing(
            index_name="EURIBOR_3M",
            rate=Decimal("-0.005"),
            fixing_date=date(2025, 6, 15),
            source="ECB",
            timestamp=_TS,
            attestation_ref="ECB-EURIBOR-2025-06-15",
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert att.value.rate == Decimal("-0.005")

    def test_firm_confidence(self) -> None:
        att = unwrap(ingest_rate_fixing(
            index_name="SOFR",
            rate=Decimal("0.053"),
            fixing_date=date(2025, 6, 15),
            source="FED",
            timestamp=_TS,
            attestation_ref="FED-SOFR-2025-06-15",
        ))
        assert isinstance(att.confidence, FirmConfidence)

    def test_empty_index_name(self) -> None:
        result = ingest_rate_fixing(
            index_name="",
            rate=Decimal("0.053"),
            fixing_date=date(2025, 6, 15),
            source="FED",
            timestamp=_TS,
            attestation_ref="FED-SOFR-2025-06-15",
        )
        assert isinstance(result, Err)

    def test_nan_rate(self) -> None:
        result = ingest_rate_fixing(
            index_name="SOFR",
            rate=Decimal("NaN"),
            fixing_date=date(2025, 6, 15),
            source="FED",
            timestamp=_TS,
            attestation_ref="FED-SOFR-2025-06-15",
        )
        assert isinstance(result, Err)
