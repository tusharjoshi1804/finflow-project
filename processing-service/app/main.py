"""
FinFlow Processing Service — FastAPI application entry point.

Starts the Kafka consumer as a background task on startup.
"""
import asyncio
import logging

from fastapi import FastAPI

from app.config import LOG_LEVEL

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL.upper(), logging.INFO),
    format="[%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="FinFlow Processing Service",
    description="Kafka consumer + payment processing for FinFlow.",
    version="1.0.0",
)

_consumer_task = None


@app.on_event("startup")
async def startup_event():
    """Launch the Kafka consumer as a background asyncio task."""
    global _consumer_task
    try:
        from app.consumer import start_consumer
        _consumer_task = asyncio.create_task(start_consumer())
        logger.info("Processing service started — Kafka consumer running")
    except Exception as exc:
        logger.warning("Kafka consumer could not start: %s", exc)


@app.on_event("shutdown")
async def shutdown_event():
    """Cancel the consumer task on shutdown."""
    global _consumer_task
    if _consumer_task and not _consumer_task.done():
        _consumer_task.cancel()
        try:
            await _consumer_task
        except asyncio.CancelledError:
            pass
    logger.info("Processing service shut down cleanly")


@app.get("/", tags=["health"])
async def root():
    """Root endpoint for the processing service."""
    return {"status": "ok", "service": "processing-service", "message": "Processing service is running"}


@app.get("/health", tags=["health"])
async def health_check():
    """Health check endpoint — always returns 200 OK."""
    return {"status": "ok", "service": "processing-service"}
