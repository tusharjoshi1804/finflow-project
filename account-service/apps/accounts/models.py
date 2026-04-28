"""
Account (wallet) model for FinFlow.

Each user can hold multiple accounts in different currencies.
Balance is stored as a Decimal to avoid floating-point errors.
"""
import logging
from decimal import Decimal

from django.conf import settings
from django.db import models

from apps.users.models import BaseModel

logger = logging.getLogger(__name__)


class Account(BaseModel):
    """
    A wallet/account belonging to one user.

    Fields
    ------
    user        — FK to the owning user
    name        — human-readable label (e.g. "Main USD Wallet")
    currency    — ISO 4217 code, 3 chars (e.g. "USD", "INR")
    balance     — current balance; never goes negative
    is_active   — soft-enable/disable without deleting
    """

    class Currency(models.TextChoices):
        USD = "USD", "US Dollar"
        INR = "INR", "Indian Rupee"
        EUR = "EUR", "Euro"
        GBP = "GBP", "British Pound"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="accounts",
    )
    name = models.CharField(max_length=255)
    currency = models.CharField(
        max_length=3,
        choices=Currency.choices,
        default=Currency.USD,
    )
    balance = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "accounts"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} ({self.currency}) — {self.user.email}"
