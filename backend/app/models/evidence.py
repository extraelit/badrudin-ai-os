"""Evidence Gate — матрица обязательных доказательств процесса (этап D, PR-D2).

Модель доказательности (PROCESS_CORE_PLAN.md §2):
- `evidence_requirement_matrix` — настраиваемая матрица «вид процесса → обязательные
  доказательства» (по организации). По умолчанию пусто — гейт не мешает, пока
  требования не заданы (дисциплина без бюрократии ради бюрократии).
- `process_evidence` — фактически приложенные доказательства; файл обязателен
  (карточка без файла доказательством не считается).
- `evidence_exception_requests` — запрос на исключение при отсутствии обязательного
  доказательства: причина обязательна, согласует уполномоченный руководитель
  (ген./исп. директор), результат помечается «принят без стандартного доказательства».
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPrimaryKeyMixin

# Типы доказательств (PROCESS_CORE_PLAN.md §2.1).
EVIDENCE_TYPES = (
    "electronic_original", "pdf", "scan", "photo", "video", "act",
    "delivery_note", "invoice", "certificate", "quality_passport",
    "test_protocol", "as_built_scheme", "work_log", "correspondence", "other",
)
EVIDENCE_PHASES = ("before", "during", "after")


class EvidenceRequirement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_requirement_matrix"
    __table_args__ = (
        UniqueConstraint("organization_id", "process_kind", "evidence_type"),
    )

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), index=True
    )
    process_kind: Mapped[str] = mapped_column(String(48), index=True)
    evidence_type: Mapped[str] = mapped_column(String(48))
    required: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=true(), nullable=False
    )
    condition: Mapped[str | None] = mapped_column(String(512), nullable=True)
    min_count: Mapped[int] = mapped_column(Integer, default=1)
    phase: Mapped[str] = mapped_column(String(8), default="after")


class ProcessEvidence(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "process_evidence"

    process_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_processes.id"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(48))
    # файл обязателен — доказательство без файла не принимается
    file_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("files.id"))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    captured_phase: Mapped[str | None] = mapped_column(String(8), nullable=True)
    added_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class EvidenceExceptionRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "evidence_exception_requests"

    process_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workflow_processes.id"), index=True
    )
    evidence_type: Mapped[str] = mapped_column(String(48))
    reason: Mapped[str] = mapped_column(Text)  # причина обязательна
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(16), default="pending")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    decision_comment: Mapped[str | None] = mapped_column(Text, nullable=True)
