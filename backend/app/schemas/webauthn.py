"""Схемы WebAuthn / passkey (этап 1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr


class RegisterCompleteIn(BaseModel):
    # ответ authenticator (PublicKeyCredential) как есть от navigator.credentials
    credential: dict
    label: str | None = None


class AuthenticateBeginIn(BaseModel):
    email: EmailStr


class AuthenticateCompleteIn(BaseModel):
    email: EmailStr
    credential: dict


class CredentialOut(BaseModel):
    id: uuid.UUID
    label: str | None
    status: str
    aaguid: str | None
    registered_at: datetime
    last_used_at: datetime | None


class StatusOut(BaseModel):
    status: str
