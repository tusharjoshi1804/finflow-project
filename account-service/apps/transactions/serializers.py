"""Serializers for the transactions app."""
from decimal import Decimal

from rest_framework import serializers

from apps.transactions.models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    """Full read serializer."""

    account_id = serializers.UUIDField(source="account.id", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id", "account_id", "transaction_type",
            "amount", "status", "reference",
            "created_at", "updated_at",
        ]
        read_only_fields = [
            "id", "account_id", "status", "created_at", "updated_at"
        ]


class TransactionCreateSerializer(serializers.ModelSerializer):
    """Create a transaction against a caller-owned account."""

    class Meta:
        model = Transaction
        fields = ["id", "account", "transaction_type", "amount", "reference"]
        read_only_fields = ["id"]

    def validate_amount(self, value: Decimal) -> Decimal:
        if value <= Decimal("0"):
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def validate_account(self, account):
        request = self.context["request"]
        if account.user != request.user:
            raise serializers.ValidationError(
                "You do not own this account."
            )
        if account.is_deleted:
            raise serializers.ValidationError("Account has been deleted.")
        return account


class TransactionStatusUpdateSerializer(serializers.ModelSerializer):
    """Internal-only serializer for updating transaction status."""

    class Meta:
        model = Transaction
        fields = ["status"]

    def validate_status(self, value: str) -> str:
        allowed = [Transaction.Status.COMPLETED, Transaction.Status.FAILED]
        if value not in allowed:
            raise serializers.ValidationError(
                f"Status must be one of: {', '.join(allowed)}"
            )
        return value
