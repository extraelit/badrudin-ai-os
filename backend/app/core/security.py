"""Утилиты безопасности: хеширование паролей и JWT-токены (T-1.C1).

Пароли хранятся только в виде bcrypt-хеша (ACCESS_CONTROL.md разделы 2, 19).
Секрет подписи токенов берётся из конфигурации (окружение), не из кода.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import get_settings


def hash_password(password: str) -> str:
    """Возвращает bcrypt-хеш пароля."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Проверяет пароль против хеша."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"), password_hash.encode("utf-8")
        )
    except (ValueError, TypeError):
        return False


def create_access_token(
    subject: str, extra: dict | None = None, expires_minutes: int | None = None
) -> str:
    """Создаёт подписанный JWT access-токен."""
    settings = get_settings()
    now = datetime.now(UTC)
    minutes = expires_minutes or settings.access_token_expire_minutes
    payload: dict = {
        "sub": subject,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(minutes=minutes)).timestamp()),
        "jti": str(uuid.uuid4()),
        "type": "access",
    }
    if extra:
        payload.update(extra)
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict:
    """Проверяет подпись и срок действия токена, возвращает payload."""
    settings = get_settings()
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )
