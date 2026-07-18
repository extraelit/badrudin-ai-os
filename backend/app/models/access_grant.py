"""Дополнительный доступ пользователя к проекту (T-1.C5).

Соответствует DATABASE.md раздел 4.7 и ACCESS_CONTROL.md раздел 23 (временный
доступ с датой окончания и автоматическим прекращением).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class ProjectAccess(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_access"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id"))
    access_level: Mapped[str] = mapped_column(String(32), default="read")
    valid_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    valid_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    granted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
