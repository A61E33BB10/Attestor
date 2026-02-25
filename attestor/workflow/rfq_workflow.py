"""Durable workflow for structured derivatives RFQ lifecycle.

Steps: receive -> map -> check -> (price -> send -> wait) x N -> book -> confirm.
The (price -> send -> wait) cycle repeats on REFRESH, max 5 times.

Determinism contract: this module contains NO I/O, NO randomness,
NO system clock access (uses workflow.now()), NO mutable globals.
All external interaction is delegated to Activities.

Committee-approved architecture (Minsky, Formalis, Karpathy, Gatheral,
Noether, Lattner, Geohot).  See structured_derivatives_workflow.md.
"""

from __future__ import annotations

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy

with workflow.unsafe.imports_passed_through():
    from attestor.core.types import UtcDatetime
    from attestor.workflow.activities import (
        book_trade,
        generate_and_send_indicative,
        map_to_cdm_product,
        price_product,
        run_pre_trade_checks,
        send_confirmation,
    )
    from attestor.workflow.types import (
        BookingInput,
        ClientAction,
        ClientResponse,
        ConfirmationInput,
        IndicativeInput,
        PreTradeInput,
        PricingInput,
        PricingResult,
        RFQInput,
        RFQOutcome,
        RFQResult,
        TermSheet,
    )

MAX_REFRESHES: int = 5
CLIENT_TIMEOUT: timedelta = timedelta(hours=24)

# -- Retry policies (Section 5 of design doc) --

MAPPING_RETRY = RetryPolicy(maximum_attempts=1)

PRE_TRADE_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=30),
    maximum_attempts=3,
)

PRICING_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=2,
    non_retryable_error_types=["PricingError", "CalibrationError"],
)

BOOKING_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=10),
    maximum_attempts=3,
    non_retryable_error_types=["ValidationError", "IllegalTransitionError"],
)

DELIVERY_RETRY = RetryPolicy(
    initial_interval=timedelta(seconds=2),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(seconds=60),
    maximum_attempts=5,
)


def _workflow_utc_now() -> UtcDatetime:
    """Replay-safe UTC timestamp from Temporal's logical clock.

    CRITICAL (Formalis): this is the ONLY way to get current time
    in workflow code.  Never use UtcDatetime.now() or datetime.now().
    """
    return UtcDatetime(value=workflow.now())


