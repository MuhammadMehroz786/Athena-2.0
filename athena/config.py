from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    unifi_webhook_secret: str = Field(..., alias="UNIFI_WEBHOOK_SECRET")
    domotz_webhook_secret: str = Field(..., alias="DOMOTZ_WEBHOOK_SECRET")
    domotz_api_base_url: str = Field(..., alias="DOMOTZ_API_BASE_URL")
    domotz_api_key: str = Field(..., alias="DOMOTZ_API_KEY")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    env: str = Field("dev", alias="ENV")


def get_settings() -> Settings:
    return Settings()
