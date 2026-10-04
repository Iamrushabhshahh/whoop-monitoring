from whoopmon.observability.redact import REDACTED, redact_processor, scrub


def test_sensitive_keys_are_redacted_at_any_depth():
    event = {
        "event": "x",
        "access_token": "abc",
        "nested": {"refresh_token": "def", "client_secret": "s", "ok": 1},
        "items": [{"email": "a@b.co"}],
    }
    out = redact_processor(None, "info", event)
    assert out["access_token"] == REDACTED
    assert out["nested"] == {"refresh_token": REDACTED, "client_secret": REDACTED, "ok": 1}
    assert out["items"] == [{"email": REDACTED}]
    assert out["event"] == "x"


def test_bearer_and_email_in_free_text():
    text = scrub("call failed: Authorization: Bearer eyJhbGciOi.x.y for rushabh@example.com")
    assert "eyJhbGciOi" not in text
    assert "rushabh@example.com" not in text
