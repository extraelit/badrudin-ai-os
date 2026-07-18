"""Эндпоинты аутентификации: вход, выход, текущий пользователь (T-1.C1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import create_access_token, decode_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import CurrentUser, LoginRequest, TokenResponse
from app.services.auth import AuthError, authenticate

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    try:
        user = authenticate(db, str(payload.email), payload.password)
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    token = create_access_token(subject=str(user.id), extra={"email": user.email})
    return TokenResponse(access_token=token)


@router.post("/logout")
def logout(authorization: str | None = Header(default=None)) -> dict[str, str]:
    # Отзыв текущего токена (jti) — сессия завершается (ACCESS_CONTROL.md раздел 19)
    if authorization and authorization.lower().startswith("bearer "):
        token = authorization.split(" ", 1)[1].strip()
        try:
            payload = decode_token(token)
            token_store.revoke(payload.get("jti", ""))
        except Exception:  # noqa: BLE001 - при неверном токене отзывать нечего
            pass
    return {"status": "ok"}


@router.get("/me", response_model=CurrentUser)
def me(current: User = Depends(get_current_user)) -> CurrentUser:
    return CurrentUser(id=str(current.id), email=current.email, status=current.status)
