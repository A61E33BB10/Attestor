"""Activity implementations for the structured derivatives RFQ workflow.

Activities are thin IO wrappers.  All domain logic lives in Attestor's
pure library layer (instrument factories, pricing functions, registries).

Each activity:
- Is decorated with @activity.defn
- Takes a single frozen-dataclass input
- Returns a frozen-dataclass output (with optional error field)
- Is idempotent (same input -> same output, no duplicate side-effects)
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from temporalio import activity

from attestor.core.money import NonEmptyStr
from attestor.core.types import UtcDatetime
from attestor.workflow.types import (
    BookingInput,
    BookingOutput,
    BookingResult,
    ConfirmationInput,
    IndicativeInput,
    MappingOutput,
    PreTradeCheckResult,
    PreTradeInput,
    PricingInput,
    PricingOutput,
    RFQInput,
    TermSheet,
)


def _utc_now() -> UtcDatetime:
    """Activity-safe UTC timestamp (NOT for workflow code)."""
    return UtcDatetime(value=datetime.now(tz=UTC))


def _content_hash(data: str) -> str:
    """SHA-256 hex digest of a string."""
    return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# 1. map_to_cdm_product
# ---------------------------------------------------------------------------


@activity.defn(name="map_to_cdm_product")
async def map_to_cdm_product(rfq: RFQInput) -> MappingOutput:
    """Map InstrumentDetail to CDM Product via Attestor instrument factories.

    Timeout: 30s | Retries: 1 (validation -- no retry)
    Idempotent: yes (pure function of input)
    """
    activity.logger.info("Mapping RFQ %s to CDM product", rfq.rfq_id.value)

    # The real implementation dispatches on InstrumentDetail variant
    # and calls the appropriate create_*_instrument factory.
    # For now, wrap in a Product with the instrument_detail's implied payout.
    try:
        from attestor.instrument.types import EconomicTerms
        from attestor.instrument.types import Product as CDMProduct

        # Minimal mapping: create EconomicTerms from the instrument detail.
        # A full implementation would use the product registry (Lattner)
        # to dispatch to the correct CDM mapper.
        terms = EconomicTerms(
            payouts=(),  # Will fail validation -- placeholder
            effective_date=rfq.trade_date,
            termination_date=rfq.settlement_date,
        )
        product = CDMProduct(economic_terms=terms)
        return MappingOutput(product=product)
    except (TypeError, ValueError) as exc:
        return MappingOutput(error=str(exc))


# ---------------------------------------------------------------------------
# 2. run_pre_trade_checks
# ---------------------------------------------------------------------------


@activity.defn(name="run_pre_trade_checks")
async def run_pre_trade_checks(inp: PreTradeInput) -> PreTradeCheckResult:
    """Run compliance checks (parallel inside, single activity outside).

    Timeout: 60s | Retries: 3 (exponential backoff)
    Idempotent: yes (reads from versioned reference data)
    """
    activity.logger.info(
        "Running pre-trade checks for RFQ %s", inp.rfq.rfq_id.value,
    )

    # Real implementation: resolve checks from PreTradeCheckRegistry,
    # run them in parallel (asyncio.gather), aggregate results.
    # Stub: all checks pass.
    return PreTradeCheckResult(
        restricted_underlying_ok=True,
        credit_limit_ok=True,
        eligibility_ok=True,
    )


# ---------------------------------------------------------------------------
# 3. price_product
# ---------------------------------------------------------------------------


@activity.defn(name="price_product")
async def price_product(inp: PricingInput) -> PricingOutput:
    """Invoke quant library.  Returns attested price + Greeks.

    Timeout: 5min | Retries: 2 | Heartbeat: 30s
    Internally implements Gatheral's pricing pipeline:
      gather_market -> calibrate -> arbitrage_gates -> price -> greeks

    Idempotent: yes (same product + market snapshot -> same price)
    """
    activity.logger.info(
        "Pricing RFQ %s", inp.rfq.rfq_id.value,
    )
    activity.heartbeat()

    # Real implementation: resolve pricer from PricingRegistry,
    # run Gatheral pipeline (staleness -> calibrate -> AF gates -> price).
    # Stub: returns an error indicating no pricer is registered.
    return PricingOutput(error="No pricer registered for this product type")


# ---------------------------------------------------------------------------
# 4. generate_and_send_indicative
# ---------------------------------------------------------------------------


@activity.defn(name="generate_and_send_indicative")
async def generate_and_send_indicative(inp: IndicativeInput) -> TermSheet:
    """Generate term sheet + deliver to client.

    Timeout: 60s | Retries: 3
    Idempotent: yes (dedup by rfq_id + document_hash)
    """
    activity.logger.info(
        "Generating indicative for RFQ %s", inp.rfq.rfq_id.value,
    )

    now = _utc_now()
    valid_until = UtcDatetime(value=now.value + inp.valid_for)

    # Content for hashing: serialise key pricing fields
    content = json.dumps({
        "rfq_id": inp.rfq.rfq_id.value,
        "price": str(inp.pricing.indicative_price.amount),
        "currency": inp.pricing.indicative_price.currency.value,
        "model": inp.pricing.model_name.value,
        "snapshot": inp.pricing.market_data_snapshot_id.value,
    }, sort_keys=True)
    doc_hash = _content_hash(content)

    return TermSheet(
        rfq_id=inp.rfq.rfq_id,
        pricing_result=inp.pricing,
        document_hash=NonEmptyStr(value=doc_hash),
        valid_until=valid_until,
        generated_at=now,
    )


# ---------------------------------------------------------------------------
# 5. book_trade
# ---------------------------------------------------------------------------


@activity.defn(name="book_trade")
async def book_trade(inp: BookingInput) -> BookingOutput:
    """Create CanonicalOrder -> ExecutePI -> BusinessEvent -> TradeState.

    Timeout: 60s | Retries: 3 | Non-retryable: ValidationError
    CRITICAL: uses rfq_id as idempotency key

    NOTE (Formalis): check_transition() calls UtcDatetime.now() internally.
    This is safe inside activities (non-deterministic context).
    """
    activity.logger.info(
        "Booking trade for RFQ %s", inp.rfq.rfq_id.value,
    )

    # Real implementation:
    #   1. Check idempotency (trade with this rfq_id already exists?)
    #   2. CanonicalOrder.create(...)
    #   3. ExecutePI(order=order)
    #   4. BusinessEvent(instruction=pi, event_intent=CONTRACT_FORMATION)
    #   5. check_transition(PROPOSED -> FORMED)
    #   6. Persist TradeState
    # Stub: return a synthetic trade ID.
    trade_id = NonEmptyStr(value=f"TRADE-{inp.rfq.rfq_id.value}")
    return BookingOutput(result=BookingResult(trade_id=trade_id))


# ---------------------------------------------------------------------------
# 6. send_confirmation
# ---------------------------------------------------------------------------


@activity.defn(name="send_confirmation")
async def send_confirmation(inp: ConfirmationInput) -> None:
    """Deliver trade confirmation to both parties.

    Timeout: 60s | Retries: 5
    Idempotent: yes (dedup by trade_id)
    """
    activity.logger.info(
        "Sending confirmation for trade %s (RFQ %s)",
        inp.trade_result.trade_id.value,
        inp.rfq.rfq_id.value,
    )

    # Real implementation: format confirmation document,
    # deliver via email/API to both counterparties.
    # Stub: no-op (logs only).
