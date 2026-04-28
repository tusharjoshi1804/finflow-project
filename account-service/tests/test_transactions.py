"""
Tests for apps/transactions — create, list, get, internal status update,
and Kafka producer (mocked).
"""
import uuid
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account
from apps.transactions.models import Transaction

User = get_user_model()

TXN_URL = "/api/transactions/"


def detail_url(pk):
    return f"/api/transactions/{pk}/"


def internal_url(pk):
    return f"/api/internal/transactions/{pk}/"


def make_auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.fixture
def user_a(db):
    return User.objects.create_user(
        email="txn_usera@example.com", password="Pass1234!",
        first_name="A", last_name="T"
    )


@pytest.fixture
def user_b(db):
    return User.objects.create_user(
        email="txn_userb@example.com", password="Pass1234!",
        first_name="B", last_name="T"
    )


@pytest.fixture
def client_a(user_a):
    return make_auth_client(user_a)


@pytest.fixture
def account_a(user_a):
    return Account.objects.create(user=user_a, name="Wallet A", currency="USD")


@pytest.fixture
def account_b(user_b):
    return Account.objects.create(user=user_b, name="Wallet B", currency="USD")


@pytest.fixture
def pending_txn(account_a):
    return Transaction.objects.create(
        account=account_a,
        transaction_type=Transaction.TransactionType.DEBIT,
        amount=Decimal("100.00"),
        status=Transaction.Status.PENDING,
    )


# ---------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestTransactionModel:
    def test_default_status_is_pending(self, account_a):
        txn = Transaction.objects.create(
            account=account_a,
            transaction_type="DEBIT",
            amount=Decimal("50.00"),
        )
        assert txn.status == Transaction.Status.PENDING

    def test_str_representation(self, pending_txn):
        s = str(pending_txn)
        assert "DEBIT" in s
        assert "PENDING" in s

    def test_uuid_primary_key(self, pending_txn):
        assert isinstance(pending_txn.id, uuid.UUID)

    def test_transaction_type_choices(self, account_a):
        credit = Transaction.objects.create(
            account=account_a,
            transaction_type=Transaction.TransactionType.CREDIT,
            amount=Decimal("200.00"),
        )
        assert credit.transaction_type == "CREDIT"


# ---------------------------------------------------------------
# Create  POST /api/transactions/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestTransactionCreate:
    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_create_returns_201(self, mock_publish, client_a, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "DEBIT",
            "amount": "150.00",
        }
        res = client_a.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["status"] == "PENDING"

    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_create_publishes_kafka_event(self, mock_publish, client_a, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "CREDIT",
            "amount": "50.00",
        }
        client_a.post(TXN_URL, payload)
        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == "transaction.created"

    @patch("apps.transactions.views.publish_event", return_value=False)
    def test_create_succeeds_even_if_kafka_fails(self, mock_publish, client_a, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "DEBIT",
            "amount": "75.00",
        }
        res = client_a.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_201_CREATED

    def test_create_zero_amount_returns_400(self, client_a, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "DEBIT",
            "amount": "0.00",
        }
        res = client_a.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_negative_amount_returns_400(self, client_a, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "DEBIT",
            "amount": "-10.00",
        }
        res = client_a.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_against_other_user_account_returns_400(
        self, client_a, account_b
    ):
        payload = {
            "account": str(account_b.id),
            "transaction_type": "DEBIT",
            "amount": "50.00",
        }
        res = client_a.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_unauthenticated_returns_401(self, api_client, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "DEBIT",
            "amount": "50.00",
        }
        res = api_client.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_missing_amount_returns_400(self, client_a, account_a):
        res = client_a.post(TXN_URL, {"account": str(account_a.id), "transaction_type": "DEBIT"})
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_create_with_reference(self, mock_publish, client_a, account_a):
        payload = {
            "account": str(account_a.id),
            "transaction_type": "CREDIT",
            "amount": "99.99",
            "reference": "REF-001",
        }
        res = client_a.post(TXN_URL, payload)
        assert res.status_code == status.HTTP_201_CREATED


