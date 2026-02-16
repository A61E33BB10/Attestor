"""Oracle credit ingestion -- CDS spreads, credit events, and auction results.

CDSSpreadQuote is the canonical CDS spread observation. CreditEventRecord and
AuctionResult cover post-event declarations and auction recovery prices.
Ingestion creates Attestation[T] with appropriate confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import final

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.instrument.derivative_types import CreditEventType
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    QuotedConfidence,
    create_attestation,
)

# ---------------------------------------------------------------------------
# CDSSpreadQuote
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class CDSSpreadQuote:
    """Observed CDS spread from the market."""

    reference_entity: NonEmptyStr
    tenor: Decimal
    spread_bps: Decimal
    recovery_rate: Decimal
    currency: NonEmptyStr
    timestamp: UtcDatetime


def ingest_cds_spread(
    reference_entity: str,
    tenor: Decimal,
    bid_bps: Decimal,
    ask_bps: Decimal,
    recovery_rate: Decimal,
    currency: str,
    venue: str,
    timestamp: datetime,
) -> Ok[Attestation[CDSSpreadQuote]] | Err[str]:
    """Ingest CDS spread quote with QuotedConfidence (bid/ask in bps).

    Validates:
    - reference_entity non-empty
    - tenor > 0
    - bid_bps > 0, ask_bps > 0
    - bid_bps <= ask_bps
    - 0 <= recovery_rate < 1
    - currency non-empty

    The mid spread (in bps) is stored as spread_bps.
    QuotedConfidence uses bid_bps and ask_bps.
    """
    match NonEmptyStr.parse(reference_entity):
        case Err(e):
            return Err(f"reference_entity: {e}")
        case Ok(ref):
            pass
    if not isinstance(tenor, Decimal) or not tenor.is_finite() or tenor <= 0:
        return Err(f"tenor must be positive finite Decimal, got {tenor}")
    if not isinstance(bid_bps, Decimal) or not bid_bps.is_finite() or bid_bps <= 0:
        return Err(f"bid_bps must be positive finite Decimal, got {bid_bps}")
    if not isinstance(ask_bps, Decimal) or not ask_bps.is_finite() or ask_bps <= 0:
        return Err(f"ask_bps must be positive finite Decimal, got {ask_bps}")
    if not isinstance(recovery_rate, Decimal) or not recovery_rate.is_finite():
        return Err(f"recovery_rate must be finite Decimal, got {recovery_rate}")
    if recovery_rate < 0:
        return Err(f"recovery_rate must be >= 0, got {recovery_rate}")
    if recovery_rate >= 1:
        return Err(f"recovery_rate must be < 1, got {recovery_rate}")
    match NonEmptyStr.parse(currency):
        case Err(e):
            return Err(f"currency: {e}")
        case Ok(cur):
            pass
    match UtcDatetime.parse(timestamp):
        case Err(e):
            return Err(f"timestamp: {e}")
        case Ok(ts):
            pass
    match QuotedConfidence.create(bid=bid_bps, ask=ask_bps, venue=venue):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = CDSSpreadQuote(
        reference_entity=ref,
        tenor=tenor,
        spread_bps=confidence.mid,
        recovery_rate=recovery_rate,
        currency=cur,
        timestamp=ts,
    )
    return create_attestation(
        value=point,
        confidence=confidence,
        source=venue,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# CreditEventRecord
# ---------------------------------------------------------------------------


def _parse_credit_event_type(raw: str) -> Ok[CreditEventType] | Err[str]:
    """Parse a string into CreditEventType without raising."""
    for member in CreditEventType:
        if member.value == raw:
            return Ok(member)
    valid = ", ".join(m.value for m in CreditEventType)
    return Err(f"invalid CreditEventType: {raw!r}, expected one of: {valid}")


@final
@dataclass(frozen=True, slots=True)
class CreditEventRecord:
    """Oracle record of a credit event declaration."""

    reference_entity: NonEmptyStr
    event_type: CreditEventType
    determination_date: date


def ingest_credit_event(
    reference_entity: str,
    event_type: str,
    determination_date: date,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[CreditEventRecord]] | Err[str]:
    """Ingest credit event declaration with FirmConfidence.

    Validates:
    - reference_entity non-empty
    - event_type is a valid CreditEventType value
    - source non-empty
    """
    match NonEmptyStr.parse(reference_entity):
        case Err(e):
            return Err(f"reference_entity: {e}")
        case Ok(ref):
            pass
    match _parse_credit_event_type(event_type):
        case Err(e):
            return Err(f"event_type: {e}")
        case Ok(evt):
            pass
    match NonEmptyStr.parse(source):
        case Err(e):
            return Err(f"source: {e}")
        case Ok(_):
            pass
    match UtcDatetime.parse(timestamp):
        case Err(e):
            return Err(f"timestamp: {e}")
        case Ok(_):
            pass
    match FirmConfidence.create(
        source=source, timestamp=timestamp, attestation_ref=attestation_ref,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = CreditEventRecord(
        reference_entity=ref,
        event_type=evt,
        determination_date=determination_date,
    )
    return create_attestation(
        value=point,
        confidence=confidence,
        source=source,
        timestamp=timestamp,
    )


# ---------------------------------------------------------------------------
# AuctionResult
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class AuctionResult:
    """Final auction price after a credit event."""

    reference_entity: NonEmptyStr
    event_type: CreditEventType
    determination_date: date
    auction_price: Decimal  # recovery price in [0, 1]


def ingest_auction_result(
    reference_entity: str,
    event_type: str,
    determination_date: date,
    auction_price: Decimal,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[AuctionResult]] | Err[str]:
    """Ingest auction result with FirmConfidence.

    Validation: 0 <= auction_price <= 1.
    """
    match NonEmptyStr.parse(reference_entity):
        case Err(e):
            return Err(f"reference_entity: {e}")
        case Ok(ref):
            pass
    match _parse_credit_event_type(event_type):
        case Err(e):
            return Err(f"event_type: {e}")
        case Ok(evt):
            pass
    if not isinstance(auction_price, Decimal) or not auction_price.is_finite():
        return Err(f"auction_price must be finite Decimal, got {auction_price}")
    if auction_price < 0:
        return Err(f"auction_price must be >= 0, got {auction_price}")
    if auction_price > 1:
        return Err(f"auction_price must be <= 1, got {auction_price}")
    match NonEmptyStr.parse(source):
        case Err(e):
            return Err(f"source: {e}")
        case Ok(_):
            pass
    match UtcDatetime.parse(timestamp):
        case Err(e):
            return Err(f"timestamp: {e}")
        case Ok(_):
            pass
    match FirmConfidence.create(
        source=source, timestamp=timestamp, attestation_ref=attestation_ref,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = AuctionResult(
        reference_entity=ref,
        event_type=evt,
        determination_date=determination_date,
        auction_price=auction_price,
    )
    return create_attestation(
        value=point,
        confidence=confidence,
        source=source,
        timestamp=timestamp,
    )
