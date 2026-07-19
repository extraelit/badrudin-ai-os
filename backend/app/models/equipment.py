"""Модуль «Техника, транспорт и инструмент» (ROADMAP этап 10, CLAUDE.md §17).

Каноническая модель DATABASE.md разделы 15 и 33.15–33.18 (решение D-009): единая
сущность `equipment` для техники, транспорта и оборудования (транспорт — это
`asset_type`, отдельная `vehicles` не вводится); инструмент — `tools`. Полный
жизненный цикл: реестр → назначение на объект/ответственного → эксплуатация
(моточасы/пробег/простой) → топливо → техобслуживание и ремонт → осмотры →
списание; инструмент — выдача и возврат с фиксацией состояния. Файлы (фото,
документы, сроки) — через существующие `files`/`documents` (D-008), ссылки
хранятся идентификаторами. Денежные суммы — Numeric; количества — Numeric.
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
    Numeric,
    String,
    Text,
    Uuid,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


# ------------------------- Техника и оборудование ------------------------ #


class Equipment(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Единица техники/транспорта/оборудования (§33.16)."""

    __tablename__ = "equipment"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    asset_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    # автомобиль | экскаватор | кран | сварочный агрегат | генератор | насос |
    # компрессор | иное оборудование (транспорт — категория equipment)
    asset_type: Mapped[str] = mapped_column(String(64), default="equipment")
    # собственность | аренда | лизинг | заказчик | субподрядчик
    ownership_type: Mapped[str] = mapped_column(String(32), default="owned")
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    registration_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    vin_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manufacture_year: Mapped[int | None] = mapped_column(Numeric(4, 0), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    # available | assigned | in_use | under_inspection | under_repair | idle |
    # written_off
    current_status: Mapped[str] = mapped_column(String(24), default="available")
    current_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    current_site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    operator_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    odometer_value: Mapped[Decimal] = mapped_column(Numeric(14, 1), default=0)
    engine_hours: Mapped[Decimal] = mapped_column(Numeric(12, 1), default=0)
    fuel_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fuel_norm: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    last_service_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_service_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_inspection_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_inspection_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    insurance_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    registration_document_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)


class EquipmentAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Назначение техники на объект/проект и ответственного (§33.16)."""

    __tablename__ = "equipment_assignments"

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    assigned_from: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    assigned_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    operator_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    task_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("tasks.id"), nullable=True
    )
    # active | returned | cancelled
    status: Mapped[str] = mapped_column(String(16), default="active")
    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)


class EquipmentUsageLog(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Эксплуатация техники за смену: моточасы/пробег/простой/топливо (§33.16)."""

    __tablename__ = "equipment_usage_logs"

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    usage_date: Mapped[date] = mapped_column(Date)
    operator_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    start_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    end_time: Mapped[str | None] = mapped_column(String(5), nullable=True)
    engine_hours_start: Mapped[Decimal | None] = mapped_column(Numeric(12, 1), nullable=True)
    engine_hours_end: Mapped[Decimal | None] = mapped_column(Numeric(12, 1), nullable=True)
    odometer_start: Mapped[Decimal | None] = mapped_column(Numeric(14, 1), nullable=True)
    odometer_end: Mapped[Decimal | None] = mapped_column(Numeric(14, 1), nullable=True)
    fuel_issued: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    fuel_consumed: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    work_description: Mapped[str | None] = mapped_column(String(500), nullable=True)
    downtime_hours: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    downtime_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)
    photo_file_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)


class EquipmentInspection(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Осмотры и поверки техники (§15.2): предсменные, периодические, гос."""

    __tablename__ = "equipment_inspections"

    equipment_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("equipment.id"))
    # pre_shift | periodic | state
    inspection_type: Mapped[str] = mapped_column(String(32), default="pre_shift")
    inspector_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    inspected_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    # passed | failed
    result: Mapped[str] = mapped_column(String(16), default="passed")
    defects: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_allowed: Mapped[bool] = mapped_column(Boolean, default=True)
    next_inspection_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    file_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("files.id"), nullable=True
    )


class MaintenanceOrder(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Заказ на техобслуживание/ремонт техники или инструмента (§33.17)."""

    __tablename__ = "maintenance_orders"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    maintenance_order_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # equipment | tool
    asset_type: Mapped[str] = mapped_column(String(16), default="equipment")
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid)
    # planned | repair | inspection | seasonal
    maintenance_type: Mapped[str] = mapped_column(String(32), default="planned")
    problem_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    reported_by: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    reported_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    planned_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    planned_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_start_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    actual_end_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    service_provider_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("suppliers.id"), nullable=True
    )
    responsible_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    # open | in_progress | completed | cancelled
    status: Mapped[str] = mapped_column(String(16), default="open")
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    actual_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    downtime_hours: Mapped[Decimal] = mapped_column(Numeric(8, 2), default=0)
    supporting_document_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)


class FuelTransaction(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Учёт топлива и ГСМ (§33.18). Система не проводит платежей."""

    __tablename__ = "fuel_transactions"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    transaction_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # receipt | issue | return | write_off | adjustment
    transaction_type: Mapped[str] = mapped_column(String(16), default="issue")
    fuel_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(12, 2), default=0)
    unit_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("units_of_measure.id"), nullable=True
    )
    unit_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    total_amount: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True
    )
    equipment_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("equipment.id"), nullable=True
    )
    employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    odometer_value: Mapped[Decimal | None] = mapped_column(Numeric(14, 1), nullable=True)
    engine_hours: Mapped[Decimal | None] = mapped_column(Numeric(12, 1), nullable=True)
    receipt_document_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("documents.id"), nullable=True
    )
    occurred_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )


# ------------------------------ Инструмент ------------------------------- #


class Tool(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    """Единица инструмента (§33.15)."""

    __tablename__ = "tools"

    organization_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("organizations.id"))
    inventory_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    serial_number: Mapped[str | None] = mapped_column(String(128), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    tool_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    manufacturer: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    purchase_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    purchase_cost: Mapped[Decimal | None] = mapped_column(Numeric(14, 2), nullable=True)
    warranty_until: Mapped[date | None] = mapped_column(Date, nullable=True)
    # available | reserved | issued | in_use | under_inspection | under_repair |
    # lost | damaged | written_off
    current_status: Mapped[str] = mapped_column(String(24), default="available")
    current_warehouse_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("warehouses.id"), nullable=True
    )
    current_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("employees.id"), nullable=True
    )
    current_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    # ok | worn | damaged
    condition_status: Mapped[str] = mapped_column(String(16), default="ok")
    last_inspection_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_inspection_at: Mapped[date | None] = mapped_column(Date, nullable=True)


class ToolAssignment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Выдача и возврат инструмента (§33.15)."""

    __tablename__ = "tool_assignments"

    tool_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tools.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    issued_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    expected_return_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    returned_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    condition_at_issue: Mapped[str | None] = mapped_column(String(16), nullable=True)
    condition_at_return: Mapped[str | None] = mapped_column(String(16), nullable=True)
    issue_photo_file_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    return_photo_file_ids: Mapped[list | None] = mapped_column(JSON, nullable=True)
    # issued | returned | overdue | lost
    status: Mapped[str] = mapped_column(String(16), default="issued")
    confirmed_by_employee_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
