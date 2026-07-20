"""Модуль «Исполнительная документация ПТО» (ROADMAP этап 12, §12/§20/§21).

Реестр исполнительной документации объекта: акты скрытых работ, исполнительные
схемы, журналы работ, сертификаты материалов, лабораторные документы, накопительные
ведомости. Каждый документ версионируется (устаревшая версия помечается
`superseded`), проходит инженерное согласование (утверждает уполномоченный
специалист — ИИ не подменяет инженерную подпись) и связывается с объектом и, при
необходимости, с фактическим объёмом работ. Обязательный комплект контролируется
автоматически (сопоставление требуемых типов с утверждёнными документами). Файлы
хранятся вне БД (D-008) — здесь только ссылка на `files`. Всё — под аудитом.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class ExecutiveDocument(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Документ исполнительной документации ПТО (версионируемый, с согласованием)."""

    __tablename__ = "executive_documents"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    # hidden_work_act | as_built_scheme | work_log | material_certificate |
    # lab_report | cumulative_statement | other
    doc_type: Mapped[str] = mapped_column(String(32), default="other")
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # ссылка на подтверждающий файл (метаданные — в files)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    # связь с фактическим объёмом/сущностью-основанием (проверяемость источника объёма)
    work_item_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    work_item_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # версионирование: новая версия ссылается на предыдущую; старая → superseded
    version_number: Mapped[int] = mapped_column(Integer, default=1)
    supersedes_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("executive_documents.id"), nullable=True
    )
    # draft | under_review | approved | rejected | superseded
    status: Mapped[str] = mapped_column(String(16), default="draft")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    reviewed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    review_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
