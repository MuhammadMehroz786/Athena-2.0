from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(..., alias="DATABASE_URL")
    redis_url: str = Field(..., alias="REDIS_URL")
    unifi_webhook_secret: str = Field(..., alias="UNIFI_WEBHOOK_SECRET")
    domotz_webhook_secret: str = Field(..., alias="DOMOTZ_WEBHOOK_SECRET")
    domotz_api_base_url: str = Field(..., alias="DOMOTZ_API_BASE_URL")
    domotz_api_key: str = Field(..., alias="DOMOTZ_API_KEY")
    openai_api_key: str = Field("", alias="OPENAI_API_KEY")
    openai_model: str = Field("gpt-4o-mini", alias="OPENAI_MODEL")
    openai_base_url: str = Field("https://api.openai.com/v1", alias="OPENAI_BASE_URL")
    openai_timeout_seconds: float = Field(8.0, alias="OPENAI_TIMEOUT_SECONDS")
    openai_enabled: bool = Field(True, alias="OPENAI_ENABLED")
    twilio_enabled: bool = Field(False, alias="TWILIO_ENABLED")
    twilio_account_sid: str = Field("", alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: str = Field("", alias="TWILIO_AUTH_TOKEN")
    twilio_from_number: str = Field("", alias="TWILIO_FROM_NUMBER")
    twilio_base_url: str = Field(
        "https://api.twilio.com/2010-04-01", alias="TWILIO_BASE_URL"
    )
    twilio_timeout_seconds: float = Field(8.0, alias="TWILIO_TIMEOUT_SECONDS")
    notify_contact_phone: str = Field("", alias="NOTIFY_CONTACT_PHONE")
    log_level: str = Field("INFO", alias="LOG_LEVEL")
    env: str = Field("dev", alias="ENV")

    @model_validator(mode="after")
    def _check_openai_key_when_enabled(self):
        if self.openai_enabled and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is required when OPENAI_ENABLED is true"
            )
        return self

    @model_validator(mode="after")
    def _check_twilio_fields_when_enabled(self):
        if not self.twilio_enabled:
            return self
        missing = []
        if not self.twilio_account_sid:
            missing.append("TWILIO_ACCOUNT_SID")
        if not self.twilio_auth_token:
            missing.append("TWILIO_AUTH_TOKEN")
        if not self.twilio_from_number:
            missing.append("TWILIO_FROM_NUMBER")
        if not self.notify_contact_phone:
            missing.append("NOTIFY_CONTACT_PHONE")
        if missing:
            raise ValueError(
                f"{', '.join(missing)} required when TWILIO_ENABLED is true"
            )
        return self


def get_settings() -> Settings:
    return Settings()
