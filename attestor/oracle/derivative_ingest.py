"""Oracle derivative ingestion — option quotes and futures settlement prices.

OptionQuote uses QuotedConfidence (bid/ask spread).
FuturesSettlement uses FirmConfidence (exchange official settlement).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import final

from attestor.core.money import NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.types import UtcDatetime
from attestor.instrument.derivative_types import OptionTypeEnum
from attestor.oracle.attestation import (
    Attestation,
    FirmConfidence,
    QuotedConfidence,
    create_attestation,
)


@final
@dataclass(frozen=True, slots=True)
class OptionQuote:
    """Option price observation with optional implied volatility."""

    instrument_id: NonEmptyStr
    underlying_id: NonEmptyStr
    strike: Decimal
    expiry_date: date
    option_type: OptionTypeEnum
    bid: Decimal
    ask: Decimal
    implied_vol_bid: Decimal | None
    implied_vol_ask: Decimal | None
    currency: NonEmptyStr
    timestamp: UtcDatetime


@final
@dataclass(frozen=True, slots=True)
class FuturesSettlement:
    """Exchange official futures settlement price."""

    instrument_id: NonEmptyStr
    settlement_price: Decimal
    currency: NonEmptyStr
    settlement_date: date
    timestamp: UtcDatetime


def ingest_option_quote(
    instrument_id: str,
    underlying_id: str,
    strike: Decimal,
    expiry_date: date,
    option_type: OptionTypeEnum,
    bid: Decimal,
    ask: Decimal,
    currency: str,
    venue: str,
    timestamp: datetime,
    implied_vol_bid: Decimal | None = None,
    implied_vol_ask: Decimal | None = None,
) -> Ok[Attestation[OptionQuote]] | Err[str]:
    """Ingest an option quote as a Quoted attestation."""
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"instrument_id: {e}")
        case Ok(iid):
            pass
    match NonEmptyStr.parse(underlying_id):
        case Err(e):
            return Err(f"underlying_id: {e}")
        case Ok(uid):
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

    quote = OptionQuote(
        instrument_id=iid, underlying_id=uid, strike=strike,
        expiry_date=expiry_date, option_type=option_type,
        bid=bid, ask=ask,
        implied_vol_bid=implied_vol_bid,
        implied_vol_ask=implied_vol_ask,
        currency=cur, timestamp=ts,
    )
    return create_attestation(
        value=quote, confidence=confidence,
        source=venue, timestamp=timestamp,
    )


def ingest_futures_settlement(
    instrument_id: str,
    settlement_price: Decimal,
    currency: str,
    settlement_date: date,
    exchange: str,
    timestamp: datetime,
    exchange_ref: str,
) -> Ok[Attestation[FuturesSettlement]] | Err[str]:
    """Ingest a futures settlement price as a Firm attestation."""
    match NonEmptyStr.parse(instrument_id):
        case Err(e):
            return Err(f"instrument_id: {e}")
        case Ok(iid):
            pass
    if (
        not isinstance(settlement_price, Decimal)
        or not settlement_price.is_finite()
        or settlement_price <= 0
    ):
        return Err(
            f"settlement_price must be positive finite Decimal, "
            f"got {settlement_price}"
        )
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
        source=exchange, timestamp=timestamp,
        attestation_ref=exchange_ref,
    ):
        case Err(e):
            return Err(f"confidence: {e}")
        case Ok(confidence):
            pass

    settlement = FuturesSettlement(
        instrument_id=iid, settlement_price=settlement_price,
        currency=cur, settlement_date=settlement_date, timestamp=ts,
    )
    return create_attestation(
        value=settlement, confidence=confidence,
        source=exchange, timestamp=timestamp,
    )
