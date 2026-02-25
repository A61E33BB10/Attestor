"""Workflow data types for structured derivatives RFQ.

6 new types: RFQInput, PreTradeCheckResult, PricingResult, TermSheet,
ClientResponse, RFQResult.  Plus activity input/output wrappers.

All types: @final @dataclass(frozen=True, slots=True).
Convention: smart constructors at activity boundaries; __post_init__ for
invariants that should hold at all times.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from enum import Enum
from typing import final

from attestor.core.identifiers import LEI
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.gateway.types import OrderSide
from attestor.instrument.derivative_types import InstrumentDetail
from attestor.instrument.types import Product
from attestor.oracle.attestation import DerivedConfidence

# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ClientAction(Enum):
    """Three possible client responses.  Exhaustive."""

    ACCEPT = "Accept"
    REJECT = "Reject"
    REFRESH = "Refresh"


class RFQOutcome(Enum):
    """Terminal states of the RFQ workflow."""

    EXECUTED = "Executed"
    REJECTED_PRE_TRADE = "RejectedPreTrade"
    REJECTED_BY_CLIENT = "RejectedByClient"
    EXPIRED = "Expired"
    FAILED = "Failed"


# ---------------------------------------------------------------------------
# Workflow input
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class RFQInput:
    """What the client wants.  Workflow entry point.

    The rfq_id serves as Temporal Workflow ID for natural idempotency.
    """

    rfq_id: NonEmptyStr
    client_lei: LEI
    instrument_detail: InstrumentDetail
    notional: PositiveDecimal
    currency: NonEmptyStr
    side: OrderSide
    trade_date: date
    settlement_date: date
    timestamp: UtcDatetime

    def __post_init__(self) -> None:
        if self.settlement_date < self.trade_date:
            raise TypeError(
                f"settlement_date ({self.settlement_date}) "
                f"must be >= trade_date ({self.trade_date})"
            )


# ---------------------------------------------------------------------------
# Activity I/O: mapping
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class MappingOutput:
    """Output of map_to_cdm_product activity."""

    product: Product | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (self.product is None) == (self.error is None):
            raise TypeError(
                "MappingOutput must have exactly one of product or error"
            )


# ---------------------------------------------------------------------------
# Activity I/O: pre-trade checks
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class PreTradeInput:
    """Input to pre-trade checks activity."""

    rfq: RFQInput
    product: Product


@final
@dataclass(frozen=True, slots=True)
class PreTradeCheckResult:
    """Outcome of all pre-trade compliance checks."""

    restricted_underlying_ok: bool
    credit_limit_ok: bool
    eligibility_ok: bool
    details: tuple[str, ...] = ()

    @property
    def passed(self) -> bool:
        return (
            self.restricted_underlying_ok
            and self.credit_limit_ok
            and self.eligibility_ok
        )

    @property
    def rejection_reasons(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.restricted_underlying_ok:
            reasons.append("Underlying on restricted list")
        if not self.credit_limit_ok:
            reasons.append("Credit limit exceeded")
        if not self.eligibility_ok:
            reasons.append("Client not eligible for this product type")
        return tuple(reasons)


# ---------------------------------------------------------------------------
# Activity I/O: pricing
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class PricingInput:
    """Input to pricing activity."""

    rfq: RFQInput
    product: Product


@final
@dataclass(frozen=True, slots=True)
class PricingResult:
    """Output of the quant pricing activity."""

    indicative_price: Money
    greeks: FrozenMap[str, Decimal]
    model_name: NonEmptyStr
    market_data_snapshot_id: NonEmptyStr
    confidence: DerivedConfidence
    pricing_attestation_id: NonEmptyStr
    timestamp: UtcDatetime


@final
@dataclass(frozen=True, slots=True)
class PricingOutput:
    """Wrapper for pricing activity result or error."""

    result: PricingResult | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise TypeError(
                "PricingOutput must have exactly one of result or error"
            )


# ---------------------------------------------------------------------------
# Activity I/O: indicative term sheet
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class IndicativeInput:
    """Input to generate_and_send_indicative activity."""

    rfq: RFQInput
    pricing: PricingResult
    valid_for: timedelta


@final
@dataclass(frozen=True, slots=True)
class TermSheet:
    """Indicative term sheet with content-addressed integrity."""

    rfq_id: NonEmptyStr
    pricing_result: PricingResult
    document_hash: NonEmptyStr
    valid_until: UtcDatetime
    generated_at: UtcDatetime

    def __post_init__(self) -> None:
        if self.valid_until.value < self.generated_at.value:
            raise TypeError(
                f"valid_until ({self.valid_until.value}) "
                f"must be >= generated_at ({self.generated_at.value})"
            )


# ---------------------------------------------------------------------------
# Client response (signal payload)
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ClientResponse:
    """Signal payload from the client."""

    rfq_id: NonEmptyStr
    action: ClientAction
    timestamp: UtcDatetime
    term_sheet_hash: NonEmptyStr | None = None
    message: str | None = None

    def __post_init__(self) -> None:
        if self.action == ClientAction.ACCEPT and self.term_sheet_hash is None:
            raise TypeError(
                "term_sheet_hash is required when action is ACCEPT"
            )


# ---------------------------------------------------------------------------
# Activity I/O: booking
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class BookingInput:
    """Input to book_trade activity."""

    rfq: RFQInput
    product: Product
    pricing: PricingResult
    accepted_price: Money


@final
@dataclass(frozen=True, slots=True)
class BookingResult:
    """Output of book_trade activity."""

    trade_id: NonEmptyStr


@final
@dataclass(frozen=True, slots=True)
class BookingOutput:
    """Wrapper for booking activity result or error."""

    result: BookingResult | None = None
    error: str | None = None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.error is None):
            raise TypeError(
                "BookingOutput must have exactly one of result or error"
            )


# ---------------------------------------------------------------------------
# Activity I/O: confirmation
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class ConfirmationInput:
    """Input to send_confirmation activity."""

    rfq: RFQInput
    trade_result: BookingResult
    term_sheet: TermSheet


# ---------------------------------------------------------------------------
# Workflow output
# ---------------------------------------------------------------------------


@final
@dataclass(frozen=True, slots=True)
class RFQResult:
    """Terminal outcome of the workflow."""

    rfq_id: NonEmptyStr
    outcome: RFQOutcome
    trade_id: NonEmptyStr | None = None
    rejection_reasons: tuple[str, ...] = ()
    pricing_attestation_id: NonEmptyStr | None = None

    def __post_init__(self) -> None:
        if self.outcome == RFQOutcome.EXECUTED and self.trade_id is None:
            raise TypeError("EXECUTED outcome requires trade_id")
        if self.outcome != RFQOutcome.EXECUTED and self.trade_id is not None:
            raise TypeError(
                f"{self.outcome.value} outcome must not have trade_id"
            )
