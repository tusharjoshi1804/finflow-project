"""Serializers for the accounts app."""
from decimal import Decimal

from rest_framework import serializers

from apps.accounts.models import Account


class AccountSerializer(serializers.ModelSerializer):
    """Full read serializer — includes owner email for convenience."""

    owner_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Account
        fields = [
            "id", "name", "currency", "balance",
            "is_active", "owner_email",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "balance", "owner_email", "created_at", "updated_at"]


class AccountCreateSerializer(serializers.ModelSerializer):
    """Create a new account — balance starts at 0."""

    class Meta:
        model = Account
        fields = ["id", "name", "currency"]
        read_only_fields = ["id"]

    def validate_currency(self, value: str) -> str:
        allowed = [c.value for c in Account.Currency]
        if value not in allowed:
            raise serializers.ValidationError(
                f"Currency must be one of: {', '.join(allowed)}"
            )
        return value


class AccountUpdateSerializer(serializers.ModelSerializer):
    """Partial update — only name and is_active can change."""

    class Meta:
        model = Account
        fields = ["name", "is_active"]
