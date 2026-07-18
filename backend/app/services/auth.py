"""Сервис аутентификации: проверка учётных данных, блокировки (T-1.C1).

Реализует учёт неудачных входов и временную блокировку
(ACCESS_CONTROL.md раздел 19).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

import pyotp

from app.core.config import get_settings
from app.core.security import verify_password
from app.models import User
from app.services.access import get_role_codes


class AuthError(Exception):
    """Ошибка аутентификации (неверные данные, блокировка, неактивен)."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def _now() -> datetime:
    return datetime.now(UTC)


def _mfa_required_for(session: Session, user: User) -> bool:
    settings = get_settings()
    required = {r.strip() for r in settings.mfa_required_roles.split(",") if r.strip()}
    return bool(get_role_codes(session, user.id) & required)


def verify_totp(secret: str, code: str) -> bool:
    return pyotp.TOTP(secret).verify(code, valid_window=1)


def authenticate(
    session: Session, email: str, password: str, mfa_code: str | None = None
) -> User:
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

    # MFA обязательна для критических ролей (ACCESS_CONTROL.md раздел 19)
    if _mfa_required_for(session, user):
        if not user.mfa_enabled or not user.mfa_secret:
            raise AuthError(
                "mfa_setup_required",
                "Для этой роли требуется настроить многофакторную аутентификацию",
            )
        if not mfa_code:
            raise AuthError("mfa_required", "Требуется код многофакторной аутентификации")
        if not verify_totp(user.mfa_secret, mfa_code):
            raise AuthError("mfa_invalid", "Неверный код многофакторной аутентификации")

    # успех: сбрасываем счётчик, фиксируем вход
    user.failed_login_count = 0
    user.locked_until = None
    user.last_login_at = _now()
    session.commit()
    return user
