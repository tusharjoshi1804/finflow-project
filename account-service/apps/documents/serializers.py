"""Serializers for the documents app."""
from rest_framework import serializers

from apps.core.minio_client import ALLOWED_CONTENT_TYPES, MAX_FILE_SIZE_BYTES
from apps.documents.models import Document


class DocumentSerializer(serializers.ModelSerializer):
    """Read serializer — returned after upload and on list/get."""

    owner_email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Document
        fields = [
            "id", "file_name", "content_type", "file_size",
            "owner_email", "created_at", "updated_at",
        ]
        read_only_fields = fields


class DocumentUploadSerializer(serializers.Serializer):
    """Write serializer — validates the incoming multipart file."""

    file = serializers.FileField()

    def validate_file(self, file):
        content_type = file.content_type
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"Unsupported file type '{content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            )
        if file.size > MAX_FILE_SIZE_BYTES:
            raise serializers.ValidationError(
                f"File too large ({file.size} bytes). Max allowed: {MAX_FILE_SIZE_BYTES} bytes."
            )
        return file
