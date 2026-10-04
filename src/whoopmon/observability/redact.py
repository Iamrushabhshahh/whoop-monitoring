"""Remove secrets and personal data from log events before they leave the process."""

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"

SENSITIVE_KEYS = frozenset(
    {
        "access_token",
        "refresh_token",
        "id_token",
        "client_secret",
        "code",
        "authorization",
        "password",
        "secret",
        "email",
        "first_name",
        "last_name",
        "x-whoop-signature",
    }
)

_BEARER = re.compile(r"(?i)bearer\s+[a-z0-9._~+/=-]+")
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")


def _scrub_str(value: str) -> str:
    return _EMAIL.sub(REDACTED, _BEARER.sub(f"Bearer {REDACTED}", value))


def scrub(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            k: REDACTED if str(k).lower() in SENSITIVE_KEYS else scrub(v) for k, v in value.items()
        }
    if isinstance(value, list | tuple):
        return type(value)(scrub(v) for v in value)
    if isinstance(value, str):
        return _scrub_str(value)
    return value


def redact_processor(_logger: Any, _method: str, event_dict: dict[str, Any]) -> dict[str, Any]:
    """structlog processor. Runs last before rendering."""
    return scrub(event_dict)  # type: ignore[no-any-return]
