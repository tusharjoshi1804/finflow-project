"""
Document model for FinFlow KYC uploads.

Only metadata is stored in the DB.
The actual file bytes live in MinIO under object_name.
"""
import uuid

from django.conf import settings
from django.db import models

from apps.users.models import BaseModel


class Document(BaseModel):
    """
    KYC document metadata record.

    Fields
    ------
    user         — owner of this document
    file_name    — original filename as uploaded by the user
    object_name  — key used to store/retrieve the file in MinIO
    content_type — MIME type (e.g. image/jpeg, application/pdf)
    file_size    — size in bytes
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="documents",
    )
    file_name = models.CharField(max_length=255)
    object_name = models.CharField(max_length=512, unique=True)
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveIntegerField(help_text="File size in bytes")

    class Meta:
        db_table = "documents"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.file_name} ({self.user.email})"
