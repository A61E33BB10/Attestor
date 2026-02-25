"""Integration tests for StructuredProductRFQWorkflow.

Uses Temporal's time-skipping test environment -- no real server needed.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from temporalio import activity
from temporalio.testing import WorkflowEnvironment
from temporalio.worker import Worker

from attestor.core.identifiers import LEI
from attestor.core.money import Money, NonEmptyStr, PositiveDecimal
from attestor.core.result import unwrap
from attestor.core.types import FrozenMap, UtcDatetime
from attestor.gateway.types import OrderSide
from attestor.instrument.derivative_types import EquityDetail
from attestor.instrument.types import EconomicTerms, EquityPayoutSpec, Product
from attestor.oracle.attestation import DerivedConfidence
from attestor.workflow.converter import ATTESTOR_DATA_CONVERTER
from attestor.workflow.rfq_workflow import (
    StructuredProductRFQWorkflow,
)
from attestor.workflow.types import (
    BookingInput,
    BookingOutput,
    BookingResult,
    ClientAction,
    ClientResponse,
    ConfirmationInput,
    IndicativeInput,
    MappingOutput,
    PreTradeCheckResult,
    PreTradeInput,
    PricingInput,
    PricingOutput,
    PricingResult,
    RFQInput,
    RFQOutcome,
    TermSheet,
)

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

_NOW = UtcDatetime(value=datetime(2025, 6, 15, 12, 0, tzinfo=UTC))
_LEI = unwrap(LEI.parse("529900T8BM49AURSDO55"))
_MONEY = unwrap(Money.create(Decimal("42.50"), "USD"))

TASK_QUEUE = "test-rfq"


async def _start_env() -> WorkflowEnvironment:
    """Start a time-skipping Temporal test environment with Attestor converter."""
    return await WorkflowEnvironment.start_time_skipping(
        data_converter=ATTESTOR_DATA_CONVERTER,
    )


def _rfq(rfq_id: str = "RFQ-TEST-001") -> RFQInput:
    return RFQInput(
        rfq_id=NonEmptyStr(value=rfq_id),
        client_lei=_LEI,
        instrument_detail=EquityDetail(),
        notional=PositiveDecimal(value=Decimal("1000000")),
        currency=NonEmptyStr(value="USD"),
        side=OrderSide.BUY,
        trade_date=date(2025, 6, 15),
        settlement_date=date(2025, 6, 17),
        timestamp=_NOW,
    )


def _product() -> Product:
    payout = unwrap(EquityPayoutSpec.create("NVDA", "USD", "XNAS"))
    terms = EconomicTerms(
        payouts=(payout,), effective_date=date(2025, 6, 15), termination_date=None,
    )
    return Product(economic_terms=terms)


def _pricing_result() -> PricingResult:
    fq = unwrap(FrozenMap.create({"rmse": Decimal("0.001")}))
    conf = unwrap(DerivedConfidence.create(
        method="BS", config_ref="v1", fit_quality=fq,
    ))
    return PricingResult(
        indicative_price=_MONEY,
        greeks=unwrap(FrozenMap.create({"delta": Decimal("0.55")})),
        model_name=NonEmptyStr(value="BlackScholes"),
        market_data_snapshot_id=NonEmptyStr(value="snap-001"),
        confidence=conf,
        pricing_attestation_id=NonEmptyStr(value="att-001"),
        timestamp=_NOW,
    )


def _term_sheet_hash(pricing: PricingResult, rfq_id: str) -> str:
    content = json.dumps({
        "rfq_id": rfq_id,
        "price": str(pricing.indicative_price.amount),
        "currency": pricing.indicative_price.currency.value,
        "model": pricing.model_name.value,
        "snapshot": pricing.market_data_snapshot_id.value,
    }, sort_keys=True)
    return hashlib.sha256(content.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Mock activities (override the real stubs)
# ---------------------------------------------------------------------------


@activity.defn(name="map_to_cdm_product")
async def mock_map_to_cdm(rfq: RFQInput) -> MappingOutput:
    return MappingOutput(product=_product())


@activity.defn(name="map_to_cdm_product")
async def mock_map_to_cdm_fail(rfq: RFQInput) -> MappingOutput:
    return MappingOutput(error="Unsupported product type")


@activity.defn(name="run_pre_trade_checks")
async def mock_pre_trade_pass(inp: PreTradeInput) -> PreTradeCheckResult:
    return PreTradeCheckResult(
        restricted_underlying_ok=True,
        credit_limit_ok=True,
        eligibility_ok=True,
    )


@activity.defn(name="run_pre_trade_checks")
async def mock_pre_trade_fail(inp: PreTradeInput) -> PreTradeCheckResult:
    return PreTradeCheckResult(
        restricted_underlying_ok=True,
        credit_limit_ok=False,
        eligibility_ok=True,
    )


@activity.defn(name="price_product")
async def mock_price(inp: PricingInput) -> PricingOutput:
    activity.heartbeat()
    return PricingOutput(result=_pricing_result())


@activity.defn(name="price_product")
async def mock_price_fail(inp: PricingInput) -> PricingOutput:
    return PricingOutput(error="Calibration diverged")


@activity.defn(name="generate_and_send_indicative")
async def mock_indicative(inp: IndicativeInput) -> TermSheet:
    now = UtcDatetime(value=datetime.now(tz=UTC))
    content = json.dumps({
        "rfq_id": inp.rfq.rfq_id.value,
        "price": str(inp.pricing.indicative_price.amount),
        "currency": inp.pricing.indicative_price.currency.value,
        "model": inp.pricing.model_name.value,
        "snapshot": inp.pricing.market_data_snapshot_id.value,
    }, sort_keys=True)
    doc_hash = hashlib.sha256(content.encode()).hexdigest()
    return TermSheet(
        rfq_id=inp.rfq.rfq_id,
        pricing_result=inp.pricing,
        document_hash=NonEmptyStr(value=doc_hash),
        valid_until=UtcDatetime(value=now.value + inp.valid_for),
        generated_at=now,
    )


@activity.defn(name="book_trade")
async def mock_book(inp: BookingInput) -> BookingOutput:
    tid = NonEmptyStr(value=f"TRADE-{inp.rfq.rfq_id.value}")
    return BookingOutput(result=BookingResult(trade_id=tid))


@activity.defn(name="book_trade")
async def mock_book_fail(inp: BookingInput) -> BookingOutput:
    return BookingOutput(error="Ledger conflict")


@activity.defn(name="send_confirmation")
async def mock_confirm(inp: ConfirmationInput) -> None:
    pass


# ---------------------------------------------------------------------------
# Activity sets
# ---------------------------------------------------------------------------

_HAPPY_ACTIVITIES = [
    mock_map_to_cdm, mock_pre_trade_pass, mock_price,
    mock_indicative, mock_book, mock_confirm,
]

_PRE_TRADE_FAIL_ACTIVITIES = [
    mock_map_to_cdm, mock_pre_trade_fail, mock_price,
    mock_indicative, mock_book, mock_confirm,
]

_MAPPING_FAIL_ACTIVITIES = [
    mock_map_to_cdm_fail, mock_pre_trade_pass, mock_price,
    mock_indicative, mock_book, mock_confirm,
]

_PRICING_FAIL_ACTIVITIES = [
    mock_map_to_cdm, mock_pre_trade_pass, mock_price_fail,
    mock_indicative, mock_book, mock_confirm,
]

_BOOKING_FAIL_ACTIVITIES = [
    mock_map_to_cdm, mock_pre_trade_pass, mock_price,
    mock_indicative, mock_book_fail, mock_confirm,
]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_happy_path() -> None:
    """RFQ -> checks pass -> price -> client accepts -> booked."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-HAPPY")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_HAPPY_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-HAPPY",
                task_queue=TASK_QUEUE,
            )

            # Wait until workflow reaches AWAITING_CLIENT
            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            # Send ACCEPT with correct hash
            doc_hash = _term_sheet_hash(_pricing_result(), "RFQ-HAPPY")
            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-HAPPY"),
                    action=ClientAction.ACCEPT,
                    timestamp=_NOW,
                    term_sheet_hash=NonEmptyStr(value=doc_hash),
                ),
            )

            result = await handle.result()
            assert result.outcome == RFQOutcome.EXECUTED
            assert result.trade_id is not None
            assert result.trade_id.value == "TRADE-RFQ-HAPPY"


