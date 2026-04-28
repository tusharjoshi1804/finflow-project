"""
Kafka producer utility for FinFlow.

Publish failures are caught and logged — they must never crash
the HTTP request that triggered the publish.
"""
import json
import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


def _get_producer():
    """Lazily create a KafkaProducer. Returns None if Kafka is unavailable."""
    try:
        from kafka import KafkaProducer  # type: ignore
        producer = KafkaProducer(
            bootstrap_servers=settings.KAFKA_BROKER,
            value_serializer=lambda v: json.dumps(v, default=str).encode("utf-8"),
            request_timeout_ms=3000,
            retries=1,
        )
        return producer
    except Exception as exc:
        logger.warning("Kafka unavailable — producer not created: %s", exc)
        return None


def publish_event(topic: str, payload: dict[str, Any]) -> bool:
    """
    Publish a JSON payload to a Kafka topic.

    Returns True on success, False on any failure.
    Failures are logged but never re-raised.
    """
    producer = _get_producer()
    if producer is None:
        logger.warning(
            "Kafka publish skipped — no producer available",
            extra={"topic": topic, "payload_keys": list(payload.keys())},
        )
        return False
    try:
        future = producer.send(topic, payload)
        producer.flush(timeout=5)
        future.get(timeout=5)
        logger.info("Kafka event published", extra={"topic": topic})
        return True
    except Exception as exc:
        logger.error(
            "Kafka publish failed — continuing request",
            extra={"topic": topic, "error": str(exc)},
        )
        return False
    finally:
        try:
            producer.close(timeout=2)
        except Exception:
            pass
