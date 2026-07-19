"""Модуль «Проектирование и дизайн» (MVP).

Реализует ядро проектного/дизайн-контура (DATABASE.md разделы 18, 11, 12) с
переиспользованием существующих сущностей: проекты/объекты (`projects`/`sites`),
зоны (`project_locations`), чертежи и ТЗ (`documents`/`document_versions`/
`files`), задания разделам (`tasks`), согласования (`approvals`), аудит
(`audit_events`). Реальные ПДн и секреты не используются (D-011).

Справочники материалов и поставщиков в MVP минимальны, но со схемой, готовой к
расширению до полного каталога и интеграций со складом/закупками (JSON-атрибуты,
поля цен/остатков/сроков и внешних ссылок).
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


# ----------------- Справочник поставщиков и материалов ------------------- #


class Counterparty(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Контрагент (минимальная карточка, DATABASE.md раздел 11.1)."""

    __tablename__ = "counterparties"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    name: Mapped[str] = mapped_column(String(255))
    inn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    # supplier | customer | contractor | designer | other
    counterparty_type: Mapped[str] = mapped_column(String(32), default="supplier")
    status: Mapped[str] = mapped_column(String(32), default="active")


class Supplier(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Расширенные сведения о поставщике (DATABASE.md раздел 11.3, минимум)."""

    __tablename__ = "suppliers"

    counterparty_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("counterparties.id")
    )
    supplier_categories: Mapped[str | None] = mapped_column(String(255), nullable=True)
    regions: Mapped[str | None] = mapped_column(String(255), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rating: Mapped[Decimal | None] = mapped_column(Numeric(3, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class Material(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Каталог материалов (минимум; расширяется до полного каталога — раздел 33)."""

    __tablename__ = "materials"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    category: Mapped[str | None] = mapped_column(String(128), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), default="шт")
    # гибкие характеристики — задел под полный каталог (material_attributes)
    attributes_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class SupplierProduct(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Товар поставщика: цена, срок, наличие (DATABASE.md раздел 11.4).

    Поля цен/наличия/сроков и внешней ссылки — интерфейс для последующего
    подключения реальных каталогов и остатков поставщиков.
    """

    __tablename__ = "supplier_products"

    supplier_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("suppliers.id"))
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    supplier_sku: Mapped[str | None] = mapped_column(String(128), nullable=True)
    supplier_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    price_valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_quantity: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 3), nullable=True
    )
    # in_stock | on_order | out_of_stock | unknown
    availability_status: Mapped[str] = mapped_column(String(32), default="unknown")
    region: Mapped[str | None] = mapped_column(String(128), nullable=True)
    product_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    last_checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ---------------------- Архитектура и дизайн (§18) ----------------------- #


class DesignBrief(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Техническое задание/бриф на архитектурный/дизайн-проект (§18.1)."""

    __tablename__ = "design_briefs"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    title: Mapped[str] = mapped_column(String(255), default="Техническое задание")
    client_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    functional_requirements: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_preferences: Mapped[str | None] = mapped_column(Text, nullable=True)
    budget_range: Mapped[str | None] = mapped_column(String(128), nullable=True)
    target_completion_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    # draft | pending_approval | approved | rejected
    status: Mapped[str] = mapped_column(String(32), default="draft")
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )


class DesignConcept(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Концепция дизайна и её версия (§18.2). Презентация — через `files`."""

    __tablename__ = "design_concepts"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    prepared_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    presentation_file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )
    # draft | submitted | client_review | approved | rejected | superseded
    status: Mapped[str] = mapped_column(String(32), default="draft")
    client_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)


class DesignSpecification(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Спецификация мебели/освещения/отделки/оборудования (§18.3)."""

    __tablename__ = "design_specifications"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    concept_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("design_concepts.id"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_locations.id"), nullable=True
    )
    # furniture | lighting | finishing | equipment | other
    category: Mapped[str] = mapped_column(String(64), default="other")
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    supplier_product_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("supplier_products.id"), nullable=True
    )
    custom_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 3), default=0)
    unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    planned_unit_price: Mapped[Decimal | None] = mapped_column(
        Numeric(14, 2), nullable=True
    )
    approved_analog_allowed: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=false(), nullable=False
    )
    # draft | checked | approved | rejected
    status: Mapped[str] = mapped_column(String(32), default="draft")


class MarketAvailabilityCheck(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Проверка реализуемости проектного решения (§18.4).

    Заполняется сервисом/агентом (рекомендация, R0/R1). Поля наличия, цен и
    сроков — интерфейс для последующего подключения реальных источников.
    """

    __tablename__ = "market_availability_checks"

    design_specification_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("design_specifications.id")
    )
    checked_by_agent_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    checked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), default="demo")
    # available | limited | unavailable | unknown
    availability_status: Mapped[str] = mapped_column(String(32), default="unknown")
    supplier_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    minimum_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    maximum_price: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    lead_time_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    regional_delivery_possible: Mapped[bool | None] = mapped_column(
        Boolean, nullable=True
    )
    recommended_option: Mapped[str | None] = mapped_column(String(255), nullable=True)
    risk_notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class DesignIssue(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Реестр замечаний проектного/дизайн-контура (DATABASE.md раздел 17.2).

    Замечание заказчика/экспертизы/нормоконтроля превращается в задачу
    (`tasks`) с ответственным и сроком (WORKFLOWS §16.6) — связь через
    `linked_task_id`, без дублирования задач.
    """

    __tablename__ = "design_issues"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    discipline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_disciplines.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    # client | expertise | normcontrol | internal
    source: Mapped[str] = mapped_column(String(32), default="internal")
    title: Mapped[str] = mapped_column(String(500))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    # low | normal | high | critical
    severity: Mapped[str] = mapped_column(String(16), default="normal")
    # open | in_progress | resolved | closed | cancelled
    status: Mapped[str] = mapped_column(String(32), default="open")
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    linked_task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
