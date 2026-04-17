from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    unifi_webhook_secret: str = Field(..., alias="UNIFI_WEBHOOK_SECRET")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    env: str = Field("dev", alias="ENV")


def get_settings() -> Settings:
    return Settings()
