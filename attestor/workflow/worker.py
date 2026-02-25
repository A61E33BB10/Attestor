"""Worker configuration for the structured derivatives RFQ workflow.

Starts a Temporal worker with the RFQ workflow and all activities
registered on the appropriate task queue.

Usage::

    import asyncio
    from attestor.workflow.worker import run_worker

    asyncio.run(run_worker())
"""

from __future__ import annotations

from temporalio.client import Client
from temporalio.worker import Worker

from attestor.workflow.activities import (
    book_trade,
    generate_and_send_indicative,
    map_to_cdm_product,
    price_product,
    run_pre_trade_checks,
    send_confirmation,
)
from attestor.workflow.rfq_workflow import StructuredProductRFQWorkflow

TASK_QUEUE = "structured-rfq"


async def run_worker(
    *,
    target_host: str = "localhost:7233",
    namespace: str = "default",
    task_queue: str = TASK_QUEUE,
) -> None:
    """Connect to Temporal and run the worker until interrupted."""
    from attestor.workflow.converter import ATTESTOR_DATA_CONVERTER

    client = await Client.connect(
        target_host, namespace=namespace,
        data_converter=ATTESTOR_DATA_CONVERTER,
    )

    worker = Worker(
        client,
        task_queue=task_queue,
        workflows=[StructuredProductRFQWorkflow],
        activities=[
            map_to_cdm_product,
            run_pre_trade_checks,
            price_product,
            generate_and_send_indicative,
            book_trade,
            send_confirmation,
        ],
    )
    await worker.run()
