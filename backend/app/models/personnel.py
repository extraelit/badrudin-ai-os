"""Производственный учёт персонала по объектам (модуль «Персонал объектов»).

Переиспользует утверждённый канон сущностей (DATABASE.md раздел 2.9, D-009):
работники → `employees`, объекты → `sites`/`projects`, документы/инструктажи/
удостоверения → `documents`, согласования выплат → `approvals` (R0–R4, D-001/D-002),
все действия → `audit_events`. Реальные ПДн и секреты не используются (D-011).

Новые прикладные сущности:
- site_worker_assignments — фактический состав людей на объекте;
- work_shifts — смены и табель пофамильно;
- payroll_drafts / payroll_lines — предварительный расчёт начислений (ФОТ);
- safety_clearances / work_permits — инструктажи, допуски и сроки документов;
- foreman_journals — журналы прораба и контроль их заполнения;
- daily_report_headcount / daily_report_issues — расширение ежедневного отчёта.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
    false,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class SiteWorkerAssignment(
    UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base
):
    """Фактическое закрепление работника за объектом (переиспользует employees)."""

    __tablename__ = "site_worker_assignments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    brigade: Mapped[str | None] = mapped_column(String(64), nullable=True)
    profession: Mapped[str | None] = mapped_column(String(128), nullable=True)
    # active | transferred | released
    status: Mapped[str] = mapped_column(String(32), default="active")
    is_responsible: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


class WorkShift(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Смена работника за день (табель пофамильно)."""

    __tablename__ = "work_shifts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    assignment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("site_worker_assignments.id"), nullable=True
    )
    work_date: Mapped[date] = mapped_column(Date)
    # day | night
    shift_type: Mapped[str] = mapped_column(String(16), default="day")
    arrival_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    departure_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    hours_worked: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    overtime_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    idle_hours: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    # none | vacation | sick | absent | no_clearance
    absence_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    volume_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # draft | confirmed
    status: Mapped[str] = mapped_column(String(16), default="draft")


class PayrollDraft(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Заголовок предварительного расчёта начислений по объекту за период."""

    __tablename__ = "payroll_drafts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)
    # draft | foreman_checked | approved | exported | rejected
    status: Mapped[str] = mapped_column(String(32), default="draft")
    total_accrued: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_advance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_deduction: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_to_pay: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # уровень риска действия выплаты (D-001): R3 обычная сумма, R4 крупная/массовая
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PayrollLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Строка начисления по работнику (почасовая/посменная/окладная/сдельная)."""

    __tablename__ = "payroll_lines"

    payroll_draft_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("payroll_drafts.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    # hourly | shift | salary | piece_rate
    scheme: Mapped[str] = mapped_column(String(16), default="hourly")
    rate: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    accrued: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    advance: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    deduction: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    to_pay: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    # draft | foreman_checked | approved | exported
    status: Mapped[str] = mapped_column(String(32), default="draft")


class SafetyClearance(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Охрана труда: инструктажи, подписи, медосмотр и общий статус допуска."""

    __tablename__ = "safety_clearances"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    intro_briefing_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    primary_briefing_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    targeted_briefing_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    signed_by_worker: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    medical_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # ссылка на подтверждающий документ (документооборот, не дублируем файлы)
    signature_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    certificates: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    # cleared | not_cleared | pending — итоговый статус вычисляется сервисом
    status: Mapped[str] = mapped_column(String(32), default="not_cleared")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class WorkPermit(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Допуск к специальным работам со сроком действия (высотные, сварочные и др.)."""

    __tablename__ = "work_permits"

    clearance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("safety_clearances.id")
    )
    # height | welding | earthworks | electrical | confined_space | gas | other
    permit_type: Mapped[str] = mapped_column(String(32))
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    # active | expired | suspended
    status: Mapped[str] = mapped_column(String(16), default="active")


class ForemanJournal(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Обязательный журнал прораба и контроль его заполнения."""

    __tablename__ = "foreman_journals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    site_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("sites.id"))
    # general_works | incoming_control | briefings | works_production |
    # concrete | welding | earthworks | special
    journal_type: Mapped[str] = mapped_column(String(32))
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    # filled | not_filled | overdue | needs_review
    status: Mapped[str] = mapped_column(String(32), default="not_filled")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_filled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attachments_count: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class DailyReportHeadcount(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Численность по профессиям в ежедневном отчёте прораба (расширяет daily_reports)."""

    __tablename__ = "daily_report_headcount"

    daily_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id")
    )
    profession: Mapped[str] = mapped_column(String(128))
    count: Mapped[int] = mapped_column(Integer, default=0)
    employee_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class DailyReportIssue(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Простои, материалы и происшествия в ежедневном отчёте прораба."""

    __tablename__ = "daily_report_issues"

    daily_report_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("daily_reports.id")
    )
    # idle | materials | incident | equipment
    issue_type: Mapped[str] = mapped_column(String(32))
    description: Mapped[str] = mapped_column(Text)
    severity: Mapped[str] = mapped_column(String(16), default="info")
