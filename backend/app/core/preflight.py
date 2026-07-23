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
    problems.extend(_production_problems(settings))
    return problems


def _production_problems(settings: Settings) -> list[str]:
    """Дополнительные требования production-контура (PR-9).

    Применяются только в strict-окружениях (staging/production); в development и
    test не проверяются, чтобы не мешать локальной работе и CI.
    """
    if not settings.is_strict_env:
        return []
    problems: list[str] = []
    # Промышленное файловое хранилище — S3-совместимое, не локальная ФС.
    if settings.storage_backend != "s3":
        problems.append("STORAGE_BACKEND: для production требуется 's3'")
    else:
        for key in ("minio_access_key", "minio_secret_key"):
            if (getattr(settings, key, "") or "").strip().lower() in PLACEHOLDER_VALUES:
                problems.append(f"{key.upper()}: не задан (значение-заглушка)")
    # База данных — не SQLite и без заглушечного пароля.
    db = (settings.database_url or "").lower()
    if db.startswith("sqlite"):
        problems.append("DATABASE_URL: SQLite недопустим в production (нужен PostgreSQL)")
    elif "change-me" in db:
        problems.append("DATABASE_URL: содержит значение-заглушку 'change-me'")
    # Отладка выключена, cookie только по HTTPS.
    if settings.app_debug:
        problems.append("APP_DEBUG: должен быть false в production")
    if not settings.cookie_secure:
        problems.append("COOKIE_SECURE: должен быть true в production (HTTPS)")
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
