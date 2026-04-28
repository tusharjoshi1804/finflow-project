"""
Transaction model for FinFlow.

A transaction records a debit/credit against an account.
Status lifecycle: PENDING → COMPLETED | FAILED
"""
import logging
from decimal import Decimal

from django.db import models

from apps.accounts.models import Account
from apps.users.models import BaseModel

logger = logging.getLogger(__name__)


class Transaction(BaseModel):
    """
    Financial transaction on an account.

    Fields
    ------
    account         — FK to the account being debited/credited
    transaction_type— DEBIT or CREDIT
    amount          — positive decimal value
    status          — PENDING / COMPLETED / FAILED
    reference       — optional external reference / note
    """

    class TransactionType(models.TextChoices):
        DEBIT = "DEBIT", "Debit"
        CREDIT = "CREDIT", "Credit"

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        COMPLETED = "COMPLETED", "Completed"
        FAILED = "FAILED", "Failed"

    account = models.ForeignKey(
        Account,
        on_delete=models.CASCADE,
        related_name="transactions",
    )
    transaction_type = models.CharField(
        max_length=10,
        choices=TransactionType.choices,
    )
    amount = models.DecimalField(
        max_digits=18,
        decimal_places=2,
    )
    status = models.CharField(
        max_length=10,
        choices=Status.choices,
        default=Status.PENDING,
    )
    reference = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "transactions"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.transaction_type} {self.amount} [{self.status}]"
