"""
HMAC-SHA256 signing and verification for FinFlow internal service auth.

Signature covers: METHOD + PATH + TIMESTAMP + NONCE + SHA256(body)
This ensures the request cannot be replayed or tampered with.
"""
import hashlib
import hmac
import time
import uuid
from typing import Tuple

from app.config import HMAC_SECRET

# Maximum age of a request before it is considered stale (seconds)
TIMESTAMP_TOLERANCE_SECONDS = 300  # 5 minutes

# In-memory nonce store — production would use Redis with TTL
_used_nonces: set[str] = set()


def _body_hash(body: bytes) -> str:
    """Return hex-encoded SHA-256 hash of the request body."""
    return hashlib.sha256(body).hexdigest()


def sign_request(method: str, path: str, body: bytes = b"") -> dict[str, str]:
    """
    Generate HMAC headers for an outgoing internal request.

    Returns a dict with X-Timestamp, X-Nonce, X-Signature headers.
    """
    timestamp = str(int(time.time()))
    nonce = str(uuid.uuid4())
    body_hash = _body_hash(body)

    message = f"{method.upper()}\n{path}\n{timestamp}\n{nonce}\n{body_hash}"
    signature = hmac.new(
        HMAC_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return {
        "X-Timestamp": timestamp,
        "X-Nonce": nonce,
        "X-Signature": signature,
    }


def verify_request(
    method: str,
    path: str,
    body: bytes,
    timestamp_str: str,
    nonce: str,
    signature: str,
) -> Tuple[bool, str]:
    """
    Verify an incoming HMAC-signed request.

    Returns (True, "") on success or (False, reason) on failure.
    """
    # 1. Timestamp check
    try:
        timestamp = int(timestamp_str)
    except (ValueError, TypeError):
        return False, "Invalid timestamp format"

    now = int(time.time())
    if abs(now - timestamp) > TIMESTAMP_TOLERANCE_SECONDS:
        return False, "Request timestamp is stale"

    # 2. Nonce replay check
    if nonce in _used_nonces:
        return False, "Nonce already used (replay attack)"

    # 3. Signature check
    body_hash = _body_hash(body)
    message = f"{method.upper()}\n{path}\n{timestamp_str}\n{nonce}\n{body_hash}"
    expected = hmac.new(
        HMAC_SECRET.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(expected, signature):
        return False, "Signature mismatch"

    # 4. Record nonce as used
    _used_nonces.add(nonce)
    return True, ""


def clear_nonces() -> None:
    """Clear the nonce store — used in tests only."""
    _used_nonces.clear()
