import pytest
from pydantic import ValidationError

from athena.config import Settings


def _base_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", "d0mz")
    monkeypatch.setenv("DOMOTZ_API_BASE_URL", "https://api-eu-west-1-cell-1.domotz.com/public-api/v1")
    monkeypatch.setenv("DOMOTZ_API_KEY", "api-key-xyz")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")


def test_settings_loads_from_env(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("ENV", "test")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.redis_url == "redis://h:6379/0"
    assert s.unifi_webhook_secret == "s3cret"
    assert s.domotz_webhook_secret == "d0mz"
    assert s.domotz_api_base_url == "https://api-eu-west-1-cell-1.domotz.com/public-api/v1"
    assert s.domotz_api_key == "api-key-xyz"
    assert s.openai_api_key == "test-openai-key"
    assert s.env == "test"


def test_settings_missing_required_raises(monkeypatch):
    for k in (
        "DATABASE_URL",
        "REDIS_URL",
        "UNIFI_WEBHOOK_SECRET",
        "DOMOTZ_WEBHOOK_SECRET",
        "DOMOTZ_API_BASE_URL",
        "DOMOTZ_API_KEY",
        "OPENAI_API_KEY",
    ):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_missing_domotz_api_fields_raises(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("DOMOTZ_WEBHOOK_SECRET", "d0mz")
    monkeypatch.setenv("OPENAI_API_KEY", "test-openai-key")
    monkeypatch.delenv("DOMOTZ_API_BASE_URL", raising=False)
    monkeypatch.delenv("DOMOTZ_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_settings_missing_openai_api_key_raises(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_openai_key_optional_when_disabled(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    s = Settings(_env_file=None)
    assert s.openai_api_key == ""
    assert s.openai_enabled is False


def test_openai_key_required_when_enabled(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_ENABLED", "true")
    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)
    assert "required when OPENAI_ENABLED" in str(exc_info.value)


def test_settings_openai_defaults(monkeypatch):
    _base_env(monkeypatch)
    for k in ("OPENAI_MODEL", "OPENAI_BASE_URL", "OPENAI_TIMEOUT_SECONDS", "OPENAI_ENABLED"):
        monkeypatch.delenv(k, raising=False)
    s = Settings(_env_file=None)
    assert s.openai_model == "gpt-4o-mini"
    assert s.openai_base_url == "https://api.openai.com/v1"
    assert s.openai_timeout_seconds == 8.0
    assert s.openai_enabled is True


def test_settings_openai_overrides(monkeypatch):
    _base_env(monkeypatch)
    monkeypatch.setenv("OPENAI_MODEL", "gpt-4o")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://proxy.local/v1")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "3.5")
    monkeypatch.setenv("OPENAI_ENABLED", "false")
    s = Settings(_env_file=None)
    assert s.openai_model == "gpt-4o"
    assert s.openai_base_url == "https://proxy.local/v1"
    assert s.openai_timeout_seconds == 3.5
    assert s.openai_enabled is False
