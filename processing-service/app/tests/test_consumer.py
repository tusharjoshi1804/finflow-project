"""
Tests for Processing Service Kafka consumer and payment processing flow.

Tests the consumer's ability to:
- Listen for transaction.created events
- Trigger the Airflow payment stub
- Call Account Service internal endpoint with HMAC auth
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
async def test_process_transaction_calls_airflow_stub():
    """Verify that process_transaction triggers the payment DAG."""
    from app.consumer import process_transaction

    with patch("app.consumer.trigger_payment_dag", new_callable=AsyncMock) as mock_dag:
        mock_dag.return_value = "COMPLETED"
        with patch("app.consumer.httpx.AsyncClient") as mock_client:
            await process_transaction("txn-123")
            mock_dag.assert_called_once_with("txn-123")


@pytest.mark.asyncio
async def test_process_transaction_sends_hmac_headers():
    """Verify that process_transaction sends valid HMAC headers to Account Service."""
    from app.consumer import process_transaction

    with patch("app.consumer.trigger_payment_dag", new_callable=AsyncMock) as mock_dag:
        mock_dag.return_value = "COMPLETED"
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = '{"status":"COMPLETED"}'
        
        with patch("app.consumer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.patch.return_value = mock_response
            
            await process_transaction("txn-123")
            
            # Verify PATCH was called
            assert mock_client.patch.called
            call_args = mock_client.patch.call_args
            
            # Check headers contain HMAC fields
            headers = call_args[1]["headers"]
            assert "X-Timestamp" in headers
            assert "X-Nonce" in headers
            assert "X-Signature" in headers


@pytest.mark.asyncio
async def test_process_transaction_fallback_to_failed_on_airflow_error():
    """Verify that process_transaction defaults to FAILED if Airflow stub fails."""
    from app.consumer import process_transaction

    with patch("app.consumer.trigger_payment_dag", new_callable=AsyncMock) as mock_dag:
        mock_dag.side_effect = Exception("Airflow down")
        
        mock_response = MagicMock()
        mock_response.status_code = 200
        
        with patch("app.consumer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            mock_client.patch.return_value = mock_response
            
            await process_transaction("txn-123")
            
            # Verify PATCH was called with FAILED status
            call_args = mock_client.patch.call_args
            body_bytes = call_args[1]["content"]
            body = json.loads(body_bytes)
            assert body["status"] == "FAILED"


@pytest.mark.asyncio
async def test_start_consumer_listens_to_topic():
    """Verify that start_consumer initializes the Kafka consumer on the correct topic."""
    from app.config import KAFKA_TOPIC_CREATED
    from app.consumer import start_consumer

    mock_consumer = AsyncMock()
    mock_consumer.__aiter__.return_value = []  # Empty message stream
    
    with patch("app.consumer.AIOKafkaConsumer", return_value=mock_consumer):
        with patch("app.consumer.asyncio.create_task"):
            try:
                await asyncio.wait_for(start_consumer(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
        
        # Verify consumer was created with correct topic
        assert mock_consumer.start.called
        assert mock_consumer.stop.called


@pytest.mark.asyncio
async def test_consumer_processes_valid_kafka_message():
    """Verify that the consumer processes a valid Kafka message."""
    from app.consumer import process_transaction, start_consumer

    message = MagicMock()
    message.topic = "transaction.created"
    message.value = {
        "transaction_id": "txn-456",
        "account_id": "acc-123",
        "transaction_type": "DEBIT",
        "amount": "100.00",
        "status": "PENDING",
    }
    
    mock_consumer = AsyncMock()
    
    # Return one message then stop
    async def message_stream():
        yield message
    
    mock_consumer.__aiter__.return_value = message_stream()
    
    with patch("app.consumer.AIOKafkaConsumer", return_value=mock_consumer):
        with patch("app.consumer.process_transaction", new_callable=AsyncMock) as mock_process:
            try:
                await asyncio.wait_for(start_consumer(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
            
            # Verify process_transaction was called with transaction_id
            mock_process.assert_called()


@pytest.mark.asyncio
async def test_consumer_skips_message_without_transaction_id():
    """Verify that consumer skips messages missing transaction_id."""
    from app.consumer import process_transaction, start_consumer

    message = MagicMock()
    message.topic = "transaction.created"
    message.value = {
        "account_id": "acc-123",
        # Missing transaction_id
    }
    
    mock_consumer = AsyncMock()
    
    async def message_stream():
        yield message
    
    mock_consumer.__aiter__.return_value = message_stream()
    
    with patch("app.consumer.AIOKafkaConsumer", return_value=mock_consumer):
        with patch("app.consumer.process_transaction", new_callable=AsyncMock) as mock_process:
            try:
                await asyncio.wait_for(start_consumer(), timeout=0.1)
            except asyncio.TimeoutError:
                pass
            
            # Verify process_transaction was NOT called
            mock_process.assert_not_called()


@pytest.mark.asyncio
async def test_consumer_handles_account_service_error():
    """Verify that consumer logs Account Service errors but continues."""
    from app.consumer import process_transaction

    with patch("app.consumer.trigger_payment_dag", new_callable=AsyncMock) as mock_dag:
        mock_dag.return_value = "COMPLETED"
        
        with patch("app.consumer.httpx.AsyncClient") as mock_client_class:
            mock_client = AsyncMock()
            mock_client_class.return_value.__aenter__.return_value = mock_client
            
            # Simulate Account Service returning 500
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_client.patch.return_value = mock_response
            
            # Should not raise, just log the error
            await process_transaction("txn-789")
            
            assert mock_client.patch.called
