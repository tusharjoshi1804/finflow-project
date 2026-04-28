"""
MinIO client utility for FinFlow.

All MinIO operations are wrapped so that connection failures
never propagate uncaught into views.
"""
import logging

from django.conf import settings

try:
    from minio import Minio  # type: ignore
except Exception:
    Minio = None

logger = logging.getLogger(__name__)

ALLOWED_CONTENT_TYPES = {
    "image/jpeg",
    "image/png",
    "image/gif",
    "application/pdf",
}
MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB


def get_minio_client():
    """Return a connected Minio client or None if unavailable."""
    try:
        client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=False,
        )
        return client
    except Exception as exc:
        logger.warning("MinIO client init failed: %s", exc)
        return None


def ensure_bucket_exists(client) -> bool:
    """Create the configured bucket if it does not exist."""
    try:
        bucket = settings.MINIO_BUCKET
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
            logger.info("MinIO bucket created: %s", bucket)
        return True
    except Exception as exc:
        logger.error("MinIO bucket check/create failed: %s", exc)
        return False


def upload_file(object_name: str, file_obj, content_type: str, size: int) -> bool:
    """
    Upload a file-like object to MinIO.
    Returns True on success, False on any failure.
    """
    client = get_minio_client()
    if client is None:
        return False
    try:
        ensure_bucket_exists(client)
        client.put_object(
            settings.MINIO_BUCKET,
            object_name,
            file_obj,
            size,
            content_type=content_type,
        )
        logger.info("MinIO upload success: %s", object_name)
        return True
    except Exception as exc:
        logger.error("MinIO upload failed for %s: %s", object_name, exc)
        return False


def download_file(object_name: str):
    """
    Download a file from MinIO.
    Returns (data, content_type) tuple or (None, None) on failure.
    """
    client = get_minio_client()
    if client is None:
        return None, None
    try:
        response = client.get_object(settings.MINIO_BUCKET, object_name)
        data = response.read()
        content_type = response.headers.get("Content-Type", "application/octet-stream")
        response.close()
        response.release_conn()
        return data, content_type
    except Exception as exc:
        logger.error("MinIO download failed for %s: %s", object_name, exc)
        return None, None


def delete_file(object_name: str) -> bool:
    """Delete a file from MinIO. Returns True on success."""
    client = get_minio_client()
    if client is None:
        return False
    try:
        client.remove_object(settings.MINIO_BUCKET, object_name)
        logger.info("MinIO delete success: %s", object_name)
        return True
    except Exception as exc:
        logger.error("MinIO delete failed for %s: %s", object_name, exc)
        return False
