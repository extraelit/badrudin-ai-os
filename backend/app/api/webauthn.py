"""API WebAuthn / FIDO2 passkey (этап 1, отдельный безопасный контур).

Регистрация ключа выполняется аутентифицированным пользователем; вход по ключу —
публичные эндпоинты церемонии. На сервере хранится только публичный ключ.
Отозванный/приостановленный ключ вход не допускает. Значимые события — в аудит.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user
from app.core.security import create_access_token, decode_token
from app.db.session import get_db
from app.models import User, WebAuthnCredential
from app.schemas.webauthn import (
    AuthenticateBeginIn,
    AuthenticateCompleteIn,
    CredentialOut,
    RegisterCompleteIn,
    StatusOut,
)
from app.schemas.auth import TokenResponse
from app.services import webauthn as svc
from app.services.audit import record_event

router = APIRouter(prefix="/auth/webauthn", tags=["webauthn"])


def _cred_out(c: WebAuthnCredential) -> CredentialOut:
    return CredentialOut(
        id=c.id, label=c.label, status=c.status, aaguid=c.aaguid,
        registered_at=c.registered_at, last_used_at=c.last_used_at,
    )


# --- Регистрация ключа (аутентифицированный пользователь) -------------------


@router.post("/register/begin")
def register_begin(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> dict:
    return svc.begin_registration(db, current)


@router.post("/register/complete", response_model=CredentialOut, status_code=201)
def register_complete(
    payload: RegisterCompleteIn,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CredentialOut:
    try:
        cred = svc.complete_registration(
            db, current, payload.credential, label=payload.label
        )
    except svc.WebAuthnError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(exc)) from exc
    record_event(
        db, actor_type="user", action="auth.webauthn.register",
        actor_user_id=current.id, entity_type="webauthn_credential",
        entity_id=cred.id, risk_level="R2",
    )
    return _cred_out(cred)


@router.get("/credentials", response_model=list[CredentialOut])
def list_credentials(
    current: User = Depends(get_current_user), db: Session = Depends(get_db)
) -> list[CredentialOut]:
    return [_cred_out(c) for c in svc.list_credentials(db, current.id)]


@router.post("/credentials/{cred_id}/revoke", response_model=StatusOut)
def revoke_credential(
    cred_id: uuid.UUID,
    current: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> StatusOut:
    try:
        cred = svc.set_status(db, current.id, cred_id, "revoked")
    except svc.WebAuthnError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    record_event(
        db, actor_type="user", action="auth.webauthn.revoke",
        actor_user_id=current.id, entity_type="webauthn_credential",
        entity_id=cred.id, new_values={"status": "revoked"}, risk_level="R2",
    )
    return StatusOut(status=cred.status)


# --- Вход по ключу (публичная церемония) ------------------------------------


def _active_user_by_email(db: Session, email: str) -> User:
    user = db.scalar(
        select(User).where(User.email == email, User.deleted_at.is_(None))
    )
    if user is None or user.status != "active":
        # не раскрываем наличие учётной записи
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Невозможно начать вход по ключу"
        )
    return user


@router.post("/authenticate/begin")
def authenticate_begin(
    payload: AuthenticateBeginIn, db: Session = Depends(get_db)
) -> dict:
    user = _active_user_by_email(db, str(payload.email))
    try:
        return svc.begin_authentication(db, user)
    except svc.WebAuthnError as exc:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Невозможно начать вход по ключу"
        ) from exc


@router.post("/authenticate/complete", response_model=TokenResponse)
def authenticate_complete(
    payload: AuthenticateCompleteIn,
    request: Request,
    db: Session = Depends(get_db),
) -> TokenResponse:
    user = _active_user_by_email(db, str(payload.email))
    try:
        svc.complete_authentication(db, user, payload.credential)
    except svc.WebAuthnError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc

    token = create_access_token(subject=str(user.id), extra={"email": user.email})
    session_id = decode_token(token).get("jti")
    record_event(
        db, actor_type="user", action="auth.login", actor_user_id=user.id,
        session_id=session_id, auth_level="passkey",
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    return TokenResponse(access_token=token)
