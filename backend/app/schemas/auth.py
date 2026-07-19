"""Схемы аутентификации (T-1.C1)."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


class MFAVerifyRequest(BaseModel):
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CurrentUser(BaseModel):
    id: str
    email: EmailStr
    status: str
    roles: list[str] = []
    permissions: list[str] = []
