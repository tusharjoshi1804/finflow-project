"""
Tests for apps/accounts — CRUD, ownership guards, soft-delete.
"""
import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts.models import Account

User = get_user_model()

ACCOUNTS_URL = "/api/accounts/"


def detail_url(pk):
    return f"/api/accounts/{pk}/"


def make_auth_client(user):
    client = APIClient()
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client


@pytest.fixture
def user_a(db):
    return User.objects.create_user(
        email="usera@example.com", password="Pass1234!",
        first_name="A", last_name="User"
    )


@pytest.fixture
def user_b(db):
    return User.objects.create_user(
        email="userb@example.com", password="Pass1234!",
        first_name="B", last_name="User"
    )


@pytest.fixture
def client_a(user_a):
    return make_auth_client(user_a)


@pytest.fixture
def client_b(user_b):
    return make_auth_client(user_b)


@pytest.fixture
def account_a(user_a):
    return Account.objects.create(user=user_a, name="Main Wallet", currency="USD")


# ---------------------------------------------------------------
# Model tests
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestAccountModel:
    def test_str_representation(self, account_a):
        assert "Main Wallet" in str(account_a)
        assert "USD" in str(account_a)

    def test_default_balance_is_zero(self, account_a):
        assert account_a.balance == 0

    def test_default_currency_is_usd(self, user_a):
        acc = Account.objects.create(user=user_a, name="Test")
        assert acc.currency == "USD"

    def test_soft_delete_sets_flag(self, account_a):
        account_a.soft_delete()
        assert account_a.is_deleted is True
        assert account_a.deleted_at is not None

    def test_uuid_primary_key(self, account_a):
        assert isinstance(account_a.id, uuid.UUID)


# ---------------------------------------------------------------
# List + Create  GET/POST /api/accounts/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestAccountListCreate:
    def test_list_returns_only_own_accounts(self, client_a, user_a, user_b):
        Account.objects.create(user=user_a, name="Mine", currency="USD")
        Account.objects.create(user=user_b, name="Not Mine", currency="INR")
        res = client_a.get(ACCOUNTS_URL)
        assert res.status_code == status.HTTP_200_OK
        emails = [a["owner_email"] for a in res.data["results"]]
        assert all(e == "usera@example.com" for e in emails)

    def test_list_unauthenticated_returns_401(self, api_client):
        res = api_client.get(ACCOUNTS_URL)
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_create_account_returns_201(self, client_a):
        res = client_a.post(ACCOUNTS_URL, {"name": "Savings", "currency": "INR"})
        assert res.status_code == status.HTTP_201_CREATED
        assert res.data["name"] == "Savings"

    def test_create_account_invalid_currency_returns_400(self, client_a):
        res = client_a.post(ACCOUNTS_URL, {"name": "Bad", "currency": "XYZ"})
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_account_missing_name_returns_400(self, client_a):
        res = client_a.post(ACCOUNTS_URL, {"currency": "USD"})
        assert res.status_code == status.HTTP_400_BAD_REQUEST

    def test_create_account_unauthenticated_returns_401(self, api_client):
        res = api_client.post(ACCOUNTS_URL, {"name": "X", "currency": "USD"})
        assert res.status_code == status.HTTP_401_UNAUTHORIZED

    def test_list_excludes_soft_deleted(self, client_a, user_a):
        acc = Account.objects.create(user=user_a, name="Deleted", currency="USD")
        acc.soft_delete()
        res = client_a.get(ACCOUNTS_URL)
        ids = [a["id"] for a in res.data["results"]]
        assert str(acc.id) not in ids

    def test_create_all_currencies(self, client_a):
        for currency in ["USD", "INR", "EUR", "GBP"]:
            res = client_a.post(ACCOUNTS_URL, {"name": f"{currency} wallet", "currency": currency})
            assert res.status_code == status.HTTP_201_CREATED


# ---------------------------------------------------------------
# Retrieve  GET /api/accounts/<id>/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestAccountRetrieve:
    def test_retrieve_own_account_returns_200(self, client_a, account_a):
        res = client_a.get(detail_url(account_a.id))
        assert res.status_code == status.HTTP_200_OK
        assert res.data["name"] == "Main Wallet"

    def test_retrieve_other_user_account_returns_404(self, client_b, account_a):
        res = client_b.get(detail_url(account_a.id))
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_nonexistent_returns_404(self, client_a):
        res = client_a.get(detail_url(uuid.uuid4()))
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_retrieve_unauthenticated_returns_401(self, api_client, account_a):
        res = api_client.get(detail_url(account_a.id))
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------
# Update  PATCH /api/accounts/<id>/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestAccountUpdate:
    def test_patch_name_returns_200(self, client_a, account_a):
        res = client_a.patch(detail_url(account_a.id), {"name": "Updated"})
        assert res.status_code == status.HTTP_200_OK

    def test_patch_is_active_false_returns_200(self, client_a, account_a):
        res = client_a.patch(detail_url(account_a.id), {"is_active": False})
        assert res.status_code == status.HTTP_200_OK

    def test_patch_other_user_account_returns_404(self, client_b, account_a):
        res = client_b.patch(detail_url(account_a.id), {"name": "Hacked"})
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_patch_unauthenticated_returns_401(self, api_client, account_a):
        res = api_client.patch(detail_url(account_a.id), {"name": "X"})
        assert res.status_code == status.HTTP_401_UNAUTHORIZED


# ---------------------------------------------------------------
# Delete  DELETE /api/accounts/<id>/
# ---------------------------------------------------------------
@pytest.mark.django_db
class TestAccountDelete:
    def test_delete_own_account_returns_200(self, client_a, account_a):
        res = client_a.delete(detail_url(account_a.id))
        assert res.status_code == status.HTTP_200_OK
        assert "deleted" in res.data["detail"].lower()

    def test_delete_soft_deletes_in_db(self, client_a, account_a):
        client_a.delete(detail_url(account_a.id))
        is_deleted = Account.objects.filter(id=account_a.id).values_list("is_deleted", flat=True).first()
        assert is_deleted in (True, 1)

    def test_delete_other_user_account_returns_404(self, client_b, account_a):
        res = client_b.delete(detail_url(account_a.id))
        assert res.status_code == status.HTTP_404_NOT_FOUND

    def test_delete_unauthenticated_returns_401(self, api_client, account_a):
        res = api_client.delete(detail_url(account_a.id))
        assert res.status_code == status.HTTP_401_UNAUTHORIZED
