"""Tests for apps/audit — AuditLog model and PII scrubbing."""
import uuid

import pytest
from django.contrib.auth import get_user_model

from apps.audit.models import AuditLog

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(
        email="audit@example.com", password="Pass1234!",
        first_name="Audit", last_name="User"
    )


@pytest.mark.django_db
class TestAuditLogModel:
    def test_log_creates_record(self, user):
        log = AuditLog.log(
            action="USER_CREATED",
            resource="User",
            resource_id=str(user.id),
            actor=user,
            new_data={"email": "audit@example.com", "first_name": "Audit"},
        )
        assert log.pk is not None
        assert log.action == "USER_CREATED"
        assert log.resource == "User"
        assert log.resource_id == str(user.id)

    def test_log_scrubs_password_from_new_data(self, user):
        log = AuditLog.log(
            action="USER_CREATED",
            resource="User",
            resource_id=str(user.id),
            new_data={"email": "x@x.com", "password": "secret123"},
        )
        assert log.new_data["password"] == "***REDACTED***"

    def test_log_scrubs_token_from_old_data(self, user):
        log = AuditLog.log(
            action="TOKEN_ISSUED",
            resource="User",
            resource_id=str(user.id),
            old_data={"token": "abc.def.ghi"},
        )
        assert log.old_data["token"] == "***REDACTED***"

    def test_log_without_actor(self):
        log = AuditLog.log(
            action="SYSTEM_EVENT",
            resource="Transaction",
            resource_id=str(uuid.uuid4()),
        )
        assert log.actor is None

    def test_log_with_ip_address(self, user):
        log = AuditLog.log(
            action="LOGIN",
            resource="User",
            resource_id=str(user.id),
            actor=user,
            ip_address="192.168.1.1",
        )
        assert log.ip_address == "192.168.1.1"

    def test_str_representation(self, user):
        log = AuditLog.log(
            action="ACCOUNT_DELETED",
            resource="Account",
            resource_id="some-uuid",
        )
        s = str(log)
        assert "ACCOUNT_DELETED" in s
        assert "Account" in s

    def test_log_none_data_fields(self, user):
        log = AuditLog.log(
            action="VIEW",
            resource="Document",
            resource_id=str(uuid.uuid4()),
            old_data=None,
            new_data=None,
        )
        assert log.old_data is None
        assert log.new_data is None

    def test_uuid_primary_key(self, user):
        log = AuditLog.log(
            action="TEST", resource="User", resource_id=str(user.id)
        )
        assert isinstance(log.id, uuid.UUID)

    def test_ordering_newest_first(self, user):
        log1 = AuditLog.log(action="FIRST", resource="User", resource_id=str(user.id))
        log2 = AuditLog.log(action="SECOND", resource="User", resource_id=str(user.id))
        logs = list(AuditLog.objects.all())
        assert logs[0].action == "SECOND"
        assert logs[1].action == "FIRST"

    def test_log_scrubs_nested_password(self, user):
        log = AuditLog.log(
            action="UPDATE",
            resource="User",
            resource_id=str(user.id),
            new_data={"user": {"password": "hidden", "email": "a@b.com"}},
        )
        assert log.new_data["user"]["password"] == "***REDACTED***"
