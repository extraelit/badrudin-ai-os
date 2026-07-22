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
    employee_id: str | None = None
    roles: list[str] = []
    permissions: list[str] = []


class RecoveryCodesResponse(BaseModel):
    """Комплект одноразовых кодов восстановления MFA (показывается один раз)."""

    codes: list[str]
    count: int


class RecoveryStatusResponse(BaseModel):
    """Состояние резервных кодов: включена ли MFA и сколько кодов осталось."""

    mfa_enabled: bool
    remaining: int
