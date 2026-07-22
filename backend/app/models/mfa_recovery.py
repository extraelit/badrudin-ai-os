"""Резервные коды восстановления MFA (этап 1, ACCESS_CONTROL.md раздел 19).

Одноразовые коды позволяют владельцу учётной записи войти, если недоступно
основное средство MFA (например, утеряно TOTP-устройство). Коды хранятся только
в виде хеша (в открытом виде показываются пользователю один раз при генерации).
Использованный код повторно не принимается (`used_at`).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class MfaRecoveryCode(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "mfa_recovery_codes"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id"), index=True, nullable=False
    )
    # хеш кода (bcrypt); сам код в БД не хранится
    code_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    # момент использования; NULL — код ещё действителен (одноразовый)
    used_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
