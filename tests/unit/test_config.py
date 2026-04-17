import pytest
from pydantic import ValidationError

from athena.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", "d0mz")
    monkeypatch.setenv("DOMOTZ_API_BASE_URL", "https://api-eu-west-1-cell-1.domotz.com/public-api/v1")
    monkeypatch.setenv("DOMOTZ_API_KEY", "api-key-xyz")
    monkeypatch.setenv("ENV", "test")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.redis_url == "redis://h:6379/0"
    assert s.unifi_webhook_secret == "s3cret"
    assert s.domotz_webhook_secret == "d0mz"
    assert s.domotz_api_base_url == "https://api-eu-west-1-cell-1.domotz.com/public-api/v1"
    assert s.domotz_api_key == "api-key-xyz"
    assert s.env == "test"


def test_settings_missing_required_raises(monkeypatch):
    for k in (
        "DATABASE_URL",
        "REDIS_URL",
        "UNIFI_WEBHOOK_SECRET",
        "DOMOTZ_WEBHOOK_SECRET",
        "DOMOTZ_API_BASE_URL",
        "DOMOTZ_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_missing_domotz_api_fields_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", "d0mz")
    monkeypatch.delenv("DOMOTZ_API_BASE_URL", raising=False)
    monkeypatch.delenv("DOMOTZ_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
