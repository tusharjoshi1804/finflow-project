"""
HMAC verification for Account Service internal endpoints.

Rejects requests with:
  - Missing headers
  - Bad signature
  - Stale timestamp (> 5 minutes)
  - Reused nonce (replay attack)
"""
import hashlib
import hmac
import time

from django.conf import settings
from django.http import JsonResponse

TIMESTAMP_TOLERANCE = 300  # 5 minutes in seconds
_used_nonces: set[str] = set()


def _body_hash(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def verify_hmac_request(request) -> tuple[bool, str]:
    """Return (True, '') or (False, reason)."""
    timestamp_str = request.META.get("HTTP_X_TIMESTAMP", "")
    nonce = request.META.get("HTTP_X_NONCE", "")
    signature = request.META.get("HTTP_X_SIGNATURE", "")

    if not all([timestamp_str, nonce, signature]):
        return False, "Missing HMAC headers"

    try:
        timestamp = int(timestamp_str)
    except ValueError:
        return False, "Invalid timestamp"

    if abs(int(time.time()) - timestamp) > TIMESTAMP_TOLERANCE:
        return False, "Stale timestamp"

    if nonce in _used_nonces:
        return False, "Nonce already used"

    body = request.body
    body_hash = _body_hash(body)
    method = request.method.upper()
    path = request.path

    message = f"{method}\n{path}\n{timestamp_str}\n{nonce}\n{body_hash}"
    expected = hmac.new(
        settings.HMAC_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return False, "Signature mismatch"

    _used_nonces.add(nonce)
    return True, ""


def clear_nonces():
    """Clear nonce store — for tests only."""
    _used_nonces.clear()
