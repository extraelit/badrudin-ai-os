"""Эндпоинты аутентификации: вход, выход, текущий пользователь (T-1.C1)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import create_access_token, decode_token
from app.db.session import get_db
from app.models import User
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    MFAVerifyRequest,
    RecoveryCodesResponse,
    RecoveryStatusResponse,
    TokenResponse,
)
from app.services.access import get_permission_codes, get_role_codes
from app.services.audit import record_event
from app.services.auth import AuthError, authenticate, auth_level_for, verify_totp
from app.services.mfa_recovery import generate_recovery_codes, remaining_count

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(
    payload: LoginRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    try:
        user = authenticate(
            db, str(payload.email), payload.password, mfa_code=payload.mfa_code
        )
    except AuthError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)
        ) from exc
    token = create_access_token(subject=str(user.id), extra={"email": user.email})
    # Идентификатор сессии = jti токена; уровень аутентификации и адрес/агент —
    # для прослеживаемости входа (ACCESS_CONTROL.md раздел 20).
    session_id = decode_token(token).get("jti")
    record_event(
        db,
        actor_type="user",
        action="auth.login",
        actor_user_id=user.id,
        organization_id=None,
        session_id=session_id,
        auth_level=auth_level_for(db, user),
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
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
def me(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CurrentUser:
    # Роли и права нужны интерфейсу для отображения доступных действий (RBAC
    # проверяется на сервере; в UI — только для скрытия/показа элементов).
    roles = get_role_codes(db, current.id)
    permissions = get_permission_codes(db, current.id)
    return CurrentUser(
        id=str(current.id), email=current.email, status=current.status,
        employee_id=str(current.employee_id) if current.employee_id else None,
        roles=sorted(roles), permissions=sorted(permissions),
    )


@router.post("/mfa/verify")
def mfa_verify(
    payload: MFAVerifyRequest, current: User = Depends(get_current_user)
) -> dict[str, str]:
    # Повторное подтверждение личности для критических действий (step-up, R3/R4)
    if not current.mfa_enabled or not current.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA не настроена для пользователя",
        )
    if not verify_totp(current.mfa_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код MFA"
        )
    return {"status": "ok"}


@router.post("/mfa/recovery-codes", response_model=RecoveryCodesResponse)
def generate_mfa_recovery_codes(
    payload: MFAVerifyRequest,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecoveryCodesResponse:
    # Генерация кодов — чувствительное действие: требуем повторного подтверждения
    # действующим кодом TOTP (step-up). Прежние неиспользованные коды аннулируются.
    if not current.mfa_enabled or not current.mfa_secret:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="MFA не настроена для пользователя",
        )
    if not verify_totp(current.mfa_secret, payload.code):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Неверный код MFA"
        )
    codes = generate_recovery_codes(db, current.id)
    # В журнал попадает факт перевыпуска и их число, но НЕ сами коды.
    record_event(
        db,
        actor_type="user",
        action="auth.mfa.recovery_codes.generate",
        actor_user_id=current.id,
        organization_id=None,
        new_values={"count": len(codes)},
        risk_level="R2",
    )
    return RecoveryCodesResponse(codes=codes, count=len(codes))


@router.get("/mfa/recovery-codes", response_model=RecoveryStatusResponse)
def mfa_recovery_status(
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RecoveryStatusResponse:
    # Число оставшихся кодов (сами коды не возвращаются — их видно лишь при выпуске)
    return RecoveryStatusResponse(
        mfa_enabled=current.mfa_enabled,
        remaining=remaining_count(db, current.id),
    )
