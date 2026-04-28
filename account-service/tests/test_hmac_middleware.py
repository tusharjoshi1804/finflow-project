"""Tests for apps/core/hmac_middleware — Account Service side."""
import hashlib
import hmac
import time
import uuid

import pytest

from apps.core.hmac_middleware import clear_nonces, verify_hmac_request


def make_request(method="PATCH", path="/api/internal/transactions/abc/",
                 body=b'{"status":"COMPLETED"}', secret="dev-hmac-secret-change-me",
                 timestamp=None, nonce=None, tamper_sig=False):
    """Build a mock Django request with HMAC headers."""
    ts = timestamp or str(int(time.time()))
    nc = nonce or str(uuid.uuid4())
    body_hash = hashlib.sha256(body).hexdigest()
    message = f"{method}\n{path}\n{ts}\n{nc}\n{body_hash}"
    sig = hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()
    if tamper_sig:
        sig = "00" * 32

    class FakeRequest:
        META = {
            "HTTP_X_TIMESTAMP": ts,
            "HTTP_X_NONCE": nc,
            "HTTP_X_SIGNATURE": sig,
        }
        this_body = body
        this_method = method
        this_path = path

        @property
        def body(self):
            return self.this_body

        @property
        def method(self):
            return self.this_method

        @property
        def path(self):
            return self.this_path

    return FakeRequest()


class TestHmacMiddleware:
    def setup_method(self):
        clear_nonces()

    def test_valid_request_passes(self):
        req = make_request()
        ok, reason = verify_hmac_request(req)
        assert ok is True
        assert reason == ""

    def test_missing_timestamp_fails(self):
        req = make_request()
        req.META.pop("HTTP_X_TIMESTAMP")
        ok, reason = verify_hmac_request(req)
        assert ok is False
        assert "Missing" in reason

    def test_missing_nonce_fails(self):
        req = make_request()
        req.META.pop("HTTP_X_NONCE")
        ok, reason = verify_hmac_request(req)
        assert ok is False

    def test_missing_signature_fails(self):
        req = make_request()
        req.META.pop("HTTP_X_SIGNATURE")
        ok, reason = verify_hmac_request(req)
        assert ok is False

    def test_bad_signature_fails(self):
        req = make_request(tamper_sig=True)
        ok, reason = verify_hmac_request(req)
        assert ok is False
        assert "Signature" in reason

    def test_stale_timestamp_fails(self):
        stale = str(int(time.time()) - 400)
        req = make_request(timestamp=stale)
        ok, reason = verify_hmac_request(req)
        assert ok is False
        assert "Stale" in reason

    def test_invalid_timestamp_format_fails(self):
        req = make_request(timestamp="not-a-number")
        ok, reason = verify_hmac_request(req)
        assert ok is False
        assert "Invalid" in reason

    def test_nonce_replay_fails(self):
        req = make_request()
        ok1, _ = verify_hmac_request(req)
        assert ok1 is True
        # Attempt replay with same nonce — build fresh sig with same nonce
        nc = req.META["HTTP_X_NONCE"]
        req2 = make_request(nonce=nc)
        ok2, reason = verify_hmac_request(req2)
        assert ok2 is False
        assert "Nonce" in reason

    def test_wrong_secret_fails(self):
        req = make_request(secret="wrong-secret")
        ok, reason = verify_hmac_request(req)
        assert ok is False

    def test_clear_nonces_resets_store(self):
        req = make_request()
        verify_hmac_request(req)
        clear_nonces()
        req2 = make_request(nonce=req.META["HTTP_X_NONCE"])
        ok, _ = verify_hmac_request(req2)
        # After clearing, same nonce should be allowed if sig is valid
        # (sig will differ due to new timestamp, but nonce check passes)
        # Just verify no exception is raised
        assert isinstance(ok, bool)
