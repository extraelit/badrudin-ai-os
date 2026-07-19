"""Модуль «Сметы и ценообразование» (MVP).

Переиспользует существующие сущности (без дублирования): проекты/объекты/зоны
(`projects`/`sites`/`project_locations`), разделы (`project_disciplines`), ТЗ и
спецификации (`design_briefs`/`design_specifications`), материалы и цены
поставщиков (`materials`/`supplier_products`), документы и версии
(`documents`/`document_versions`), согласования (`approvals`) и аудит
(`audit_events`). Все денежные расчёты — Decimal.

Состав: справочник единиц (`units_of_measure`), справочник расценок
(`rate_items`, ручной ввод; интерфейс адаптеров импорта — в сервисе), настройки
ценообразования организации (`pricing_settings`, настраиваемый порог R3/R4),
сметы (`estimates`) с версиями/статусами, позиции (`estimate_positions`) с
раздельными материалами/трудом/машинами, журнал изменений (`estimate_changes`)
и коммерческие предложения (`commercial_offers`).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class UnitOfMeasure(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Справочник единиц измерения."""

    __tablename__ = "units_of_measure"

    organization_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("organizations.id"), nullable=True
    )
    code: Mapped[str] = mapped_column(String(32))
    name: Mapped[str] = mapped_column(String(64))
    # length | area | volume | mass | piece | time | other
    category: Mapped[str] = mapped_column(String(16), default="other")
    status: Mapped[str] = mapped_column(String(16), default="active")


class RateItem(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Справочник расценок (ручной ввод). Расширяется адаптерами импорта.

    Источник (`source`) допускает будущий импорт ГЭСН/ФЕР/ТЕР через адаптеры
    (в MVP — только собственные расценки; сами нормативные базы прикрепляются как
    документы).
    """

    __tablename__ = "rate_items"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    code: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(500))
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    material_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    labor_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    machine_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    # own | gesn | fer | ter | import
    source: Mapped[str] = mapped_column(String(16), default="own")
    attributes_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="active")


class PricingSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Настройки ценообразования организации (пороги и значения по умолчанию).

    Порог отнесения выплаты/предложения к R4 задаётся на уровне организации, а не
    жёстко в коде (решение владельца).
    """

    __tablename__ = "pricing_settings"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id"), unique=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    default_vat_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=20)
    default_overhead_percent: Mapped[Decimal] = mapped_column(
        Numeric(6, 3), default=0
    )
    default_profit_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    # правило округления денежных сумм (например, "0.01")
    rounding: Mapped[str] = mapped_column(String(8), default="0.01")
    # порог крупной суммы для КП: >= порога → R4 (иначе R3)
    offer_r4_amount_threshold: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=1000000
    )
    # массовое КП (много позиций) → R4
    offer_r4_positions_threshold: Mapped[int] = mapped_column(Integer, default=100)


class Estimate(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Смета: локальная, объектная или сводная. Версионируется и согласуется."""

    __tablename__ = "estimates"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    # договор (contracts не в MVP-модели) — ссылка без FK
    contract_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    discipline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_disciplines.id"), nullable=True
    )
    design_brief_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("design_briefs.id"), nullable=True
    )
    document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    # local | object | summary
    estimate_type: Mapped[str] = mapped_column(String(16), default="local")
    parent_estimate_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimates.id"), nullable=True
    )
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(500))
    version: Mapped[int] = mapped_column(Integer, default=1)
    # draft | review | approved | superseded
    status: Mapped[str] = mapped_column(String(16), default="draft")
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # коэффициент индексации к прямым затратам
    base_index: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=1)
    vat_rate: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=20)
    overhead_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    profit_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    rounding: Mapped[str] = mapped_column(String(8), default="0.01")
    # раздельные составляющие и итоги (рассчитываются сервисом)
    material_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    labor_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    machine_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    direct_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    overhead_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    profit_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    subtotal: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    vat_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    grand_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    approved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    approved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EstimatePosition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Позиция сметы с раздельными материалами, трудом и машинами."""

    __tablename__ = "estimate_positions"

    estimate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("estimates.id"))
    parent_position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("estimate_positions.id"), nullable=True
    )
    rate_item_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("rate_items.id"), nullable=True
    )
    material_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("materials.id"), nullable=True
    )
    design_specification_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("design_specifications.id"), nullable=True
    )
    discipline_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_disciplines.id"), nullable=True
    )
    location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_locations.id"), nullable=True
    )
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(500))
    work_type: Mapped[str | None] = mapped_column(String(128), nullable=True)
    position_no: Mapped[int] = mapped_column(Integer, default=0)
    quantity: Mapped[Decimal] = mapped_column(Numeric(14, 3), default=0)
    material_unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    labor_unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    machine_unit_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    coefficient: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=1)
    overhead_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    profit_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    # рассчитываемые значения позиции
    position_direct: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    position_overhead: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    position_profit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    position_total: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EstimateChange(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Журнал изменений сметы: причины изменения цены и объёма (change order)."""

    __tablename__ = "estimate_changes"

    estimate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("estimates.id"))
    position_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    # price | volume | scope | new_version | index | rate
    change_type: Mapped[str] = mapped_column(String(16))
    old_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    new_value_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    amount_delta: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    reason: Mapped[str] = mapped_column(Text)
    approval_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(16), default="recorded")
    changed_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)


class CommercialOffer(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Коммерческое предложение: наценка к смете, итоговая цена заказчику."""

    __tablename__ = "commercial_offers"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    estimate_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("estimates.id"))
    number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    markup_percent: Mapped[Decimal] = mapped_column(Numeric(6, 3), default=0)
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    offer_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=0)
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    # draft | pending_approval | approved | sent | rejected
    status: Mapped[str] = mapped_column(String(16), default="draft")
    risk_level: Mapped[str] = mapped_column(String(2), default="R0")
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("approvals.id"), nullable=True
    )
    valid_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
