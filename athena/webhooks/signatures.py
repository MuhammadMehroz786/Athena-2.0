import hmac
import hashlib


def verify_hmac_sha256(body: bytes, signature_hex: str, secret: str) -> bool:
    if not signature_hex:
        return False
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature_hex)
