import hmac
import hashlib
from athena.webhooks.signatures import verify_hmac_sha256


def test_verify_hmac_sha256_accepts_valid():
    secret = "s3cret"
    body = b'{"a":1}'
    sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    assert verify_hmac_sha256(body, sig, secret) is True


def test_verify_hmac_sha256_rejects_tampered():
    secret = "s3cret"
    assert verify_hmac_sha256(b'{"a":1}', "deadbeef", secret) is False


def test_verify_hmac_sha256_rejects_empty_signature():
    assert verify_hmac_sha256(b"x", "", "k") is False


def test_verify_hmac_sha256_rejects_length_mismatch():
    # length-mismatched inputs must return False without raising
    assert verify_hmac_sha256(b"x", "abc", "k") is False
