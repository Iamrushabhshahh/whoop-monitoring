import os
import stat
import time

from cryptography.fernet import Fernet

from whoopmon.auth.token_store import EXPIRY_SKEW_SECONDS, TokenSet, TokenStore


def _tokens(expires_in: float = 3600) -> TokenSet:
    now = time.time()
    return TokenSet("a", "r", now + expires_in, "offline", now)


def test_roundtrip_and_permissions(tmp_path):
    store = TokenStore(tmp_path / "tokens.json")
    store.save(_tokens())
    assert store.load().refresh_token == "r"
    mode = stat.S_IMODE(os.stat(tmp_path / "tokens.json").st_mode)
    assert mode == 0o600


def test_encrypted_at_rest(tmp_path):
    key = Fernet.generate_key().decode()
    store = TokenStore(tmp_path / "tokens.json", key)
    store.save(_tokens())
    assert b"offline" not in (tmp_path / "tokens.json").read_bytes()
    assert store.load().access_token == "a"


def test_is_expiring_uses_skew():
    assert _tokens(EXPIRY_SKEW_SECONDS - 1).is_expiring()
    assert not _tokens(EXPIRY_SKEW_SECONDS + 60).is_expiring()
