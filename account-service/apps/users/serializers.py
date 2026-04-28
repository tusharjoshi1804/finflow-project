"""Serializers for the users app."""
from django.contrib.auth.password_validation import validate_password
from rest_framework import serializers

from apps.users.models import User


class UserCreateSerializer(serializers.ModelSerializer):
    """Register a new user. Password is write-only and validated."""

    password = serializers.CharField(
        write_only=True,
        min_length=8,
        style={"input_type": "password"},
    )

    class Meta:
        model = User
        fields = ["id", "email", "first_name", "last_name", "phone", "password"]
        read_only_fields = ["id"]

    def validate_password(self, value: str) -> str:
        validate_password(value)
        return value

    def create(self, validated_data: dict) -> User:
        password = validated_data.pop("password")
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        return user


class UserDetailSerializer(serializers.ModelSerializer):
    """Read / update a user. Password is never returned."""

    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = User
        fields = [
            "id", "email", "first_name", "last_name",
            "phone", "full_name", "is_active",
            "created_at", "updated_at",
        ]
        read_only_fields = ["id", "email", "created_at", "updated_at"]


class UserUpdateSerializer(serializers.ModelSerializer):
    """Partial update — email and password excluded."""

    class Meta:
        model = User
        fields = ["first_name", "last_name", "phone"]
