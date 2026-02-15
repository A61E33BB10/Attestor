"""Oracle equity ingestion — ingest exchange fills and market quotes as Attestations.

MarketDataPoint is the canonical equity price observation. Ingestion creates
Attestation[MarketDataPoint] with the appropriate confidence type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import final

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    QuotedConfidence,
    create_attestation,
)


@final
@dataclass(frozen=True, slots=True)
class MarketDataPoint:
    """A single equity price observation."""

    instrument_id: NonEmptyStr
    price: Decimal
    currency: NonEmptyStr
    timestamp: UtcDatetime


def ingest_equity_fill(
    instrument_id: str,
    price: Decimal,
    currency: str,
    exchange: str,
    timestamp: datetime,
    exchange_ref: str,
) -> Ok[Attestation[MarketDataPoint]] | Err[str]:
    """Ingest an exchange fill as a Firm attestation."""
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"instrument_id: {e}")
        case Ok(iid):
            pass
    if not isinstance(price, Decimal) or not price.is_finite() or price <= 0:
        return Err(f"price must be positive finite Decimal, got {price}")
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
    match FirmConfidence.create(
        source=exchange, timestamp=timestamp, attestation_ref=exchange_ref,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = MarketDataPoint(instrument_id=iid, price=price, currency=cur, timestamp=ts)
    return create_attestation(
        value=point,
        confidence=confidence,
        source=exchange,
        timestamp=timestamp,
    )


def ingest_equity_quote(
    instrument_id: str,
    bid: Decimal,
    ask: Decimal,
    currency: str,
    venue: str,
    timestamp: datetime,
) -> Ok[Attestation[MarketDataPoint]] | Err[str]:
    """Ingest a market quote as a Quoted attestation (mid price)."""
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"instrument_id: {e}")
        case Ok(iid):
            pass
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
    match QuotedConfidence.create(bid=bid, ask=ask, venue=venue):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = MarketDataPoint(
        instrument_id=iid, price=confidence.mid, currency=cur, timestamp=ts,
    )
    return create_attestation(
        value=point,
        confidence=confidence,
        source=venue,
        timestamp=timestamp,
    )
