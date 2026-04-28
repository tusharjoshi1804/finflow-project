"""
Kafka consumer for FinFlow Processing Service.

Listens on transaction.created, triggers Airflow stub,
then calls Account Service internal endpoint with HMAC auth
to update the transaction status.
"""
import asyncio
import hashlib
import json
import logging

import httpx
from aiokafka import AIOKafkaConsumer  # type: ignore

from app.airflow_stub import trigger_payment_dag
from app.config import (
    ACCOUNT_SERVICE_URL,
    KAFKA_BROKER,
    KAFKA_GROUP_ID,
    KAFKA_TOPIC_CREATED,
)
from app.hmac_auth import sign_request

logger = logging.getLogger(__name__)


async def process_transaction(transaction_id: str) -> None:
    """
    Full processing pipeline for one transaction:
      1. Trigger Airflow stub
      2. HMAC-sign and PATCH Account Service
    """
    try:
        outcome = await trigger_payment_dag(transaction_id)
    except Exception as exc:
        logger.error(
            "Airflow stub failed: %s — defaulting to FAILED",
            exc,
            extra={"transaction_id": transaction_id},
        )
        outcome = "FAILED"

    path = f"/api/internal/transactions/{transaction_id}/"
    body = json.dumps({"status": outcome}).encode("utf-8")
    headers = sign_request("PATCH", path, body)
    headers["Content-Type"] = "application/json"

    url = f"{ACCOUNT_SERVICE_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.patch(url, content=body, headers=headers)
            if response.status_code == 200:
                logger.info(
                    "Transaction status updated",
                    extra={"transaction_id": transaction_id, "status": outcome},
                )
            else:
                logger.error(
                    "Account Service returned error",
                    extra={
                        "transaction_id": transaction_id,
                        "status_code": response.status_code,
                        "body": response.text[:200],
                    },
                )
    except Exception as exc:
        logger.error(
            "Failed to call Account Service: %s",
            exc,
            extra={"transaction_id": transaction_id},
        )


async def start_consumer() -> None:
    """Start the Kafka consumer loop. Runs indefinitely."""
    consumer = AIOKafkaConsumer(
        KAFKA_TOPIC_CREATED,
        bootstrap_servers=KAFKA_BROKER,
        group_id=KAFKA_GROUP_ID,
        value_deserializer=lambda v: json.loads(v.decode("utf-8")),
        auto_offset_reset="earliest",
    )
    await consumer.start()
    logger.info("Kafka consumer started — listening on %s", KAFKA_TOPIC_CREATED)
    try:
        async for message in consumer:
            payload = message.value
            transaction_id = payload.get("transaction_id")
            if not transaction_id:
                logger.warning("Received event without transaction_id: %s", payload)
                continue
            logger.info(
                "Kafka event received",
                extra={"topic": message.topic, "transaction_id": transaction_id},
            )
            asyncio.create_task(process_transaction(transaction_id))
    except asyncio.CancelledError:
        logger.info("Kafka consumer shutting down")
    finally:
        await consumer.stop()
