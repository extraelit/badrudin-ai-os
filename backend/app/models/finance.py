"""Модуль «Финансы и бюджеты» (MVP).

Реализует бюджетный контур (DATABASE.md раздел 16.2–16.4) и общий справочник
статей затрат (переиспользуется будущим модулем подотчётных средств):
- `finance_settings` — порог крупной финансовой операции организации (R4 + MFA);
- `expense_categories` — справочник статей затрат;
- `budgets` — бюджет проекта (формируется из утверждённой сметы);
- `budget_lines` — статьи бюджета (план/утверждено/обязательства/факт/прогноз);
- `financial_commitments` — ручные обязательства («решения»), не покрытые
  заказами и договорами.

Переиспользование без дублирования: план берётся из `estimates`/
`estimate_positions`; обязательства и факт агрегируются из `purchase_orders`,
`contracts` и `payroll_drafts` (сервис финансовой сводки), а не копируются.
Согласования — общий контур `approvals` (R3/R4 + MFA); документы — `documents`;
контрагенты — `counterparties`; аудит — `audit_events`. Все суммы — Decimal.
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


class FinanceSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Настройки финансов организации: порог крупной операции (R4 + MFA).

    Порог задаётся владельцем на уровне организации, а не жёстко в коде.
    Значение по умолчанию — 10 000 000 ₽: сумма ≥ порога → R4 + MFA, иначе R3.
    """

    __tablename__ = "finance_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), unique=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    large_operation_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=10000000
    )


class ExpenseCategory(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Справочник статей затрат (общий; переиспользуется подотчётными средствами)."""

    __tablename__ = "expense_categories"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_categories.id"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    # material | labor | machine | subcontract | overhead | other
    kind: Mapped[str] = mapped_column(String(32), default="other")
    status: Mapped[str] = mapped_column(String(16), default="active")


class Budget(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Бюджет проекта (DATABASE.md раздел 16.2).

    Базовый бюджет формируется из утверждённой сметы (`source_estimate_id`);
    ручные статьи допускаются только для расходов вне сметы.
    """

    __tablename__ = "budgets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    source_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimates.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), default="Бюджет проекта")
    version: Mapped[int] = mapped_column(Integer, default=1)
    period_start: Mapped[date | None] = mapped_column(Date, nullable=True)
    period_end: Mapped[date | None] = mapped_column(Date, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # draft | pending_approval | approved | superseded | closed
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # суммарные плановые/утверждённые значения (пересчитываются сервисом)
    planned_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    approved_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class BudgetLine(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Статья бюджета (DATABASE.md раздел 16.3).

    `committed_amount`/`actual_amount`/`forecast_amount` — рассчитываемые значения
    (сервис агрегирует заказы/договоры/ФОТ, не копируя суммы). Ручная статья
    (`is_manual`) допускается только с указанным источником (`source_reference`)
    и проходит согласование (`approval_id`).
    """

    __tablename__ = "budget_lines"

    budget_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("budgets.id"))
    parent_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("budget_lines.id"), nullable=True
    )
    expense_category_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("expense_categories.id"), nullable=True
    )
    cost_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # material | labor | machine | subcontract | overhead | other
    category: Mapped[str] = mapped_column(String(32), default="other")
    description: Mapped[str] = mapped_column(String(500))
    planned_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    approved_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    committed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    actual_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    forecast_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    # estimate | manual
    source: Mapped[str] = mapped_column(String(16), default="estimate")
    is_manual: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # обязательное основание для ручной статьи (расход вне сметы)
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # draft | pending_approval | approved | rejected — статус ручной статьи
    status: Mapped[str] = mapped_column(String(16), default="approved")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


class FinancialCommitment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Ручное финансовое обязательство — «решение» (DATABASE.md раздел 16.4).

    Обязательства по заказам (`purchase_orders`) и договорам (`contracts`)
    агрегируются сервисом финансовой сводки напрямую (без дублирования); эта
    таблица хранит только ручные обязательства, не покрытые заказами/договорами
    (аренда, разовые решения и т. п.).
    """

    __tablename__ = "financial_commitments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    budget_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("budget_lines.id"), nullable=True
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    # manual | decision — источник ручного обязательства
    source_type: Mapped[str] = mapped_column(String(32), default="manual")
    source_reference: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str] = mapped_column(String(500))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # open | settled | cancelled
    status: Mapped[str] = mapped_column(String(16), default="open")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


# ------------------- Счета, заявки на оплату, платежи -------------------- #


class Invoice(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Счёт на оплату (DATABASE.md раздел 16.5).

    Формируется из договора/обязательства/заказа или вручную. Файл счёта —
    через `documents`. Сумма к оплате уменьшается по мере регистрации платежей
    (`paid_amount`), статус оплаты пересчитывается сервисом.
    """

    __tablename__ = "invoices"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id")
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("contracts.id"), nullable=True
    )
    commitment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("financial_commitments.id"), nullable=True
    )
    budget_line_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("budget_lines.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    invoice_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    invoice_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    paid_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    # draft | registered | cancelled — жизненный цикл счёта
    status: Mapped[str] = mapped_column(String(16), default="draft")
    # unpaid | partially_paid | paid — статус оплаты
    payment_status: Mapped[str] = mapped_column(String(16), default="unpaid")
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class PaymentRequest(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Заявка на оплату счёта и маршрут согласования (DATABASE.md раздел 16.6).

    Согласование — R3, крупная сумма — R4 + MFA. Система не проводит платёж:
    после согласования платёж фиксируется вручную (`payments`).
    """

    __tablename__ = "payment_requests"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("invoices.id"))
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    requested_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    planned_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    justification: Mapped[str | None] = mapped_column(Text, nullable=True)
    # pending | approved | rejected | paid | cancelled
    status: Mapped[str] = mapped_column(String(16), default="pending")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


class Payment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Отражение платежа (DATABASE.md раздел 16.7).

    Система не выполняет банковских операций (решение владельца): платёж
    фиксируется вручную либо импортируется из бухгалтерии. Идемпотентность
    ручного ввода — по `idempotency_key`.
    """

    __tablename__ = "payments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    invoice_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("invoices.id"), nullable=True
    )
    payment_request_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("payment_requests.id"), nullable=True
    )
    payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # outgoing | incoming
    payment_direction: Mapped[str] = mapped_column(String(16), default="outgoing")
    # manual | accounting_import — источник записи (не банковская операция)
    method: Mapped[str] = mapped_column(String(32), default="manual")
    external_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True
    )
    # recorded | reconciled | cancelled
    status: Mapped[str] = mapped_column(String(16), default="recorded")
    recorded_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
