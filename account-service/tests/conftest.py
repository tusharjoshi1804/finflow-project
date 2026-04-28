"""
Shared pytest fixtures for the account-service test suite.
"""
import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

User = get_user_model()


@pytest.fixture
def api_client():
    """Unauthenticated DRF test client."""
    return APIClient()


@pytest.fixture
def create_user(db):
    """Factory fixture: creates and returns a User instance."""
    def _create(
        email="testuser@example.com",
        password="StrongPass123!",
        first_name="Test",
        last_name="User",
        **kwargs,
    ):
        return User.objects.create_user(
            email=email,
            password=password,
            first_name=first_name,
            last_name=last_name,
            **kwargs,
        )
    return _create


@pytest.fixture
def user(create_user):
    """A single ready-made user."""
    return create_user()


@pytest.fixture
def auth_client(user):
    """APIClient pre-authenticated as `user` via JWT."""
    client = APIClient()
    from rest_framework_simplejwt.tokens import RefreshToken
    refresh = RefreshToken.for_user(user)
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {str(refresh.access_token)}")
    return client, user
