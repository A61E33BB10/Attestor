"""Tests for attestor.oracle.credit_ingest -- CDS spread, credit event, auction result."""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from attestor.core.result import Err, Ok, unwrap
from attestor.oracle.attestation import FirmConfidence, QuotedConfidence
from attestor.oracle.credit_ingest import (
    AuctionResult,
    CDSSpreadQuote,
    CreditEventRecord,
    ingest_auction_result,
    ingest_cds_spread,
    ingest_credit_event,
)

_TS = datetime(2025, 7, 1, 10, 0, 0, tzinfo=UTC)


# ---------------------------------------------------------------------------
# ingest_cds_spread
# ---------------------------------------------------------------------------


class TestIngestCDSSpread:
    def test_valid_ok_with_quoted_confidence(self) -> None:
        result = ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, CDSSpreadQuote)
        assert att.value.reference_entity.value == "ACME Corp"
        assert att.value.tenor == Decimal("5")
        assert att.value.spread_bps == Decimal("105")  # mid of 100/110
        assert att.value.recovery_rate == Decimal("0.4")
        assert att.value.currency.value == "USD"
        assert isinstance(att.confidence, QuotedConfidence)

    def test_bid_greater_than_ask_err(self) -> None:
        result = ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("120"),
            ask_bps=Decimal("100"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_negative_spread_err(self) -> None:
        result = ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("-10"),
            ask_bps=Decimal("100"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_zero_tenor_err(self) -> None:
        result = ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("0"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_recovery_rate_ge_1_err(self) -> None:
        result = ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("1"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        )
        assert isinstance(result, Err)

    def test_recovery_rate_negative_err(self) -> None:
        result = ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("-0.1"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        )
        assert isinstance(result, Err)


class TestCDSSpreadQuoteFrozen:
    def test_immutable(self) -> None:
        att = unwrap(ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            att.value.tenor = Decimal("10")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ingest_credit_event
# ---------------------------------------------------------------------------


class TestIngestCreditEvent:
    def test_valid_ok_with_firm_confidence(self) -> None:
        result = ingest_credit_event(
            reference_entity="ACME Corp",
            event_type="Bankruptcy",
            determination_date=date(2025, 7, 1),
            source="ISDA",
            timestamp=_TS,
            attestation_ref="ISDA-CE-2025-001",
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, CreditEventRecord)
        assert att.value.reference_entity.value == "ACME Corp"
        assert att.value.event_type.value == "Bankruptcy"
        assert att.value.determination_date == date(2025, 7, 1)
        assert isinstance(att.confidence, FirmConfidence)

    def test_invalid_event_type_err(self) -> None:
        result = ingest_credit_event(
            reference_entity="ACME Corp",
            event_type="ALIEN_INVASION",
            determination_date=date(2025, 7, 1),
            source="ISDA",
            timestamp=_TS,
            attestation_ref="ISDA-CE-2025-002",
        )
        assert isinstance(result, Err)

    def test_empty_reference_entity_err(self) -> None:
        result = ingest_credit_event(
            reference_entity="",
            event_type="FailureToPay",
            determination_date=date(2025, 7, 1),
            source="ISDA",
            timestamp=_TS,
            attestation_ref="ISDA-CE-2025-003",
        )
        assert isinstance(result, Err)


class TestCreditEventRecordFrozen:
    def test_immutable(self) -> None:
        att = unwrap(ingest_credit_event(
            reference_entity="ACME Corp",
            event_type="Restructuring",
            determination_date=date(2025, 7, 1),
            source="ISDA",
            timestamp=_TS,
            attestation_ref="ISDA-CE-2025-004",
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            att.value.event_type = None  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ingest_auction_result
# ---------------------------------------------------------------------------


class TestIngestAuctionResult:
    def test_valid_ok_with_firm_confidence(self) -> None:
        result = ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="Bankruptcy",
            determination_date=date(2025, 7, 1),
            auction_price=Decimal("0.35"),
            source="Creditex",
            timestamp=_TS,
            attestation_ref="CX-AUC-2025-001",
        )
        assert isinstance(result, Ok)
        att = unwrap(result)
        assert isinstance(att.value, AuctionResult)
        assert att.value.auction_price == Decimal("0.35")
        assert isinstance(att.confidence, FirmConfidence)

    def test_price_greater_than_1_err(self) -> None:
        result = ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="Bankruptcy",
            determination_date=date(2025, 7, 1),
            auction_price=Decimal("1.01"),
            source="Creditex",
            timestamp=_TS,
            attestation_ref="CX-AUC-2025-002",
        )
        assert isinstance(result, Err)

    def test_price_negative_err(self) -> None:
        result = ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="Bankruptcy",
            determination_date=date(2025, 7, 1),
            auction_price=Decimal("-0.01"),
            source="Creditex",
            timestamp=_TS,
            attestation_ref="CX-AUC-2025-003",
        )
        assert isinstance(result, Err)

    def test_invalid_event_type_err(self) -> None:
        result = ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="NONSENSE",
            determination_date=date(2025, 7, 1),
            auction_price=Decimal("0.5"),
            source="Creditex",
            timestamp=_TS,
            attestation_ref="CX-AUC-2025-004",
        )
        assert isinstance(result, Err)


class TestAuctionResultFrozen:
    def test_immutable(self) -> None:
        att = unwrap(ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="FailureToPay",
            determination_date=date(2025, 7, 1),
            auction_price=Decimal("0.25"),
            source="Creditex",
            timestamp=_TS,
            attestation_ref="CX-AUC-2025-005",
        ))
        with pytest.raises(dataclasses.FrozenInstanceError):
            att.value.auction_price = Decimal("0.99")  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cross-cutting: content_hash and provenance
# ---------------------------------------------------------------------------


class TestAttestationMetadata:
    def test_cds_spread_has_content_hash(self) -> None:
        att = unwrap(ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        ))
        assert att.content_hash != ""
        assert isinstance(att.content_hash, str)

    def test_credit_event_has_content_hash(self) -> None:
        att = unwrap(ingest_credit_event(
            reference_entity="ACME Corp",
            event_type="Bankruptcy",
            determination_date=date(2025, 7, 1),
            source="ISDA",
            timestamp=_TS,
            attestation_ref="ISDA-CE-2025-010",
        ))
        assert att.content_hash != ""
        assert isinstance(att.content_hash, str)

    def test_auction_result_has_content_hash(self) -> None:
        att = unwrap(ingest_auction_result(
            reference_entity="ACME Corp",
            event_type="Bankruptcy",
            determination_date=date(2025, 7, 1),
            auction_price=Decimal("0.35"),
            source="Creditex",
            timestamp=_TS,
            attestation_ref="CX-AUC-2025-010",
        ))
        assert att.content_hash != ""
        assert isinstance(att.content_hash, str)

    def test_provenance_is_tuple(self) -> None:
        att = unwrap(ingest_cds_spread(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            bid_bps=Decimal("100"),
            ask_bps=Decimal("110"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            venue="ICE",
            timestamp=_TS,
        ))
        assert isinstance(att.provenance, tuple)


# ---------------------------------------------------------------------------
# CDSSpreadQuote.create smart constructor (Phase 5 D1)
# ---------------------------------------------------------------------------


class TestCDSSpreadQuoteCreate:
    """CDSSpreadQuote.create validates all fields."""

    def test_valid_ok(self) -> None:
        from attestor.core.types import UtcDatetime
        ts = UtcDatetime(value=_TS)
        result = CDSSpreadQuote.create(
            reference_entity="ACME Corp",
            tenor=Decimal("5"),
            spread_bps=Decimal("100"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            timestamp=ts,
        )
        assert isinstance(result, Ok)
        q = unwrap(result)
        assert q.reference_entity.value == "ACME Corp"
        assert q.tenor == Decimal("5")

    def test_empty_entity_err(self) -> None:
        from attestor.core.types import UtcDatetime
        ts = UtcDatetime(value=_TS)
        result = CDSSpreadQuote.create(
            reference_entity="",
            tenor=Decimal("5"),
            spread_bps=Decimal("100"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            timestamp=ts,
        )
        assert isinstance(result, Err)

    def test_zero_tenor_err(self) -> None:
        from attestor.core.types import UtcDatetime
        ts = UtcDatetime(value=_TS)
        result = CDSSpreadQuote.create(
            reference_entity="ACME",
            tenor=Decimal("0"),
            spread_bps=Decimal("100"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            timestamp=ts,
        )
        assert isinstance(result, Err)

    def test_negative_spread_err(self) -> None:
        from attestor.core.types import UtcDatetime
        ts = UtcDatetime(value=_TS)
        result = CDSSpreadQuote.create(
            reference_entity="ACME",
            tenor=Decimal("5"),
            spread_bps=Decimal("-10"),
            recovery_rate=Decimal("0.4"),
            currency="USD",
            timestamp=ts,
        )
        assert isinstance(result, Err)


# ---------------------------------------------------------------------------
# AuctionResult.create smart constructor (Phase 5 D1)
# ---------------------------------------------------------------------------


class TestAuctionResultCreate:
    """AuctionResult.create validates auction_price in [0, 1]."""

    def test_valid_ok(self) -> None:
        from attestor.instrument.derivative_types import CreditEventTypeEnum
        result = AuctionResult.create(
            reference_entity="ACME Corp",
            event_type=CreditEventTypeEnum.BANKRUPTCY,
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("0.35"),
        )
        assert isinstance(result, Ok)
        ar = unwrap(result)
        assert ar.auction_price == Decimal("0.35")

    def test_price_above_one_err(self) -> None:
        from attestor.instrument.derivative_types import CreditEventTypeEnum
        result = AuctionResult.create(
            reference_entity="ACME Corp",
            event_type=CreditEventTypeEnum.BANKRUPTCY,
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("1.5"),
        )
        assert isinstance(result, Err)

    def test_price_negative_err(self) -> None:
        from attestor.instrument.derivative_types import CreditEventTypeEnum
        result = AuctionResult.create(
            reference_entity="ACME Corp",
            event_type=CreditEventTypeEnum.BANKRUPTCY,
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("-0.1"),
        )
        assert isinstance(result, Err)

    def test_price_one_ok(self) -> None:
        from attestor.instrument.derivative_types import CreditEventTypeEnum
        result = AuctionResult.create(
            reference_entity="ACME Corp",
            event_type=CreditEventTypeEnum.BANKRUPTCY,
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("1"),
        )
        assert isinstance(result, Ok)

    def test_price_zero_ok(self) -> None:
        from attestor.instrument.derivative_types import CreditEventTypeEnum
        result = AuctionResult.create(
            reference_entity="ACME Corp",
            event_type=CreditEventTypeEnum.BANKRUPTCY,
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("0"),
        )
        assert isinstance(result, Ok)

    def test_empty_entity_err(self) -> None:
        from attestor.instrument.derivative_types import CreditEventTypeEnum
        result = AuctionResult.create(
            reference_entity="",
            event_type=CreditEventTypeEnum.BANKRUPTCY,
            determination_date=date(2025, 8, 1),
            auction_price=Decimal("0.35"),
        )
        assert isinstance(result, Err)
