from whoopmon.webhook.signature import compute_signature, verify

SECRET = "test-secret"
BODY = b'{"user_id":456,"id":"550e8400-e29b-41d4-a716-446655440000","type":"sleep.updated","trace_id":"t1"}'


def test_valid_signature_passes():
    ts = "1759600000000"
    sig = compute_signature(SECRET, ts, BODY)
    assert verify(SECRET, ts, sig, BODY, now_ms=1759600000500)


def test_tampered_body_fails():
    ts = "1759600000000"
    sig = compute_signature(SECRET, ts, BODY)
    assert not verify(SECRET, ts, sig, BODY + b" ", now_ms=1759600000500)


def test_old_timestamp_fails():
    ts = "1759600000000"
    sig = compute_signature(SECRET, ts, BODY)
    assert not verify(SECRET, ts, sig, BODY, now_ms=1759600000000 + 11 * 60 * 1000)


def test_missing_headers_fail():
    assert not verify(SECRET, None, "x", BODY)
    assert not verify(SECRET, "123", None, BODY)
    assert not verify(SECRET, "abc", "x", BODY)
