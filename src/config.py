"""
Configuration module for Voicebip SMS Support System
Loads and validates environment variables using Pydantic Settings
"""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    # Voicebip Configuration
    voicebip_api_key: str = Field(..., alias="VOICEBIP_API_KEY")
    voicebip_api_url: str = Field(default="https://api.voicebip.com/v1", alias="VOICEBIP_API_URL")
    voicebip_webhook_secret: str = Field(..., alias="VOICEBIP_WEBHOOK_SECRET")
    voicebip_agent_id: str = Field(..., alias="VOICEBIP_AGENT_ID")
    voicebip_provisioned_number: str = Field(default="+2342013501089", alias="VOICEBIP_PROVISIONED_NUMBER")

    # Server Configuration
    host: str = Field(default="0.0.0.0", alias="HOST")
    port: int = Field(default=8000, alias="PORT")
    environment: str = Field(default="development", alias="ENVIRONMENT")
    webhook_url: Optional[str] = Field(default=None, alias="WEBHOOK_URL")

    # Logging
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",
    }

    @property
    def is_production(self) -> bool:
        return self.environment.lower() == "production"

    @property
    def is_development(self) -> bool:
        return self.environment.lower() == "development"


# Global settings instance
settings = Settings()


def validate_settings() -> None:
    """Validate required settings are present."""
    errors = []

    if not settings.voicebip_api_key or settings.voicebip_api_key == "pk_live_your_api_key_here":
        errors.append("VOICEBIP_API_KEY is required and must be set to your actual API key")

    if not settings.voicebip_webhook_secret or settings.voicebip_webhook_secret == "your_webhook_secret_here":
        errors.append("VOICEBIP_WEBHOOK_SECRET is required for webhook signature verification")

    if not settings.voicebip_agent_id or settings.voicebip_agent_id == "your_customer_support_agent_id":
        errors.append("VOICEBIP_AGENT_ID is required - get this from your Voicebip Customer Support Agent")

    if settings.is_production and not settings.webhook_url:
        errors.append("WEBHOOK_URL is required in production environment")

    if errors:
        raise ValueError(f"Configuration validation failed:\n" + "\n".join(errors))


# Validate on import
validate_settings()