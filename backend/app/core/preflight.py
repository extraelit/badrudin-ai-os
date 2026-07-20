"""Проверка обязательных секретов перед запуском (fail-fast).

Мотивация (см. ACCESS_CONTROL.md раздел 24; ARCHITECTURE.md раздел 12.3):
секреты задаются только через окружение и не должны оставаться значениями-
заглушками из `.env.example`. Проверка выполняется при создании приложения и в
бутстрап-скрипте `scripts/dev_bootstrap.py`.

Политика по окружениям:
- `staging` / `production` — запуск с заглушкой или слишком коротким секретом
  запрещён (поднимается `SecretValidationError`);
- `development` / `test` — выводится предупреждение, но запуск не блокируется
  (удобство локальной разработки; для реальной работы секрет всё равно нужен).
"""

from __future__ import annotations

import logging

from app.core.config import Settings

logger = logging.getLogger("app.preflight")

# Значения-заглушки из `.env.example`, обязательные к замене (D-008).
PLACEHOLDER_VALUES = frozenset({"", "change-me", "replace_me"})

# Минимальная длина секрета для HS256 (RFC 7518, раздел 3.2).
MIN_SECRET_LENGTH = 32

# Секреты, критичные для безопасности API. `SECRET_KEY` в объекте настроек
# отсутствует (extra="ignore"), поэтому проверяется реально используемый JWT-секрет.
REQUIRED_SECRETS: tuple[str, ...] = ("jwt_secret",)

# Окружения, где небезопасная конфигурация блокирует запуск.
STRICT_ENVIRONMENTS = frozenset({"staging", "production"})


class SecretValidationError(RuntimeError):
    """Небезопасная конфигурация секретов для текущего окружения."""


def _problems_for(settings: Settings) -> list[str]:
    problems: list[str] = []
    for name in REQUIRED_SECRETS:
        value = (getattr(settings, name, "") or "").strip()
        if value.lower() in PLACEHOLDER_VALUES:
            problems.append(f"{name.upper()}: не задан (значение-заглушка)")
        elif len(value) < MIN_SECRET_LENGTH:
            problems.append(
                f"{name.upper()}: слишком короткий — {len(value)} байт "
                f"(минимум {MIN_SECRET_LENGTH})"
            )
    return problems


def check_required_secrets(
    settings: Settings, *, strict: bool | None = None
) -> list[str]:
    """Проверяет обязательные секреты приложения.

    Возвращает список найденных проблем (пустой — всё в порядке). В strict-режиме
    (по умолчанию для staging/production) при наличии проблем поднимает
    `SecretValidationError`; иначе — только предупреждение в лог.
    """
    problems = _problems_for(settings)
    if strict is None:
        strict = settings.app_env.strip().lower() in STRICT_ENVIRONMENTS
    if problems:
        detail = "; ".join(problems)
        if strict:
            raise SecretValidationError(
                f"Небезопасная конфигурация секретов для окружения "
                f"'{settings.app_env}': {detail}. Задайте значения длиной "
                f"не менее {MIN_SECRET_LENGTH} байт через переменные окружения."
            )
        logger.warning(
            "Небезопасные секреты (окружение '%s'): %s. Для development это "
            "допустимо; в staging/production запуск будет заблокирован.",
            settings.app_env,
            detail,
        )
    return problems
