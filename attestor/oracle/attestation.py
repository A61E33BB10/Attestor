"""Attestation and Confidence types — epistemic payloads for observed values.

Attestation[T] wraps any value with provenance, confidence, and content-addressed
identity (content_hash for value identity, attestation_id for full identity).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, localcontext
from enum import Enum
from typing import final

from attestor.core.money import ATTESTOR_DECIMAL_CONTEXT, NonEmptyStr
from attestor.core.result import Err, Ok
from attestor.core.serialization import content_hash
from attestor.core.types import FrozenMap, UtcDatetime

# ---------------------------------------------------------------------------
# QuoteCondition enum (GAP-32)
# ---------------------------------------------------------------------------


class QuoteCondition(Enum):
    """Market condition under which a quote was observed."""

    INDICATIVE = "Indicative"
    FIRM = "Firm"
    RFQ = "RFQ"


# ---------------------------------------------------------------------------
# FirmConfidence (GAP-12, GAP-20)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class FirmConfidence:
    """Confidence from a firm, exchange-quality source."""

    source: NonEmptyStr
    timestamp: UtcDatetime
    attestation_ref: NonEmptyStr

    @staticmethod
    def create(
        source: str, timestamp: datetime, attestation_ref: str,
    ) -> Ok[FirmConfidence] | Err[str]:
        match NonEmptyStr.parse(source):
            case Err(e):
                return Err(f"FirmConfidence.source: {e}")
            case Ok(src):
                pass
        match UtcDatetime.parse(timestamp):
            case Err(e):
                return Err(f"FirmConfidence.timestamp: {e}")
            case Ok(ts):
                pass
        match NonEmptyStr.parse(attestation_ref):
            case Err(e):
                return Err(f"FirmConfidence.attestation_ref: {e}")
            case Ok(ref):
                pass
        return Ok(FirmConfidence(source=src, timestamp=ts, attestation_ref=ref))


# ---------------------------------------------------------------------------
# QuotedConfidence (GAP-06: bid<=ask, mid/spread)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class QuotedConfidence:
    """Confidence from a quoted market — bid/ask with venue."""

    bid: Decimal
    ask: Decimal
    venue: NonEmptyStr
    size: Decimal | None
    conditions: QuoteCondition

    @staticmethod
    def create(
        bid: Decimal, ask: Decimal, venue: str,
        size: Decimal | None = None,
        conditions: QuoteCondition = QuoteCondition.INDICATIVE,
    ) -> Ok[QuotedConfidence] | Err[str]:
        if not isinstance(bid, Decimal) or not bid.is_finite():
            return Err(f"QuotedConfidence.bid must be finite Decimal, got {bid}")
        if not isinstance(ask, Decimal) or not ask.is_finite():
            return Err(f"QuotedConfidence.ask must be finite Decimal, got {ask}")
        if bid > ask:
            return Err(
                f"QuotedConfidence: bid ({bid}) > ask ({ask}) implies negative spread"
            )
        match NonEmptyStr.parse(venue):
            case Err(e):
                return Err(f"QuotedConfidence.venue: {e}")
            case Ok(v):
                pass
        return Ok(QuotedConfidence(bid=bid, ask=ask, venue=v, size=size, conditions=conditions))

    @property
    def mid(self) -> Decimal:
        """Mid-price: (bid + ask) / 2."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return (self.bid + self.ask) / 2

    @property
    def spread(self) -> Decimal:
        """Spread: ask - bid. Always >= 0 by construction."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return self.ask - self.bid

    @property
    def half_spread(self) -> Decimal:
        """Half-spread: spread / 2."""
        with localcontext(ATTESTOR_DECIMAL_CONTEXT):
            return self.spread / 2


# ---------------------------------------------------------------------------
# DerivedConfidence (GAP-07, GAP-09, GAP-31)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class DerivedConfidence:
    """Confidence from a model/calibration — with fit quality metrics."""

    method: NonEmptyStr
    config_ref: NonEmptyStr
    fit_quality: FrozenMap[str, Decimal]
    confidence_interval: tuple[Decimal, Decimal] | None
    confidence_level: Decimal | None

    @staticmethod
    def create(
        method: str, config_ref: str,
        fit_quality: FrozenMap[str, Decimal],
        confidence_interval: tuple[Decimal, Decimal] | None = None,
        confidence_level: Decimal | None = None,
    ) -> Ok[DerivedConfidence] | Err[str]:
        # GAP-31: reject empty fit_quality
        if len(fit_quality) == 0:
            return Err("DerivedConfidence: fit_quality must not be empty")
        # GAP-07: both or neither
        if (confidence_interval is None) != (confidence_level is None):
            return Err(
                "confidence_interval and confidence_level must be both present or both absent"
            )
        # confidence_level in (0, 1)
        if confidence_level is not None and not (0 < confidence_level < 1):
            return Err(f"confidence_level must be in (0,1), got {confidence_level}")
        match NonEmptyStr.parse(method):
            case Err(e):
                return Err(f"DerivedConfidence.method: {e}")
            case Ok(m):
                pass
        match NonEmptyStr.parse(config_ref):
            case Err(e):
                return Err(f"DerivedConfidence.config_ref: {e}")
            case Ok(cr):
                pass
        return Ok(DerivedConfidence(
            method=m, config_ref=cr, fit_quality=fit_quality,
            confidence_interval=confidence_interval, confidence_level=confidence_level,
        ))


# Type alias
Confidence = FirmConfidence | QuotedConfidence | DerivedConfidence


# ---------------------------------------------------------------------------
# Attestation[T] (GAP-01: attestation_id)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class Attestation[T]:
    """Content-addressed attestation wrapping a value with epistemic metadata.

    content_hash: SHA-256 of canonical_bytes(value) — value identity
    attestation_id: SHA-256 of canonical_bytes(full identity payload) — full identity
    """

    value: T
    confidence: Confidence
    source: NonEmptyStr
    timestamp: UtcDatetime
    provenance: tuple[str, ...]
    content_hash: str
    attestation_id: str


def create_attestation[T](
    value: T,
    confidence: Confidence,
    source: str,
    timestamp: datetime,
    provenance: tuple[str, ...] = (),
) -> Ok[Attestation[T]] | Err[str]:
    """Create an Attestation with computed content_hash and attestation_id.

    Returns Err if value cannot be serialized (GAP-04), or if source/timestamp
    validation fails.
    """
    # Compute content_hash from value only
    match content_hash(value):
        case Err(e):
            return Err(f"Cannot hash value: {e}")
        case Ok(ch):
            pass

    # GAP-01: compute attestation_id from all identity fields
    identity_payload = {
        "source": source,
        "timestamp": timestamp.isoformat() if isinstance(timestamp, datetime) else str(timestamp),
        "confidence": confidence,
        "value": value,
        "provenance": provenance,
    }
    match content_hash(identity_payload):
        case Err(e):
            return Err(f"Cannot compute attestation_id: {e}")
        case Ok(aid):
            pass

    match UtcDatetime.parse(timestamp):
        case Err(e):
            return Err(f"Attestation timestamp: {e}")
        case Ok(ts):
            pass

    match NonEmptyStr.parse(source):
        case Err(e):
            return Err(f"Attestation source: {e}")
        case Ok(src):
            pass

    return Ok(Attestation(
        value=value, confidence=confidence, source=src,
        timestamp=ts, provenance=provenance,
        content_hash=ch, attestation_id=aid,
    ))
