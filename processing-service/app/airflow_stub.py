"""
Airflow stub for FinFlow Processing Service.

In production this would call the real Airflow REST API to trigger
a DAG run and poll for completion. Here we simulate the behaviour
so the rest of the processing pipeline works end-to-end.
"""
import asyncio
import logging
import random

logger = logging.getLogger(__name__)


async def trigger_payment_dag(transaction_id: str) -> str:
    """
    Simulate triggering an Airflow DAG for payment processing.

    Returns "COMPLETED" or "FAILED" to reflect the payment outcome.
    In a real implementation this would:
      1. POST /api/v1/dags/{dag_id}/dagRuns  to trigger the run
      2. Poll GET /api/v1/dags/{dag_id}/dagRuns/{run_id} until done
    """
    logger.info(
        "Airflow stub: triggering payment DAG",
        extra={"transaction_id": transaction_id},
    )

    # Simulate async processing delay (50–150 ms)
    await asyncio.sleep(random.uniform(0.05, 0.15))

    # 90% success rate in the stub
    outcome = "COMPLETED" if random.random() < 0.9 else "FAILED"

    logger.info(
        "Airflow stub: DAG run complete",
        extra={"transaction_id": transaction_id, "outcome": outcome},
    )
    return outcome
