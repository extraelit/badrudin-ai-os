"""Тесты проверки обязательных секретов (app.core.preflight)."""

from __future__ import annotations

import pytest

from app.core.config import Settings
from app.core.preflight import (
    MIN_SECRET_LENGTH,
    SecretValidationError,
    check_required_secrets,
)


def _settings(**overrides) -> Settings:
    base = {"jwt_secret": "x" * MIN_SECRET_LENGTH, "app_env": "development"}
    base.update(overrides)
    return Settings(**base)


def test_strong_secret_has_no_problems() -> None:
    assert check_required_secrets(_settings()) == []


def test_placeholder_secret_warns_in_development() -> None:
    # В development заглушка не блокирует запуск, но фиксируется как проблема.
    problems = check_required_secrets(_settings(jwt_secret="change-me"))
    assert problems and "JWT_SECRET" in problems[0]


def test_short_secret_warns_in_development() -> None:
    problems = check_required_secrets(_settings(jwt_secret="short"))
    assert problems and "JWT_SECRET" in problems[0]


@pytest.mark.parametrize("env", ["staging", "production"])
def test_placeholder_secret_blocks_in_strict_env(env: str) -> None:
    with pytest.raises(SecretValidationError):
        check_required_secrets(_settings(jwt_secret="change-me", app_env=env))


def test_strict_override_forces_error_in_development() -> None:
    with pytest.raises(SecretValidationError):
        check_required_secrets(_settings(jwt_secret="change-me"), strict=True)


def test_strong_secret_passes_in_production() -> None:
    assert check_required_secrets(_settings(app_env="production")) == []
