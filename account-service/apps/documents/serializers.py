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
        # Validate content type
        content_type = file.content_type
        if content_type not in ALLOWED_CONTENT_TYPES:
            raise serializers.ValidationError(
                f"Unsupported file type '{content_type}'. "
                f"Allowed: {', '.join(sorted(ALLOWED_CONTENT_TYPES))}"
            )
        
        # Validate file size
        if file.size is None or file.size == 0:
            raise serializers.ValidationError("File is empty.")
        if file.size > MAX_FILE_SIZE_BYTES:
            max_mb = MAX_FILE_SIZE_BYTES / (1024 * 1024)
            raise serializers.ValidationError(
                f"File too large ({file.size:,} bytes). "
                f"Max allowed: {MAX_FILE_SIZE_BYTES:,} bytes ({max_mb:.1f} MB)."
            )
        return file
