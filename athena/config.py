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
    openai_api_key: str = Field(..., alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_timeout_seconds: float = Field(8.0, alias="OPENAI_TIMEOUT_SECONDS")
    openai_enabled: bool = Field(True, alias="OPENAI_ENABLED")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    env: str = Field("dev", alias="ENV")


def get_settings() -> Settings:
    return Settings()