@pytest.mark.asyncio
async def test_pre_trade_rejection() -> None:
    """RFQ -> restricted underlying -> rejected."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-PRETRADE-FAIL")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_PRE_TRADE_FAIL_ACTIVITIES,
        ):
            result = await env.client.execute_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-PRETRADE-FAIL",
                task_queue=TASK_QUEUE,
            )
            assert result.outcome == RFQOutcome.REJECTED_PRE_TRADE
            assert "Credit limit exceeded" in result.rejection_reasons


@pytest.mark.asyncio
async def test_mapping_failure() -> None:
    """RFQ with unsupported product -> FAILED."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-MAP-FAIL")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_MAPPING_FAIL_ACTIVITIES,
        ):
            result = await env.client.execute_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-MAP-FAIL",
                task_queue=TASK_QUEUE,
            )
            assert result.outcome == RFQOutcome.FAILED
            assert "Unsupported product type" in result.rejection_reasons


@pytest.mark.asyncio
async def test_pricing_failure() -> None:
    """Pricing calibration fails -> FAILED."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-PRICE-FAIL")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_PRICING_FAIL_ACTIVITIES,
        ):
            result = await env.client.execute_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-PRICE-FAIL",
                task_queue=TASK_QUEUE,
            )
            assert result.outcome == RFQOutcome.FAILED
            assert any("Pricing failed" in r for r in result.rejection_reasons)


@pytest.mark.asyncio
async def test_client_rejects() -> None:
    """Client explicitly rejects the quote."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-REJECT")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_HAPPY_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-REJECT",
                task_queue=TASK_QUEUE,
            )

            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-REJECT"),
                    action=ClientAction.REJECT,
                    timestamp=_NOW,
                    message="Too expensive",
                ),
            )

            result = await handle.result()
            assert result.outcome == RFQOutcome.REJECTED_BY_CLIENT


