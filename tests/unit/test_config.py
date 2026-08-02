"""Configuration tests."""

import pytest
from pydantic import ValidationError

from app.config import Settings


def build_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "bot_token": "123456:testing-token",
        "database_url": "postgresql+asyncpg://user:pass@localhost/db",
        "superadmin_ids_value": "",
    }
    values.update(overrides)
    return Settings.model_validate(values)


def test_superadmin_ids_are_safely_parsed_and_deduplicated() -> None:
    settings = build_settings(superadmin_ids_value="42, 100\n42")

    assert settings.superadmin_ids == frozenset({42, 100})


def test_invalid_superadmin_id_is_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(superadmin_ids_value="42,not-an-id")


def test_empty_required_settings_are_rejected() -> None:
    with pytest.raises(ValidationError):
        build_settings(bot_token="")


def test_database_url_requires_asyncpg_driver() -> None:
    with pytest.raises(ValidationError):
        build_settings(database_url="postgresql://user:pass@localhost/db")
