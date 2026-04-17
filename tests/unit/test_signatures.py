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
    assert verify_hmac_sha256(b"x", "abc", "k") is False


def test_verify_hmac_sha256_rejects_wrong_full_length_digest():
    secret = "s3cret"
    body = b'{"a":1}'
    valid = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    # Flip one hex character — still 64 chars, still valid hex, but wrong digest.
    # This is the path where compare_digest's constant-time property matters.
    tampered = ("1" if valid[0] != "1" else "2") + valid[1:]
    assert len(tampered) == 64
    assert verify_hmac_sha256(body, tampered, secret) is False
