"""Token persistence.

WHOOP rotates refresh tokens: a refresh makes the old refresh token invalid at once.
Thus the store must (1) write atomically and (2) let only one process refresh at a time.
`TokenStore.lock()` gives an exclusive cross-process file lock for that.
"""

import fcntl
import json
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path

from cryptography.fernet import Fernet

# Refresh this many seconds before the access token expires.
EXPIRY_SKEW_SECONDS = 300


@dataclass(frozen=True)
class TokenSet:
    access_token: str
    refresh_token: str
    expires_at: float
    scope: str
    obtained_at: float

    @classmethod
    def from_response(cls, payload: dict[str, object]) -> "TokenSet":
        now = time.time()
        return cls(
            access_token=str(payload["access_token"]),
            refresh_token=str(payload["refresh_token"]),
            expires_at=now + float(payload.get("expires_in", 3600)),  # type: ignore[arg-type]
            scope=str(payload.get("scope", "")),
            obtained_at=now,
        )

    def is_expiring(self, now: float | None = None) -> bool:
        return (now or time.time()) >= self.expires_at - EXPIRY_SKEW_SECONDS


class TokenStore:
    def __init__(self, path: Path, encryption_key: str | None = None) -> None:
        self.path = path
        self._lock_path = path.with_suffix(".lock")
        self._fernet = Fernet(encryption_key.encode()) if encryption_key else None

    def load(self) -> TokenSet | None:
        if not self.path.exists():
            return None
        raw = self.path.read_bytes()
        if self._fernet:
            raw = self._fernet.decrypt(raw)
        return TokenSet(**json.loads(raw))

    def save(self, tokens: TokenSet) -> None:
        raw = json.dumps(asdict(tokens)).encode()
        if self._fernet:
            raw = self._fernet.encrypt(raw)
        tmp = self.path.with_suffix(".tmp")
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, self.path)

    def clear(self) -> None:
        self.path.unlink(missing_ok=True)

    @contextmanager
    def lock(self) -> Iterator[None]:
        self._lock_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._lock_path, "w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
