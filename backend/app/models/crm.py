"""Модуль «Ядро CRM» (MVP).

Продажный и клиентский контур: справочники источников лидов и причин проигрыша,
настраиваемая воронка, лиды, сделки, контактные лица, единый центр коммуникаций,
договоры и цели менеджеров (план-факт). Настройки крупной сделки — на уровне
организации (`crm_settings`).

Переиспользование существующих сущностей (без дублирования):
- заказчики/клиенты → `counterparties` (DATABASE.md раздел 11.1);
- коммерческие предложения → `commercial_offers` (сметный модуль);
- задачи менеджеров → `tasks` (сообщение → задача);
- проекты и договоры-объекты → `projects` (`projects.customer_id` → `counterparties`);
- документы и файлы → `documents`/`files`;
- согласования (R2/R3/R4) → `approvals`/`approval_steps`;
- ответственные сотрудники → `employees`;
- аудит значимых действий → `audit_events`.

Цепочка: lead → deal → commercial_offer → contract → project (проект создаётся
только после выигранной сделки и утверждённого/подписанного договора).

ПДн контактных лиц — только тестовые (D-011). Просмотр телефонов и e-mail
ограничивается правами; для пользователей без полного доступа данные маскируются
на уровне сервиса.
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


# ------------------------------ Настройки ------------------------------- #


class CrmSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Настройки CRM организации: порог крупной сделки (R4) и значения по умолчанию.

    Порог отнесения сделки/договора к R4 задаётся владельцем на уровне
    организации, а не жёстко в коде (решение владельца). Значение по умолчанию —
    10 000 000 ₽.
    """

    __tablename__ = "crm_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), unique=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # порог крупной сделки/договора: >= порога → R4 + MFA (иначе R3)
    deal_r4_amount_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=10000000
    )


# ------------------------------ Справочники ----------------------------- #


class LeadSource(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Источник лида (сайт, звонок, рекомендация, выставка и т. п.)."""

    __tablename__ = "lead_sources"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")


class DealLossReason(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Справочник причин проигрыша сделки (для аналитики продаж)."""

    __tablename__ = "deal_loss_reasons"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(16), default="active")


class PipelineStage(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Настраиваемый этап воронки продаж (порядок, вероятность, признаки исхода)."""

    __tablename__ = "pipeline_stages"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    # вероятность закрытия на этом этапе, %
    probability_percent: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    is_won: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    is_lost: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    status: Mapped[str] = mapped_column(String(16), default="active")


# --------------------- Контактные лица (§11.2 + ПДн) --------------------- #


class CounterpartyContact(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Контактное лицо контрагента (DATABASE.md раздел 11.2).

    Телефон и e-mail — ПДн: их просмотр ограничивается правами (`crm.contact.pii`),
    для остальных данные маскируются сервисом. Хранится согласие на обработку и
    его дата.
    """

    __tablename__ = "counterparty_contacts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id")
    )
    full_name: Mapped[str] = mapped_column(String(255))
    position: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    messenger: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_primary: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # согласие на обработку персональных данных
    consent_given: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    consent_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


# ------------------------------- Лиды ----------------------------------- #


class Lead(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Лид — входящий интерес потенциального клиента (до квалификации).

    После квалификации связывается с контрагентом (`counterparty_id`) и может быть
    сконвертирован в сделку (`converted_deal_id`).
    """

    __tablename__ = "leads"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    lead_source_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("lead_sources.id"), nullable=True
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # контактные данные лида (ПДн; маскируются по правам)
    contact_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    company_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    estimated_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # new | qualified | converted | rejected
    status: Mapped[str] = mapped_column(String(16), default="new")
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    converted_deal_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    qualified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rejected_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ------------------------------ Сделки ---------------------------------- #


class Deal(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Сделка: движение по воронке, сумма, исход, связи с КП/договором/проектом.

    Коммерческое предложение не дублируется — сделка ссылается на существующее
    `commercial_offers`. Проект создаётся только после выигрыша и
    утверждённого/подписанного договора.
    """

    __tablename__ = "deals"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id")
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id"), nullable=True
    )
    pipeline_stage_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("pipeline_stages.id"), nullable=True
    )
    commercial_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commercial_offers.id"), nullable=True
    )
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # open | won | lost
    status: Mapped[str] = mapped_column(String(16), default="open")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    expected_close_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    loss_reason_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deal_loss_reasons.id"), nullable=True
    )
    loss_comment: Mapped[str | None] = mapped_column(String(500), nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


class DealStageHistory(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """История перемещений сделки по этапам воронки (для аналитики конверсии)."""

    __tablename__ = "deal_stage_history"

    deal_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("deals.id"))
    from_stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    to_stage_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    note: Mapped[str | None] = mapped_column(String(500), nullable=True)


# ------------------- Единый центр коммуникаций (§10.4) ------------------- #


class Communication(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Коммуникация: письмо, звонок, встреча или сообщение (DATABASE.md раздел 10.4).

    Единая история взаимодействий с привязкой к контрагенту/контакту/лиду/сделке/
    проекту. Сообщение может порождать задачу (`tasks`) — связь через
    `linked_task_id`, без дублирования задач.
    """

    __tablename__ = "communications"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    counterparty_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparties.id"), nullable=True
    )
    contact_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("counterparty_contacts.id"), nullable=True
    )
    lead_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("leads.id"), nullable=True
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deals.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    # email | whatsapp_business | telegram | web_form | internal_chat | manual |
    # call | meeting
    channel: Mapped[str] = mapped_column(String(32), default="manual")
    # inbound | outbound | internal
    direction: Mapped[str] = mapped_column(String(16), default="outbound")
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    classification: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # new | processed | task_created | ignored
    processing_status: Mapped[str] = mapped_column(String(32), default="new")
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    linked_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )


# ------------------------------ Договоры (§16.1) ------------------------- #


class Contract(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Договор с контрагентом (DATABASE.md раздел 16.1).

    Связывает контрагента, сделку, коммерческое предложение и проект. Утверждение
    и подписание — R3 (крупный — R4 + MFA). Файл договора хранится через
    `documents`.
    """

    __tablename__ = "contracts"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id")
    )
    deal_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("deals.id"), nullable=True
    )
    commercial_offer_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("commercial_offers.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    # contract | supplementary_agreement | annex | framework
    contract_type: Mapped[str] = mapped_column(String(32), default="contract")
    number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subject: Mapped[str | None] = mapped_column(Text, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    payment_terms: Mapped[str | None] = mapped_column(Text, nullable=True)
    signed_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # draft | pending_approval | approved | signed | active | closed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="draft")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


# ---------------- Цели менеджеров (план-факт продаж) -------------------- #


class SalesTarget(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Цель менеджера по продажам на период (для план-факта).

    Небольшая обоснованная сущность: факт берётся из выигранных сделок
    (`deals`), без дублирования; здесь хранится только план (цель).
    """

    __tablename__ = "sales_targets"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    period_year: Mapped[int] = mapped_column(Integer)
    period_month: Mapped[int | None] = mapped_column(Integer, nullable=True)
    target_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    target_deals_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)
