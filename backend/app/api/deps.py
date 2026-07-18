"""Общие зависимости FastAPI: текущий пользователь (T-1.C1)."""

from __future__ import annotations

import uuid

import jwt
from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from collections.abc import Callable

from app.core import token_store
from app.core.security import decode_token
from app.db.session import get_db
from app.models import User
from app.services.access import has_permission

_UNAUTHORIZED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Требуется аутентификация",
    headers={"WWW-Authenticate": "Bearer"},
)


def get_current_user(
    authorization: str | None = Header(default=None),
    db: Session = Depends(get_db),
) -> User:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise _UNAUTHORIZED
    token = authorization.split(" ", 1)[1].strip()
    try:
        payload = decode_token(token)
    except jwt.PyJWTError as exc:  # истёк, неверная подпись и т. п.
        raise _UNAUTHORIZED from exc

    if token_store.is_revoked(payload.get("jti", "")):
        raise _UNAUTHORIZED  # сессия отозвана (logout)

    user = db.get(User, uuid.UUID(payload["sub"]))
    if user is None or user.deleted_at is not None or user.status != "active":
        raise _UNAUTHORIZED
    return user


def require_permission(code: str) -> Callable[..., User]:
    """Фабрика зависимостей: требует наличие разрешения (RBAC, серверная проверка).

    Проверка выполняется на сервере, а не только в интерфейсе
    (ACCESS_CONTROL.md разделы 30, 32).
    """

    def _dep(
        current: User = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> User:
        if not has_permission(db, current.id, code):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Недостаточно прав для выполнения действия",
            )
        return current

    return _dep
