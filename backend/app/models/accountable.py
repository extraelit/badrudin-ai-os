"""Модуль «Подотчётные денежные средства» (MVP, DATABASE.md раздел 32).

Полный жизненный цикл подотчётной суммы: выдача под отчёт → расходы с
подтверждающими документами → авансовый отчёт → проверка бухгалтером →
возврат/возмещение → закрытие. Разделение ролей инициатор/согласующий/бухгалтер,
контроль лимита и срока отчёта, предотвращение повторного использования чека
(`duplicate_hash`), запрет изменения утверждённого отчёта без истории, все
значимые действия — в `audit_events`. Система не проводит банковских операций
(D-015): возврат/возмещение только фиксируются.

Переиспользование без дублирования: сотрудники (`employees`), проекты/объекты
(`projects`/`sites`), задачи (`tasks`), поставщики (`suppliers`), статьи затрат
(`expense_categories` — расширены §32.6), файлы (`files`), согласования
(`approvals`), порог крупной операции (`finance_settings`), аудит (`audit_events`).
Все суммы — Decimal.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
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


class AccountableAdvance(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Выдача денежных средств под отчёт (DATABASE.md §32.3)."""

    __tablename__ = "accountable_advances"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    expense_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_categories.id"), nullable=True
    )
    advance_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    purpose: Mapped[str] = mapped_column(Text)
    amount_issued: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency_code: Mapped[str] = mapped_column(String(3), default="RUB")
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    report_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # cash | card | transfer | corporate_card
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    issued_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    # draft | pending_approval | approved | issued | partially_reported |
    # reported | under_accounting_review | correction_required | awaiting_return |
    # awaiting_reimbursement | closed | cancelled | overdue
    status: Mapped[str] = mapped_column(String(32), default="draft")
    amount_spent_confirmed: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    amount_returned: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    amount_reimbursable: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    balance_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class AccountableExpense(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Расход подотчётного лица (DATABASE.md §32.4)."""

    __tablename__ = "accountable_expenses"

    advance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accountable_advances.id")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    supplier_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True
    )
    expense_category_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("expense_categories.id")
    )
    expense_date: Mapped[date] = mapped_column(Date)
    description: Mapped[str] = mapped_column(Text)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency_code: Mapped[str] = mapped_column(String(3), default="RUB")
    vat_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # cash | card | transfer | corporate_card
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")
    receipt_required: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=false(), nullable=False
    )
    # missing | attached | verified
    document_status: Mapped[str] = mapped_column(String(20), default="missing")
    # draft | submitted | under_review | approved | partially_approved |
    # rejected | duplicate_suspected | clarification_required
    verification_status: Mapped[str] = mapped_column(String(24), default="draft")
    verified_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_from_mobile: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    latitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)


class ExpenseDocument(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Подтверждающий документ расхода — чек/накладная (DATABASE.md §32.5).

    Оригинал файла хранится в `files`; распознанные данные — отдельно.
    `duplicate_hash` уникален в пределах организации: один чек нельзя использовать
    повторно (предотвращение повторного использования, CLAUDE.md §16).
    """

    __tablename__ = "expense_documents"

    expense_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accountable_expenses.id")
    )
    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    # receipt | invoice | waybill | act | bill | other
    document_type: Mapped[str] = mapped_column(String(20), default="receipt")
    document_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    document_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    seller_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    seller_tax_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fiscal_sign: Mapped[str | None] = mapped_column(String(64), nullable=True)
    extracted_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    extracted_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    # pending | processed | failed | not_required
    ocr_status: Mapped[str] = mapped_column(String(16), default="pending")
    # уникальный отпечаток документа (организация + фискальный признак/номер)
    duplicate_hash: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    validated_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    validated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


class AdvanceReport(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Авансовый отчёт (DATABASE.md §32.7)."""

    __tablename__ = "advance_reports"

    advance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accountable_advances.id")
    )
    report_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    submitted_by_employee_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("employees.id")
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_expenses_submitted: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    total_expenses_approved: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    amount_to_return: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    amount_to_reimburse: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    # submitted | under_review | approved | correction_required | closed
    status: Mapped[str] = mapped_column(String(24), default="submitted")
    accountant_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    accountant_reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # pending | exported | not_required
    accounting_export_status: Mapped[str] = mapped_column(String(16), default="pending")


class AdvanceSettlement(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Возврат остатка или возмещение перерасхода (DATABASE.md §32.8).

    Операция только фиксируется (система не проводит банковских операций, D-015).
    """

    __tablename__ = "advance_settlements"

    advance_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("accountable_advances.id")
    )
    report_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("advance_reports.id"), nullable=True
    )
    # return | reimbursement
    settlement_type: Mapped[str] = mapped_column(String(16))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency_code: Mapped[str] = mapped_column(String(3), default="RUB")
    settled_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # cash | transfer | cashbox | bank
    payment_method: Mapped[str] = mapped_column(String(20), default="cash")
    payment_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    processed_by_user_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    # recorded | confirmed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="recorded")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
