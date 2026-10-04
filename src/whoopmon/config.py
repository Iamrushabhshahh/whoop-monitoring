"""Runtime configuration. Every value comes from the environment or `.env`."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

WHOOP_SCOPES = (
    "offline",
    "read:recovery",
    "read:cycles",
    "read:sleep",
    "read:workout",
    "read:profile",
    "read:body_measurement",
)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # WHOOP OAuth app (developer-dashboard.whoop.com)
    whoop_client_id: str
    whoop_client_secret: SecretStr
    whoop_redirect_uri: str = "http://localhost:8765/callback"
    whoop_api_base: str = "https://api.prod.whoop.com/developer"
    whoop_oauth_base: str = "https://api.prod.whoop.com/oauth/oauth2"

    # OpenObserve
    o2_url: str = "http://localhost:5080"
    o2_org: str = "default"
    o2_user: str
    o2_password: SecretStr
    o2_stream_prefix: str = "whoop_"

    # Local state
    data_dir: Path = Path("data")
    token_encryption_key: SecretStr | None = Field(
        default=None, description="Fernet key. If set, tokens.json is encrypted at rest."
    )

    # Sync behaviour
    sync_interval_seconds: int = 900
    sync_lookback_hours: int = 72
    http_timeout_seconds: float = 20.0
    max_retries: int = 5

    # Where OpenObserve posts alert notifications. Empty: provision dashboards only.
    alert_webhook_url: str = ""

    # Webhook receiver
    webhook_host: str = "0.0.0.0"  # noqa: S104 - receiver is meant to listen in a container
    webhook_port: int = 8080

    # Telemetry
    log_level: str = "INFO"
    log_format: str = "json"  # json | console
    otel_enabled: bool = True
    otel_service_name: str = "whoopmon"
    environment: str = "local"

    @property
    def state_db(self) -> Path:
        return self.data_dir / "state.db"

    @property
    def token_file(self) -> Path:
        return self.data_dir / "tokens.json"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()  # type: ignore[call-arg]
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    return settings
