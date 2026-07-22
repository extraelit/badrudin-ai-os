"""Учётные данные WebAuthn / FIDO2 passkey (этап 1, отдельный безопасный контур).

Персональный аппаратный/платформенный ключ пользователя. На сервере хранится
**только публичный ключ** и метаданные — закрытый ключ никогда не покидает
устройство пользователя и в БД не попадает. Ключ имеет жизненный цикл
`active | suspended | revoked`; отозванный/приостановленный ключ вход не допускает.
Счётчик подписей (`sign_count`) монотонно растёт — регресс указывает на клонирование.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class WebAuthnCredential(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "webauthn_credentials"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    # идентификатор ключа (base64url) — уникален
    credential_id: Mapped[str] = mapped_column(String(512), unique=True)
    # ТОЛЬКО публичный ключ (base64url COSE); закрытый ключ на сервере не хранится
    public_key: Mapped[str] = mapped_column(String(1024))
    sign_count: Mapped[int] = mapped_column(Integer, default=0)
    aaguid: Mapped[str | None] = mapped_column(String(64), nullable=True)
    transports: Mapped[list | None] = mapped_column(JSON, nullable=True)
    label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # active | suspended | revoked
    status: Mapped[str] = mapped_column(String(16), default="active")
    registered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
