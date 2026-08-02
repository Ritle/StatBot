"""Application configuration loaded from environment variables."""

from __future__ import annotations

import re
from enum import StrEnum
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class BotMode(StrEnum):
    """Supported Telegram update delivery modes."""

    POLLING = "polling"
    WEBHOOK = "webhook"


def _parse_superadmin_ids(value: str) -> frozenset[int]:
    stripped = value.strip()
    if not stripped:
        return frozenset()

    parts = re.split(r"[\s,]+", stripped)
    try:
        identifiers = frozenset(int(part) for part in parts)
    except ValueError as error:
        raise ValueError(
            "SUPERADMIN_IDS must contain integers separated by commas or spaces",
        ) from error

    if any(identifier <= 0 for identifier in identifiers):
        raise ValueError("SUPERADMIN_IDS must contain positive Telegram user IDs")
    return identifiers


class Settings(BaseSettings):
    """Validated, immutable application settings."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
        frozen=True,
        populate_by_name=True,
    )

    bot_token: SecretStr = Field(validation_alias="BOT_TOKEN")
    database_url: SecretStr = Field(validation_alias="DATABASE_URL")
    superadmin_ids_value: str = Field(
        default="",
        validation_alias="SUPERADMIN_IDS",
        repr=False,
    )
    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    default_timezone: str = Field(
        default="Europe/Amsterdam",
        validation_alias="DEFAULT_TIMEZONE",
    )
    bot_mode: BotMode = Field(default=BotMode.POLLING, validation_alias="BOT_MODE")
    webhook_base_url: str = Field(default="", validation_alias="WEBHOOK_BASE_URL")
    webhook_path: str = Field(
        default="/telegram/webhook",
        validation_alias="WEBHOOK_PATH",
    )
    webhook_secret: SecretStr | None = Field(
        default=None,
        validation_alias="WEBHOOK_SECRET",
        repr=False,
    )

    @field_validator("bot_token", "database_url", mode="before")
    @classmethod
    def validate_required_secret(cls, value: object) -> object:
        raw_value = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError("value must not be empty")
        return value

    @field_validator("database_url")
    @classmethod
    def validate_database_driver(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must use the postgresql+asyncpg driver")
        return value

    @field_validator("superadmin_ids_value")
    @classmethod
    def validate_superadmin_ids(cls, value: str) -> str:
        _parse_superadmin_ids(value)
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        allowed_levels = {"CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"}
        if normalized not in allowed_levels:
            raise ValueError(f"LOG_LEVEL must be one of {sorted(allowed_levels)}")
        return normalized

    @field_validator("default_timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError(f"unknown timezone: {value}") from error
        return value

    @field_validator("webhook_path")
    @classmethod
    def validate_webhook_path(cls, value: str) -> str:
        if not value.startswith("/"):
            raise ValueError("WEBHOOK_PATH must start with '/'")
        return value

    @model_validator(mode="after")
    def validate_webhook_settings(self) -> Settings:
        if self.bot_mode is BotMode.WEBHOOK:
            if not self.webhook_base_url.startswith("https://"):
                raise ValueError("WEBHOOK_BASE_URL must be an HTTPS URL in webhook mode")
            if self.webhook_secret is None or not self.webhook_secret.get_secret_value():
                raise ValueError("WEBHOOK_SECRET is required in webhook mode")
        return self

    @property
    def superadmin_ids(self) -> frozenset[int]:
        """Return validated Telegram user IDs."""
        return _parse_superadmin_ids(self.superadmin_ids_value)

    @property
    def sqlalchemy_url(self) -> str:
        """Return the database DSN only to infrastructure code."""
        return self.database_url.get_secret_value()


def load_settings() -> Settings:
    """Load settings from the process environment and optional .env file."""
    return Settings()
