"""Oracle FX and rate fixing ingestion — ingest FX rates and official fixings.

FXRate is the canonical FX price observation. RateFixing covers official fixings
(SOFR, EURIBOR, etc.). Ingestion creates Attestation[T] with appropriate confidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import final

from attestor.core.money import CurrencyPair, NonEmptyStr, PositiveDecimal
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
class FXRate:
    """Observed FX rate for a currency pair."""

    currency_pair: CurrencyPair
    rate: PositiveDecimal
    timestamp: UtcDatetime


@final
@dataclass(frozen=True, slots=True)
class RateFixing:
    """Official rate fixing (e.g. SOFR, EURIBOR)."""

    index_name: NonEmptyStr
    rate: Decimal  # can be negative (negative interest rates)
    fixing_date: date
    source: NonEmptyStr
    timestamp: UtcDatetime


def ingest_fx_rate(
    currency_pair: str,
    bid: Decimal,
    ask: Decimal,
    venue: str,
    timestamp: datetime,
) -> Ok[Attestation[FXRate]] | Err[str]:
    """Ingest FX rate quote with QuotedConfidence (mid price)."""
    match CurrencyPair.parse(currency_pair):
        case Err(e):
            return Err(f"currency_pair: {e}")
        case Ok(cp):
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
    match PositiveDecimal.parse(confidence.mid):
        case Err(e):
            return Err(f"mid rate: {e}")
        case Ok(rate):
            pass

    point = FXRate(currency_pair=cp, rate=rate, timestamp=ts)
    return create_attestation(
        value=point,
        confidence=confidence,
        source=venue,
        timestamp=timestamp,
    )


def ingest_fx_rate_firm(
    currency_pair: str,
    rate: Decimal,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[FXRate]] | Err[str]:
    """Ingest firm FX rate (e.g. ECB fixing) with FirmConfidence."""
    match CurrencyPair.parse(currency_pair):
        case Err(e):
            return Err(f"currency_pair: {e}")
        case Ok(cp):
            pass
    match PositiveDecimal.parse(rate):
        case Err(e):
            return Err(f"rate: {e}")
        case Ok(r):
            pass
    match UtcDatetime.parse(timestamp):
        case Err(e):
            return Err(f"timestamp: {e}")
        case Ok(ts):
            pass
    match FirmConfidence.create(
        source=source, timestamp=timestamp, attestation_ref=attestation_ref,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = FXRate(currency_pair=cp, rate=r, timestamp=ts)
    return create_attestation(
        value=point,
        confidence=confidence,
        source=source,
        timestamp=timestamp,
    )


def ingest_rate_fixing(
    index_name: str,
    rate: Decimal,
    fixing_date: date,
    source: str,
    timestamp: datetime,
    attestation_ref: str,
) -> Ok[Attestation[RateFixing]] | Err[str]:
    """Ingest official rate fixing with FirmConfidence."""
    match NonEmptyStr.parse(index_name):
        case Err(e):
            return Err(f"index_name: {e}")
        case Ok(idx):
            pass
    if not isinstance(rate, Decimal) or not rate.is_finite():
        return Err(f"rate must be finite Decimal, got {rate}")
    match NonEmptyStr.parse(source):
        case Err(e):
            return Err(f"source: {e}")
        case Ok(src):
            pass
    match UtcDatetime.parse(timestamp):
        case Err(e):
            return Err(f"timestamp: {e}")
        case Ok(ts):
            pass
    match FirmConfidence.create(
        source=source, timestamp=timestamp, attestation_ref=attestation_ref,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    point = RateFixing(
        index_name=idx, rate=rate, fixing_date=fixing_date,
        source=src, timestamp=ts,
    )
    return create_attestation(
        value=point,
        confidence=confidence,
        source=source,
        timestamp=timestamp,
    )
