"""Сервис аутентификации: проверка учётных данных, блокировки (T-1.C1).

Реализует учёт неудачных входов и временную блокировку
(ACCESS_CONTROL.md раздел 19).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import verify_password
from app.models import User


class AuthError(Exception):
    """Ошибка аутентификации (неверные данные, блокировка, неактивен)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(UTC)


def authenticate(session: Session, email: str, password: str) -> User:
    settings = get_settings()
    user = session.scalar(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    # одинаковая ошибка для несуществующего/неверного, чтобы не раскрывать наличие
    if user is None:
        raise AuthError("invalid_credentials", "Неверный e-mail или пароль")

    locked_until = user.locked_until
    if locked_until is not None and locked_until.tzinfo is None:
        locked_until = locked_until.replace(tzinfo=UTC)
    if locked_until is not None and locked_until > _now():
        raise AuthError("locked", "Учётная запись временно заблокирована")

    if user.status != "active":
        raise AuthError("inactive", "Учётная запись неактивна")

    if not verify_password(password, user.password_hash):
        user.failed_login_count = (user.failed_login_count or 0) + 1
        if user.failed_login_count >= settings.max_failed_logins:
            user.locked_until = _now() + timedelta(minutes=settings.lockout_minutes)
        session.commit()
        raise AuthError("invalid_credentials", "Неверный e-mail или пароль")

    # успех: сбрасываем счётчик, фиксируем вход
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    session.commit()
    return user