# ---------------------------------------------------------------
# List  GET /api/transactions/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestTransactionList:
    def test_list_returns_only_own_transactions(
        self, client_a, account_a, account_b
    ):
        Transaction.objects.create(
            account=account_a, transaction_type="DEBIT", amount=Decimal("10.00")
        )
        Transaction.objects.create(
            account=account_b, transaction_type="CREDIT", amount=Decimal("20.00")
        )
        res = client_a.get(TXN_URL)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == 1

    def test_list_unauthenticated_returns_401(self, api_client):
        res = api_client.get(TXN_URL)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_empty_for_new_user(self, client_a):
        res = client_a.get(TXN_URL)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["count"] == 0


# ---------------------------------------------------------------
# Retrieve  GET /api/transactions/<id>/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestTransactionRetrieve:
    def test_retrieve_own_transaction(self, client_a, pending_txn):
        res = client_a.get(detail_url(pending_txn.id))
        assert res.status_code == status.HTTP_200_OK
        assert res.data["status"] == "PENDING"

    def test_retrieve_other_user_transaction_returns_404(
        self, client_a, account_b
    ):
        txn = Transaction.objects.create(
            account=account_b, transaction_type="DEBIT", amount=Decimal("10.00")
        )
        res = client_a.get(detail_url(txn.id))
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_nonexistent_returns_404(self, client_a):
        res = client_a.get(detail_url(uuid.uuid4()))
        assert res.status_code == status.HTTP_404_NOT_FOUND


# ---------------------------------------------------------------
# Internal status update  PATCH /api/internal/transactions/<id>/
# ---------------------------------------------------------------
import hashlib
import hmac as hmac_lib
import time as time_lib
import json as json_lib


def make_hmac_headers(method, path, body_bytes, secret="dev-hmac-secret-change-me"):
    """Helper: generate valid HMAC headers for internal requests."""
    import uuid as uuid_lib
    timestamp = str(int(time_lib.time()))
    nonce = str(uuid_lib.uuid4())
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    message = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    signature = hmac_lib.new(
        secret.encode(), message.encode(), hashlib.sha256
    ).hexdigest()
    return {"HTTP_X_TIMESTAMP": timestamp, "HTTP_X_NONCE": nonce, "HTTP_X_SIGNATURE": signature}


