"""Маскирование секретов в журналах (T-1.H1).

Секреты хранятся только в переменных окружения / .env вне Git (D-008;
ARCHITECTURE.md раздел 12.3). Журналы и сообщения маскируют секретные значения
(ACCESS_CONTROL.md раздел 24).
"""

from __future__ import annotations

import logging

from app.core.config import get_settings


def mask_secret(value: str | None, visible: int = 2) -> str:
    """Маскирует секрет, оставляя видимыми несколько символов."""
    if not value:
        return ""
    if len(value) <= visible * 2:
        return "*" * len(value)
    return f"{value[:visible]}{'*' * (len(value) - visible * 2)}{value[-visible:]}"


def _secret_values() -> list[str]:
    s = get_settings()
    values = [
        s.jwt_secret,
        s.minio_secret_key,
        s.minio_access_key,
    ]
    return [v for v in values if v and v != "change-me"]


class SecretMaskingFilter(logging.Filter):
    """Заменяет известные секретные значения в тексте журнала на маску."""

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        for secret in _secret_values():
            if secret in message:
                message = message.replace(secret, mask_secret(secret))
        record.msg = message
        record.args = ()
        return True
