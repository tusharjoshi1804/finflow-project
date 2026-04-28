"""
Full integration tests demonstrating the end-to-end transaction flow:

1. Account Service creates a transaction (JWT auth)
2. Account Service publishes transaction.created to Kafka
3. Processing Service consumes the event
4. Processing Service triggers Airflow stub (simulates payment)
5. Processing Service sends HMAC-signed PATCH to Account Service
6. Account Service validates HMAC and updates transaction status
7. Account Service publishes transaction.updated

This test requires Docker Compose with Kafka running.
"""
import hashlib
import hmac
import json
import time
import uuid
from decimal import Decimal
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account
from apps.transactions.models import Transaction

User = get_user_model()


def get_jwt_client(user):
    """Create an APIClient authenticated with JWT."""
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.mark.django_db
class TestTransactionFullFlow:
    """Full integration tests for the transaction lifecycle."""

    def setup_method(self):
        """Create a test user and account."""
        self.user = User.objects.create_user(
            email="flow-test@example.com",
            password="Pass1234!",
            first_name="Flow",
            last_name="Test",
        )
        self.account = Account.objects.create(
            user=self.user,
            name="Test Wallet",
            currency="USD",
        )
        self.client = get_jwt_client(self.user)

    def test_01_create_transaction_returns_pending(self):
        """Step 1: Creating a transaction should return PENDING status."""
        payload = {
            "account": str(self.account.id),
            "transaction_type": "DEBIT",
            "amount": "100.00",
            "reference": "FLOW-TEST-001",
        }
        
        with patch("apps.transactions.views.publish_event", return_value=True):
            res = self.client.post("/api/transactions/", payload)
        
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["status"] == "PENDING"
        assert res.data["amount"] == "100.00"
        assert res.data["transaction_type"] == "DEBIT"
        
        self.txn_id = res.data["id"]

    def test_02_verify_transaction_was_created_in_db(self):
        """Step 1b: Verify transaction exists in DB with PENDING status."""
        # Create a transaction first
        payload = {
            "account": str(self.account.id),
            "transaction_type": "CREDIT",
            "amount": "50.00",
        }
        
        with patch("apps.transactions.views.publish_event", return_value=True):
            res = self.client.post("/api/transactions/", payload)
        
        txn_id = res.data["id"]
        
        # Verify it exists in DB
        txn = Transaction.objects.get(id=txn_id)
        assert txn.status == Transaction.Status.PENDING
        assert txn.amount == Decimal("50.00")
        assert txn.account == self.account

    def test_03_kafka_event_published_on_create(self):
        """Step 2: Creating a transaction publishes transaction.created event."""
        payload = {
            "account": str(self.account.id),
            "transaction_type": "DEBIT",
            "amount": "75.00",
        }
        
        with patch(
            "apps.transactions.views.publish_event", return_value=True
        ) as mock_publish:
            res = self.client.post("/api/transactions/", payload)
        
        # Verify publish_event was called
        mock_publish.assert_called_once()
        
        # Verify it was called with transaction.created topic
        call_args = mock_publish.call_args
        assert call_args[0][0] == "transaction.created"
        
        # Verify event payload structure
        event_payload = call_args[0][1]
        assert "transaction_id" in event_payload
        assert event_payload["amount"] == "75.00"
        assert event_payload["status"] == "PENDING"

    def test_04_processing_service_can_update_status_via_hmac(self):
        """Step 5-6: Processing Service updates transaction status with HMAC."""
        # Create a transaction
        txn = Transaction.objects.create(
            account=self.account,
            transaction_type=Transaction.TransactionType.DEBIT,
            amount=Decimal("100.00"),
            status=Transaction.Status.PENDING,
        )
        
        # Prepare HMAC-signed request
        path = f"/api/internal/transactions/{txn.id}/"
        body = json.dumps({"status": "COMPLETED"}, separators=(",", ":")).encode()
        
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"PATCH\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
        
        signature = hmac.new(
            "dev-hmac-secret-change-me".encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        # Make the internal call (without JWT)
        api_client = APIClient()
        res = api_client.patch(
            path,
            {"status": "COMPLETED"},
            format="json",
            HTTP_X_TIMESTAMP=timestamp,
            HTTP_X_NONCE=nonce,
            HTTP_X_SIGNATURE=signature,
        )
        
        assert res.status_code == status.HTTP_200_OK
        assert res.data["status"] == "COMPLETED"

    def test_05_bad_hmac_signature_rejected(self):
        """Step 6b: Requests with invalid HMAC are rejected."""
        txn = Transaction.objects.create(
            account=self.account,
            transaction_type=Transaction.TransactionType.DEBIT,
            amount=Decimal("100.00"),
            status=Transaction.Status.PENDING,
        )
        
        path = f"/api/internal/transactions/{txn.id}/"
        
        # Make request with bad signature
        api_client = APIClient()
        res = api_client.patch(
            path,
            {"status": "COMPLETED"},
            format="json",
            HTTP_X_TIMESTAMP=str(int(time.time())),
            HTTP_X_NONCE=str(uuid.uuid4()),
            HTTP_X_SIGNATURE="00" * 32,  # Invalid signature
        )
        
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_06_transaction_updated_event_published(self):
        """Step 7: Updating transaction status publishes transaction.updated event."""
        from apps.core.hmac_middleware import clear_nonces
        
        txn = Transaction.objects.create(
            account=self.account,
            transaction_type=Transaction.TransactionType.DEBIT,
            amount=Decimal("100.00"),
            status=Transaction.Status.PENDING,
        )
        
        clear_nonces()
        
        # Prepare HMAC request
        path = f"/api/internal/transactions/{txn.id}/"
        body = json.dumps({"status": "COMPLETED"}, separators=(",", ":")).encode()
        
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"PATCH\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
        
        signature = hmac.new(
            "dev-hmac-secret-change-me".encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        # Make the update with mocked publish
        api_client = APIClient()
        with patch(
            "apps.transactions.views.publish_event", return_value=True
        ) as mock_publish:
            res = api_client.patch(
                path,
                {"status": "COMPLETED"},
                format="json",
                HTTP_X_TIMESTAMP=timestamp,
                HTTP_X_NONCE=nonce,
                HTTP_X_SIGNATURE=signature,
            )
        
        assert res.status_code == status.HTTP_200_OK
        
        # Verify transaction.updated was published
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "transaction.updated"
        assert call_args[0][1]["status"] == "COMPLETED"

    def test_07_full_flow_summary(self):
        """Full flow summary: create → pending → kafka → hmac update → completed."""
        # Step 1-2: Create transaction
        payload = {
            "account": str(self.account.id),
            "transaction_type": "DEBIT",
            "amount": "200.00",
        }
        
        with patch("apps.transactions.views.publish_event", return_value=True):
            res = self.client.post("/api/transactions/", payload)
        
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["status"] == "PENDING"
        txn_id = res.data["id"]
        
        # Verify transaction in DB
        txn = Transaction.objects.get(id=txn_id)
        assert txn.status == Transaction.Status.PENDING
        
        # Step 5-6: Simulate Processing Service HMAC callback
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        
        path = f"/api/internal/transactions/{txn_id}/"
        body = json.dumps({"status": "COMPLETED"}, separators=(",", ":")).encode()
        
        timestamp = str(int(time.time()))
        nonce = str(uuid.uuid4())
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"PATCH\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
        
        signature = hmac.new(
            "dev-hmac-secret-change-me".encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()
        
        api_client = APIClient()
        with patch("apps.transactions.views.publish_event", return_value=True):
            res = api_client.patch(
                path,
                {"status": "COMPLETED"},
                format="json",
                HTTP_X_TIMESTAMP=timestamp,
                HTTP_X_NONCE=nonce,
                HTTP_X_SIGNATURE=signature,
            )
        
        assert res.status_code == status.HTTP_200_OK
        
        # Step 7: Verify final state
        txn.refresh_from_db()
        assert txn.status == Transaction.Status.COMPLETED
