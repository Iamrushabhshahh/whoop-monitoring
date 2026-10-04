import pytest

from whoopmon.config import Settings


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        _env_file=None,
        whoop_client_id="test-client",
        whoop_client_secret="test-secret",
        o2_user="o2@example.com",
        o2_password="pw",
        data_dir=tmp_path,
        otel_enabled=False,
        max_retries=2,
    )
