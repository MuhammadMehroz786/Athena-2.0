import pytest
from pydantic import ValidationError

from athena.config import Settings


def test_settings_loads_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@h/db")
    monkeypatch.setenv("REDIS_URL", "redis://h:6379/0")
    monkeypatch.setenv("UNIFI_WEBHOOK_SECRET", "s3cret")
    monkeypatch.setenv("ENV", "test")
    s = Settings(_env_file=None)
    assert s.database_url == "postgresql+asyncpg://u:p@h/db"
    assert s.redis_url == "redis://h:6379/0"
    assert s.unifi_webhook_secret == "s3cret"
    assert s.env == "test"


def test_settings_missing_required_raises(monkeypatch):
    for k in ("DATABASE_URL", "REDIS_URL", "UNIFI_WEBHOOK_SECRET"):
        monkeypatch.delenv(k, raising=False)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
