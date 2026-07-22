"""Сервис WebAuthn / FIDO2 passkey (этап 1, отдельный безопасный контур).

Инкапсулирует церемонии регистрации и аутентификации по стандарту WebAuthn:
- `begin_*` формирует опции с одноразовым челленджем (хранится на сервере);
- `complete_registration` проверяет ответ устройства и сохраняет **только
  публичный ключ** и метаданные (закрытый ключ на сервере не хранится);
- `complete_authentication` проверяет подпись и **отклоняет отозванный или
  приостановленный ключ** (вход не допускается), а также требует монотонного
  роста `sign_count` (защита от клонирования).

Криптографическая проверка делегируется библиотеке `webauthn`.
"""

from __future__ import annotations

import base64
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session
from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorSelectionCriteria,
    PublicKeyCredentialDescriptor,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import get_settings
from app.core import webauthn_challenge as challenge_store
from app.models import User, WebAuthnCredential


class WebAuthnError(Exception):
    """Ошибка церемонии WebAuthn (проверка не пройдена, ключ недоступен и т. п.)."""


def _now() -> datetime:
    return datetime.now(UTC)


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    return base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))


def _active_credentials(session: Session, user_id: uuid.UUID) -> list[WebAuthnCredential]:
    return list(
        session.execute(
            select(WebAuthnCredential).where(
                WebAuthnCredential.user_id == user_id,
                WebAuthnCredential.status == "active",
            )
        ).scalars()
    )


# --- Регистрация -----------------------------------------------------------


def begin_registration(session: Session, user: User) -> dict:
    """Формирует опции регистрации нового ключа и сохраняет челлендж."""
    s = get_settings()
    existing = _active_credentials(session, user.id)
    options = generate_registration_options(
        rp_id=s.webauthn_rp_id,
        rp_name=s.webauthn_rp_name,
        user_id=user.id.bytes,
        user_name=user.email,
        user_display_name=user.email,
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=_b64url_decode(c.credential_id))
            for c in existing
        ],
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.PREFERRED,
            user_verification=UserVerificationRequirement.PREFERRED,
        ),
    )
    challenge_store.put(f"reg:{user.id}", options.challenge)
    import json

    return json.loads(options_to_json(options))


def complete_registration(
    session: Session,
    user: User,
    credential: dict,
    *,
    label: str | None = None,
) -> WebAuthnCredential:
    """Проверяет ответ устройства и сохраняет публичный ключ (без закрытого)."""
    s = get_settings()
    expected = challenge_store.take(f"reg:{user.id}")
    if expected is None:
        raise WebAuthnError("Челлендж регистрации отсутствует или истёк")
    try:
        verified = verify_registration_response(
            credential=credential,
            expected_challenge=expected,
            expected_rp_id=s.webauthn_rp_id,
            expected_origin=s.webauthn_rp_origin,
        )
    except Exception as exc:  # noqa: BLE001 — любую ошибку проверки скрываем от клиента
        raise WebAuthnError("Проверка регистрации ключа не пройдена") from exc

    cred = WebAuthnCredential(
        user_id=user.id,
        credential_id=_b64url(verified.credential_id),
        public_key=_b64url(verified.credential_public_key),
        sign_count=verified.sign_count,
        aaguid=verified.aaguid,
        label=label,
        status="active",
        registered_at=_now(),
    )
    session.add(cred)
    session.commit()
    return cred


# --- Аутентификация --------------------------------------------------------


def begin_authentication(session: Session, user: User) -> dict:
    """Формирует опции аутентификации по активным ключам пользователя."""
    s = get_settings()
    active = _active_credentials(session, user.id)
    if not active:
        raise WebAuthnError("У пользователя нет активных ключей")
    options = generate_authentication_options(
        rp_id=s.webauthn_rp_id,
        allow_credentials=[
            PublicKeyCredentialDescriptor(id=_b64url_decode(c.credential_id))
            for c in active
        ],
        user_verification=UserVerificationRequirement.PREFERRED,
    )
    challenge_store.put(f"auth:{user.id}", options.challenge)
    import json

    return json.loads(options_to_json(options))


def complete_authentication(
    session: Session, user: User, credential: dict
) -> WebAuthnCredential:
    """Проверяет подпись; отклоняет отозванный/приостановленный ключ и регресс счётчика."""
    s = get_settings()
    expected = challenge_store.take(f"auth:{user.id}")
    if expected is None:
        raise WebAuthnError("Челлендж аутентификации отсутствует или истёк")

    raw_id = credential.get("rawId") or credential.get("id")
    if not raw_id:
        raise WebAuthnError("Некорректный ответ устройства")
    cred = session.execute(
        select(WebAuthnCredential).where(
            WebAuthnCredential.user_id == user.id,
            WebAuthnCredential.credential_id == raw_id,
        )
    ).scalar_one_or_none()
    if cred is None:
        raise WebAuthnError("Ключ не найден")
    # отозванный/приостановленный ключ вход не допускает
    if cred.status != "active":
        raise WebAuthnError("Ключ отозван или приостановлен — вход невозможен")

    try:
        verified = verify_authentication_response(
            credential=credential,
            expected_challenge=expected,
            expected_rp_id=s.webauthn_rp_id,
            expected_origin=s.webauthn_rp_origin,
            credential_public_key=_b64url_decode(cred.public_key),
            credential_current_sign_count=cred.sign_count,
        )
    except Exception as exc:  # noqa: BLE001
        raise WebAuthnError("Проверка подписи ключа не пройдена") from exc

    # монотонность счётчика подписей (регресс — признак клонирования)
    if cred.sign_count and verified.new_sign_count <= cred.sign_count:
        raise WebAuthnError("Обнаружен регресс счётчика подписей ключа")
    cred.sign_count = verified.new_sign_count
    cred.last_used_at = _now()
    session.commit()
    return cred


# --- Управление ключами ----------------------------------------------------


def list_credentials(session: Session, user_id: uuid.UUID) -> list[WebAuthnCredential]:
    return list(
        session.execute(
            select(WebAuthnCredential)
            .where(WebAuthnCredential.user_id == user_id)
            .order_by(WebAuthnCredential.registered_at.desc())
        ).scalars()
    )


def _owned(session: Session, user_id: uuid.UUID, cred_id: uuid.UUID) -> WebAuthnCredential:
    cred = session.get(WebAuthnCredential, cred_id)
    if cred is None or cred.user_id != user_id:
        raise WebAuthnError("Ключ не найден")
    return cred


def set_status(
    session: Session, user_id: uuid.UUID, cred_id: uuid.UUID, status: str
) -> WebAuthnCredential:
    if status not in ("active", "suspended", "revoked"):
        raise WebAuthnError(f"Недопустимый статус ключа: {status}")
    cred = _owned(session, user_id, cred_id)
    # отозванный ключ нельзя реактивировать (необратимый отзыв)
    if cred.status == "revoked" and status != "revoked":
        raise WebAuthnError("Отозванный ключ нельзя вернуть в строй")
    cred.status = status
    session.commit()
    return cred
