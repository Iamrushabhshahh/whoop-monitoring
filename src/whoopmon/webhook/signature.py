"""WHOOP webhook signature check.

signature = base64(HMAC-SHA256(key=client_secret, msg=timestamp_header + raw_body))
"""

import base64
import hashlib
import hmac
import time

# Reject events older than this, to limit replay of a captured request.
MAX_SKEW_MS = 10 * 60 * 1000


def compute_signature(secret: str, timestamp: str, body: bytes) -> str:
    mac = hmac.new(secret.encode(), timestamp.encode() + body, hashlib.sha256)
    return base64.b64encode(mac.digest()).decode()


def verify(
    secret: str,
    timestamp: str | None,
    signature: str | None,
    body: bytes,
    now_ms: int | None = None,
) -> bool:
    if not timestamp or not signature or not timestamp.isdigit():
        return False
    now_ms = now_ms if now_ms is not None else int(time.time() * 1000)
    if abs(now_ms - int(timestamp)) > MAX_SKEW_MS:
        return False
    return hmac.compare_digest(compute_signature(secret, timestamp, body), signature)