@pytest.mark.asyncio
async def test_refresh_then_accept() -> None:
    """Client refreshes once, then accepts."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-REFRESH")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_HAPPY_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-REFRESH",
                task_queue=TASK_QUEUE,
            )

            # First round: REFRESH
            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-REFRESH"),
                    action=ClientAction.REFRESH,
                    timestamp=_NOW,
                ),
            )

            # Second round: ACCEPT
            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            doc_hash = _term_sheet_hash(_pricing_result(), "RFQ-REFRESH")
            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-REFRESH"),
                    action=ClientAction.ACCEPT,
                    timestamp=_NOW,
                    term_sheet_hash=NonEmptyStr(value=doc_hash),
                ),
            )

            result = await handle.result()
            assert result.outcome == RFQOutcome.EXECUTED


@pytest.mark.asyncio
async def test_stale_acceptance() -> None:
    """Client accepts with wrong term_sheet_hash -> FAILED."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-STALE")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_HAPPY_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-STALE",
                task_queue=TASK_QUEUE,
            )

            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-STALE"),
                    action=ClientAction.ACCEPT,
                    timestamp=_NOW,
                    term_sheet_hash=NonEmptyStr(value="wrong-hash"),
                ),
            )

            result = await handle.result()
            assert result.outcome == RFQOutcome.FAILED
            assert any("stale" in r.lower() for r in result.rejection_reasons)


@pytest.mark.asyncio
async def test_booking_failure() -> None:
    """Trade booking fails -> FAILED."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-BOOK-FAIL")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_BOOKING_FAIL_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-BOOK-FAIL",
                task_queue=TASK_QUEUE,
            )

            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            doc_hash = _term_sheet_hash(_pricing_result(), "RFQ-BOOK-FAIL")
            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-BOOK-FAIL"),
                    action=ClientAction.ACCEPT,
                    timestamp=_NOW,
                    term_sheet_hash=NonEmptyStr(value=doc_hash),
                ),
            )

            result = await handle.result()
            assert result.outcome == RFQOutcome.FAILED
            assert any("Booking failed" in r for r in result.rejection_reasons)


@pytest.mark.asyncio
async def test_query_current_pricing() -> None:
    """Query returns latest pricing result after pricing completes."""
    async with await _start_env() as env:
        rfq = _rfq("RFQ-QUERY")
        async with Worker(
            env.client, task_queue=TASK_QUEUE,
            workflows=[StructuredProductRFQWorkflow],
            activities=_HAPPY_ACTIVITIES,
        ):
            handle = await env.client.start_workflow(
                StructuredProductRFQWorkflow.run,
                rfq,
                id="RFQ-QUERY",
                task_queue=TASK_QUEUE,
            )

            for _ in range(50):
                status = await handle.query(
                    StructuredProductRFQWorkflow.get_status,
                )
                if status == "AWAITING_CLIENT":
                    break
                await asyncio.sleep(0.1)

            pricing = await handle.query(
                StructuredProductRFQWorkflow.get_current_pricing,
            )
            assert pricing is not None
            assert pricing.model_name.value == "BlackScholes"

            # Clean up: reject so workflow finishes
            await handle.signal(
                StructuredProductRFQWorkflow.client_responds,
                ClientResponse(
                    rfq_id=NonEmptyStr(value="RFQ-QUERY"),
                    action=ClientAction.REJECT,
                    timestamp=_NOW,
                ),
            )
            await handle.result()