@pytest.mark.django_db
class TestInternalTransactionStatus:
    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_update_to_completed(self, mock_publish, api_client, pending_txn):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        path = f"/api/internal/transactions/{pending_txn.id}/"
        body = json_lib.dumps({"status": "COMPLETED"}).encode()
        headers = make_hmac_headers("PATCH", path, body)
        res = api_client.patch(path, {"status": "COMPLETED"}, **headers)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["status"] == "COMPLETED"

    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_update_to_failed(self, mock_publish, api_client, pending_txn):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        path = f"/api/internal/transactions/{pending_txn.id}/"
        body = json_lib.dumps({"status": "FAILED"}).encode()
        headers = make_hmac_headers("PATCH", path, body)
        res = api_client.patch(path, {"status": "FAILED"}, **headers)
        assert res.status_code == status.HTTP_200_OK
        assert res.data["status"] == "FAILED"

    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_update_publishes_kafka_event(self, mock_publish, api_client, pending_txn):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        path = f"/api/internal/transactions/{pending_txn.id}/"
        body = json_lib.dumps({"status": "COMPLETED"}).encode()
        headers = make_hmac_headers("PATCH", path, body)
        api_client.patch(path, {"status": "COMPLETED"}, **headers)
        mock_publish.assert_called_once()
        assert mock_publish.call_args[0][0] == "transaction.updated"

    def test_update_missing_hmac_headers_returns_401(self, api_client, pending_txn):
        path = f"/api/internal/transactions/{pending_txn.id}/"
        res = api_client.patch(path, {"status": "COMPLETED"})
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_bad_signature_returns_401(self, api_client, pending_txn):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        path = f"/api/internal/transactions/{pending_txn.id}/"
        body = json_lib.dumps({"status": "COMPLETED"}).encode()
        headers = make_hmac_headers("PATCH", path, body, secret="wrong-secret")
        res = api_client.patch(path, {"status": "COMPLETED"}, **headers)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_update_invalid_status_returns_400(self, api_client, pending_txn):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        path = f"/api/internal/transactions/{pending_txn.id}/"
        body = json_lib.dumps({"status": "PENDING"}).encode()
        headers = make_hmac_headers("PATCH", path, body)
        res = api_client.patch(path, {"status": "PENDING"}, **headers)
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    @patch("apps.transactions.views.publish_event", return_value=True)
    def test_update_already_completed_returns_400(
        self, mock_publish, api_client, account_a
    ):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        txn = Transaction.objects.create(
            account=account_a,
            transaction_type="DEBIT",
            amount=Decimal("50.00"),
            status=Transaction.Status.COMPLETED,
        )
        path = f"/api/internal/transactions/{txn.id}/"
        body = json_lib.dumps({"status": "FAILED"}).encode()
        headers = make_hmac_headers("PATCH", path, body)
        res = api_client.patch(path, {"status": "FAILED"}, **headers)
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_update_nonexistent_returns_404(self, api_client):
        from apps.core.hmac_middleware import clear_nonces
        clear_nonces()
        fake_id = uuid.uuid4()
        path = f"/api/internal/transactions/{fake_id}/"
        body = json_lib.dumps({"status": "COMPLETED"}).encode()
        headers = make_hmac_headers("PATCH", path, body)
        res = api_client.patch(path, {"status": "COMPLETED"}, **headers)
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_stale_timestamp_returns_401(self, api_client, pending_txn):
        from apps.core.hmac_middleware import clear_nonces
        import uuid as uuid_lib
        clear_nonces()
        path = f"/api/internal/transactions/{pending_txn.id}/"
        body = json_lib.dumps({"status": "COMPLETED"}).encode()
        stale_ts = str(int(time_lib.time()) - 400)
        nonce = str(uuid_lib.uuid4())
        body_hash = hashlib.sha256(body).hexdigest()
        message = f"PATCH\n{path}\n{stale_ts}\n{nonce}\n{body_hash}"
        sig = hmac_lib.new(b"dev-hmac-secret-change-me", message.encode(), hashlib.sha256).hexdigest()
        res = api_client.patch(
            path, {"status": "COMPLETED"},
            HTTP_X_TIMESTAMP=stale_ts, HTTP_X_NONCE=nonce, HTTP_X_SIGNATURE=sig
        )
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------
# Kafka producer unit tests (no real Kafka needed)
# ---------------------------------------------------------------
class TestKafkaProducer:
    @patch("apps.core.kafka_producer._get_producer", return_value=None)
    def test_publish_returns_false_when_no_producer(self, mock_get):
        from apps.core.kafka_producer import publish_event
        result = publish_event("test.topic", {"key": "value"})
        assert result is False

    @patch("apps.core.kafka_producer._get_producer")
    def test_publish_returns_true_on_success(self, mock_get):
        from apps.core.kafka_producer import publish_event
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_producer.send.return_value = mock_future
        mock_future.get.return_value = None
        mock_get.return_value = mock_producer
        result = publish_event("test.topic", {"key": "value"})
        assert result is True
        mock_producer.send.assert_called_once()
        mock_producer.flush.assert_called_once()

    @patch("apps.core.kafka_producer._get_producer")
    def test_publish_returns_false_on_send_exception(self, mock_get):
        from apps.core.kafka_producer import publish_event
        mock_producer = MagicMock()
        mock_producer.send.side_effect = Exception("Kafka down")
        mock_get.return_value = mock_producer
        result = publish_event("test.topic", {"key": "value"})
        assert result is False

    @patch("apps.core.kafka_producer._get_producer")
    def test_publish_closes_producer_after_success(self, mock_get):
        from apps.core.kafka_producer import publish_event
        mock_producer = MagicMock()
        mock_future = MagicMock()
        mock_producer.send.return_value = mock_future
        mock_get.return_value = mock_producer
        publish_event("test.topic", {"data": "x"})
        mock_producer.close.assert_called_once()

    @patch("apps.core.kafka_producer._get_producer")
    def test_publish_closes_producer_even_on_failure(self, mock_get):
        from apps.core.kafka_producer import publish_event
        mock_producer = MagicMock()
        mock_producer.send.side_effect = Exception("fail")
        mock_get.return_value = mock_producer
        publish_event("test.topic", {"data": "x"})
        mock_producer.close.assert_called_once()

    def test_get_producer_returns_none_when_kafka_unavailable(self):
        from apps.core.kafka_producer import _get_producer
        with patch("apps.core.kafka_producer.KafkaProducer", side_effect=Exception("no kafka")):
            result = _get_producer()
            assert result is None