@workflow.defn(name="StructuredProductRFQ")
class StructuredProductRFQWorkflow:
    """Durable workflow for structured derivatives RFQ lifecycle.

    Invariants maintained:
    - Every RFQ reaches exactly one terminal outcome (totality)
    - No trade booked without passing all pre-trade checks
    - No trade booked without explicit client ACCEPT
    - Refresh loop terminates (bounded by MAX_REFRESHES)
    - All activity inputs/outputs are frozen dataclasses
    - Workflow is deterministic under Temporal replay
    """

    def __init__(self) -> None:
        self._status: str = "RECEIVED"
        self._client_response: ClientResponse | None = None
        self._current_pricing: PricingResult | None = None
        self._current_term_sheet: TermSheet | None = None

    # -- Signal --

    @workflow.signal
    async def client_responds(self, response: ClientResponse) -> None:
        """Client sends ACCEPT / REJECT / REFRESH."""
        self._client_response = response

    # -- Queries --

    @workflow.query
    def get_status(self) -> str:
        """Current workflow phase."""
        return self._status

    @workflow.query
    def get_current_pricing(self) -> PricingResult | None:
        """Latest pricing result, if available."""
        return self._current_pricing

    # -- Main workflow --

    @workflow.run
    async def run(self, rfq: RFQInput) -> RFQResult:  # noqa: C901
        """Execute the full RFQ lifecycle."""

        # --- Step 1: Map to CDM product ---
        self._status = "MAPPING"
        cdm_product = await workflow.execute_activity(
            map_to_cdm_product,
            rfq,
            start_to_close_timeout=timedelta(seconds=30),
            retry_policy=MAPPING_RETRY,
        )
        if cdm_product.error is not None:
            return RFQResult(
                rfq_id=rfq.rfq_id,
                outcome=RFQOutcome.FAILED,
                rejection_reasons=(cdm_product.error,),
            )

        product = cdm_product.product
        assert product is not None  # guaranteed when error is None

        # --- Step 2: Pre-trade checks ---
        self._status = "PRE_TRADE_CHECKS"
        checks = await workflow.execute_activity(
            run_pre_trade_checks,
            PreTradeInput(rfq=rfq, product=product),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=PRE_TRADE_RETRY,
        )
        if not checks.passed:
            return RFQResult(
                rfq_id=rfq.rfq_id,
                outcome=RFQOutcome.REJECTED_PRE_TRADE,
                rejection_reasons=checks.rejection_reasons,
            )

        # --- Steps 3-6: Price / Send / Wait loop ---
        refresh_count = 0
        pricing: PricingResult | None = None
        term_sheet: TermSheet | None = None

        while refresh_count <= MAX_REFRESHES:
            # Step 3: Price
            self._status = "PRICING"
            pricing_out = await workflow.execute_activity(
                price_product,
                PricingInput(rfq=rfq, product=product),
                start_to_close_timeout=timedelta(minutes=5),
                retry_policy=PRICING_RETRY,
                heartbeat_timeout=timedelta(seconds=30),
            )
            if pricing_out.error is not None:
                return RFQResult(
                    rfq_id=rfq.rfq_id,
                    outcome=RFQOutcome.FAILED,
                    rejection_reasons=(
                        f"Pricing failed: {pricing_out.error}",
                    ),
                )
            pricing = pricing_out.result
            assert pricing is not None
            self._current_pricing = pricing

            # Step 4: Generate and send indicative term sheet
            self._status = "QUOTING"
            term_sheet = await workflow.execute_activity(
                generate_and_send_indicative,
                IndicativeInput(
                    rfq=rfq,
                    pricing=pricing,
                    valid_for=timedelta(hours=1),
                ),
                start_to_close_timeout=timedelta(seconds=60),
                retry_policy=DELIVERY_RETRY,
            )
            self._current_term_sheet = term_sheet

            # Step 5: Wait for client response
            self._status = "AWAITING_CLIENT"
            self._client_response = None

            try:
                await workflow.wait_condition(
                    lambda: self._client_response is not None,
                    timeout=CLIENT_TIMEOUT,
                )
            except TimeoutError:
                return RFQResult(
                    rfq_id=rfq.rfq_id,
                    outcome=RFQOutcome.EXPIRED,
                    pricing_attestation_id=pricing.pricing_attestation_id,
                )

            response = self._client_response
            assert response is not None

            # Step 6: Branch on client action
            match response.action:
                case ClientAction.REJECT:
                    return RFQResult(
                        rfq_id=rfq.rfq_id,
                        outcome=RFQOutcome.REJECTED_BY_CLIENT,
                        rejection_reasons=(
                            response.message or "Client rejected",
                        ),
                        pricing_attestation_id=pricing.pricing_attestation_id,
                    )

                case ClientAction.REFRESH:
                    refresh_count += 1
                    continue  # Loop back to pricing

                case ClientAction.ACCEPT:
                    # Stale acceptance guard (Minsky)
                    if (
                        response.term_sheet_hash
                        != term_sheet.document_hash
                    ):
                        return RFQResult(
                            rfq_id=rfq.rfq_id,
                            outcome=RFQOutcome.FAILED,
                            rejection_reasons=(
                                "Client accepted stale term sheet",
                            ),
                        )
                    break  # Proceed to booking

                case _:
                    return RFQResult(
                        rfq_id=rfq.rfq_id,
                        outcome=RFQOutcome.FAILED,
                        rejection_reasons=(
                            f"Unexpected client action: {response.action}",
                        ),
                    )

        else:
            # Exhausted max refreshes
            return RFQResult(
                rfq_id=rfq.rfq_id,
                outcome=RFQOutcome.EXPIRED,
                rejection_reasons=(
                    f"Exceeded {MAX_REFRESHES} price refreshes",
                ),
            )

        # --- Step 7: Book trade ---
        assert pricing is not None and term_sheet is not None
        self._status = "BOOKING"
        booking = await workflow.execute_activity(
            book_trade,
            BookingInput(
                rfq=rfq,
                product=product,
                pricing=pricing,
                accepted_price=pricing.indicative_price,
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=BOOKING_RETRY,
        )
        if booking.error is not None:
            return RFQResult(
                rfq_id=rfq.rfq_id,
                outcome=RFQOutcome.FAILED,
                rejection_reasons=(f"Booking failed: {booking.error}",),
                pricing_attestation_id=pricing.pricing_attestation_id,
            )

        assert booking.result is not None

        # --- Step 8: Send confirmation ---
        self._status = "CONFIRMING"
        await workflow.execute_activity(
            send_confirmation,
            ConfirmationInput(
                rfq=rfq,
                trade_result=booking.result,
                term_sheet=term_sheet,
            ),
            start_to_close_timeout=timedelta(seconds=60),
            retry_policy=DELIVERY_RETRY,
        )

        self._status = "COMPLETED"
        return RFQResult(
            rfq_id=rfq.rfq_id,
            outcome=RFQOutcome.EXECUTED,
            trade_id=booking.result.trade_id,
            pricing_attestation_id=pricing.pricing_attestation_id,
        )
