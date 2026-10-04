"""WHOOP OAuth 2.0 authorization-code flow with refresh-token rotation."""

import secrets
import time
from urllib.parse import urlencode

import httpx

from whoopmon.auth.token_store import TokenSet, TokenStore
from whoopmon.config import WHOOP_SCOPES, Settings
from whoopmon.observability import get_logger
from whoopmon.observability.metrics import token_refreshes

log = get_logger(__name__)


class AuthError(RuntimeError):
    """Raised when there is no usable token. The fix is `whoopmon auth login`."""


def new_state() -> str:
    # WHOOP needs at least 8 characters.
    return secrets.token_urlsafe(24)


def authorize_url(settings: Settings, state: str) -> str:
    query = urlencode(
        {
            "response_type": "code",
            "client_id": settings.whoop_client_id,
            "redirect_uri": settings.whoop_redirect_uri,
            "scope": " ".join(WHOOP_SCOPES),
            "state": state,
        }
    )
    return f"{settings.whoop_oauth_base}/auth?{query}"


def _token_request(settings: Settings, data: dict[str, str]) -> TokenSet:
    body = {
        **data,
        "client_id": settings.whoop_client_id,
        "client_secret": settings.whoop_client_secret.get_secret_value(),
    }
    resp = httpx.post(
        f"{settings.whoop_oauth_base}/token", data=body, timeout=settings.http_timeout_seconds
    )
    if resp.status_code != 200:
        # The body can echo request values; log only the error code.
        error = resp.json().get("error", "unknown") if resp.content else "empty"
        raise AuthError(f"token endpoint returned {resp.status_code}: {error}")
    return TokenSet.from_response(resp.json())


def exchange_code(settings: Settings, code: str) -> TokenSet:
    tokens = _token_request(
        settings,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": settings.whoop_redirect_uri,
        },
    )
    log.info("auth.code.exchanged", scope=tokens.scope)
    return tokens


class TokenManager:
    """Gives a valid access token. Refreshes under a file lock when needed."""

    def __init__(self, settings: Settings, store: TokenStore) -> None:
        self.settings = settings
        self.store = store

    def access_token(self, force_refresh: bool = False) -> str:
        tokens = self.store.load()
        if tokens is None:
            raise AuthError("no tokens stored; run `whoopmon auth login`")
        if not force_refresh and not tokens.is_expiring():
            return tokens.access_token

        with self.store.lock():
            # Another process may have refreshed while we waited for the lock.
            current = self.store.load()
            if current is None:
                raise AuthError("tokens removed during refresh; run `whoopmon auth login`")
            if current.obtained_at > tokens.obtained_at and not current.is_expiring():
                return current.access_token
            return self._refresh(current).access_token

    def _refresh(self, tokens: TokenSet) -> TokenSet:
        started = time.monotonic()
        try:
            new = _token_request(
                self.settings,
                {
                    "grant_type": "refresh_token",
                    "refresh_token": tokens.refresh_token,
                    "scope": "offline",
                },
            )
        except (AuthError, httpx.HTTPError) as exc:
            token_refreshes.add(1, {"outcome": "failure"})
            log.error("auth.token.refresh_failed", error=str(exc))
            raise
        # Save before use: the old refresh token is already dead.
        self.store.save(new)
        token_refreshes.add(1, {"outcome": "success"})
        log.info(
            "auth.token.refreshed",
            expires_in_s=round(new.expires_at - time.time()),
            duration_ms=round((time.monotonic() - started) * 1000),
        )
        return new
