"""
AuditLog model — records every significant state change in FinFlow.

PII fields (email, etc.) are scrubbed before saving using the same
_scrub() utility as the JSON logger.
"""
import json

from django.conf import settings
from django.db import models

from apps.core.logging import _scrub
from apps.users.models import BaseModel


class AuditLog(BaseModel):
    """
    Immutable record of a state-change event.

    Fields
    ------
    actor        — user who triggered the action (null for system events)
    action       — short verb: USER_CREATED, ACCOUNT_DELETED, etc.
    resource     — model name: User, Account, Transaction, Document
    resource_id  — UUID of the affected object (stored as string)
    old_data     — JSON snapshot before the change (PII scrubbed)
    new_data     — JSON snapshot after the change (PII scrubbed)
    ip_address   — request IP (optional)
    """

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="audit_logs",
    )
    action = models.CharField(max_length=100)
    resource = models.CharField(max_length=100)
    resource_id = models.CharField(max_length=36)
    old_data = models.JSONField(null=True, blank=True)
    new_data = models.JSONField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = "audit_logs"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.action} on {self.resource}({self.resource_id})"

    @classmethod
    def log(
        cls,
        action: str,
        resource: str,
        resource_id: str,
        actor=None,
        old_data: dict | None = None,
        new_data: dict | None = None,
        ip_address: str | None = None,
    ) -> "AuditLog":
        """Convenience factory — scrubs PII before persisting."""
        return cls.objects.create(
            actor=actor,
            action=action,
            resource=resource,
            resource_id=str(resource_id),
            old_data=_scrub(old_data) if old_data else None,
            new_data=_scrub(new_data) if new_data else None,
            ip_address=ip_address,
        )
