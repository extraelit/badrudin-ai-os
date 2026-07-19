"""Дополнительные сущности мобильного ежедневного отчёта прораба.

Расширяют существующий `daily_reports` (§18, DATABASE.md разделы 9, 21) без
дублирования: техника на объекте за смену и доказательства (фото/файлы),
связанные с отчётом и, при необходимости, с конкретной выполненной работой.
Численность (`daily_report_headcount`), проблемы (`daily_report_issues`) и
объёмы работ (`daily_report_work_items`) уже существуют и переиспользуются.
Файлы хранятся в MinIO вне БД (D-008); здесь — только связь с метаданными `files`.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class DailyReportEquipment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Техника и оборудование на объекте за смену (в составе ежедневного отчёта)."""

    __tablename__ = "daily_report_equipment"

    daily_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id")
    )
    name: Mapped[str] = mapped_column(String(255))
    equipment_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    count: Mapped[int] = mapped_column(Integer, default=1)
    hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    # working | idle | repair
    status: Mapped[str] = mapped_column(String(16), default="working")
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DailyReportFile(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Доказательство (фото/видео/документ) в ежедневном отчёте прораба.

    Связывает отчёт (и при необходимости конкретную выполненную работу) с
    метаданными файла `files`. Несколько доказательств на один отчёт.
    """

    __tablename__ = "daily_report_files"

    daily_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id")
    )
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("daily_report_work_items.id"), nullable=True
    )
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"))
    # photo | video | document
    kind: Mapped[str] = mapped_column(String(16), default="photo")
    caption: Mapped[str | None] = mapped_column(String(500), nullable=True)
    captured_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
