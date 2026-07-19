"""Pydantic-схемы модуля «Техника, транспорт и инструмент»."""

from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import BaseModel, Field


# ------------------------------ Техника ---------------------------------- #


class EquipmentIn(BaseModel):
    name: str
    asset_type: str = "equipment"
    ownership_type: str = "owned"
    asset_number: str | None = None
    manufacturer: str | None = None
    model: str | None = None
    serial_number: str | None = None
    registration_number: str | None = None
    fuel_type: str | None = None
    next_service_at: date | None = None
    next_inspection_at: date | None = None


class EquipmentOut(BaseModel):
    id: uuid.UUID
    asset_number: str | None
    name: str
    asset_type: str
    ownership_type: str
    current_status: str
    current_project_id: uuid.UUID | None
    responsible_employee_id: uuid.UUID | None
    odometer_value: str
    engine_hours: str
    fuel_type: str | None
    next_service_at: date | None
    next_inspection_at: date | None


class AssignIn(BaseModel):
    project_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    responsible_employee_id: uuid.UUID | None = None
    operator_employee_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    assigned_until: datetime | None = None
    notes: str | None = None


class AssignmentOut(BaseModel):
    id: uuid.UUID
    equipment_id: uuid.UUID
    project_id: uuid.UUID | None
    status: str
    responsible_employee_id: uuid.UUID | None


class UsageIn(BaseModel):
    usage_date: date
    engine_hours_end: float | None = None
    odometer_end: float | None = None
    engine_hours_start: float | None = None
    odometer_start: float | None = None
    fuel_issued: float = Field(0, ge=0)
    fuel_consumed: float = Field(0, ge=0)
    downtime_hours: float = Field(0, ge=0)
    downtime_reason: str | None = None
    operator_employee_id: uuid.UUID | None = None
    work_description: str | None = None


class UsageOut(BaseModel):
    id: uuid.UUID
    equipment_id: uuid.UUID
    usage_date: date
    engine_hours_end: str | None
    odometer_end: str | None
    downtime_hours: str


class InspectionIn(BaseModel):
    inspection_type: str = "pre_shift"
    result: str = "passed"
    operation_allowed: bool = True
    defects: str | None = None
    inspector_employee_id: uuid.UUID | None = None
    next_inspection_at: date | None = None


class InspectionOut(BaseModel):
    id: uuid.UUID
    inspection_type: str
    result: str
    operation_allowed: bool


# --------------------- Техобслуживание и ремонт -------------------------- #


class MaintenanceIn(BaseModel):
    asset_type: str = Field("equipment", pattern="^(equipment|tool)$")
    asset_id: uuid.UUID
    maintenance_type: str = "planned"
    problem_description: str | None = None
    priority: str = "normal"
    planned_start_at: datetime | None = None
    estimated_cost: float | None = None
    responsible_employee_id: uuid.UUID | None = None
    number: str | None = None


class MaintenanceCompleteIn(BaseModel):
    actual_cost: float | None = None
    downtime_hours: float = Field(0, ge=0)


class MaintenanceOut(BaseModel):
    id: uuid.UUID
    asset_type: str
    asset_id: uuid.UUID
    maintenance_type: str
    status: str
    priority: str
    actual_cost: str | None


# ------------------------------ Топливо ---------------------------------- #


class FuelIn(BaseModel):
    transaction_type: str = Field("issue", pattern="^(receipt|issue|return|write_off|adjustment)$")
    fuel_type: str | None = None
    quantity: float = Field(gt=0)
    equipment_id: uuid.UUID | None = None
    unit_price: float | None = None
    project_id: uuid.UUID | None = None
    odometer_value: float | None = None
    engine_hours: float | None = None
    number: str | None = None


class FuelOut(BaseModel):
    id: uuid.UUID
    transaction_type: str
    fuel_type: str | None
    quantity: str
    total_amount: str | None
    equipment_id: uuid.UUID | None


# ------------------------------ Инструмент ------------------------------- #


class ToolIn(BaseModel):
    name: str
    tool_type: str | None = None
    inventory_number: str | None = None
    serial_number: str | None = None
    manufacturer: str | None = None
    model: str | None = None


class ToolOut(BaseModel):
    id: uuid.UUID
    inventory_number: str | None
    name: str
    tool_type: str | None
    current_status: str
    condition_status: str
    current_employee_id: uuid.UUID | None


class ToolIssueIn(BaseModel):
    employee_id: uuid.UUID
    project_id: uuid.UUID | None = None
    site_id: uuid.UUID | None = None
    expected_return_at: datetime | None = None
    condition_at_issue: str | None = None


class ToolReturnIn(BaseModel):
    condition_at_return: str | None = None


class ToolAssignmentOut(BaseModel):
    id: uuid.UUID
    tool_id: uuid.UUID
    employee_id: uuid.UUID
    status: str


# ------------------------------- Сводка ---------------------------------- #


class EquipmentSummaryOut(BaseModel):
    equipment_total: int
    equipment_available: int
    equipment_assigned: int
    equipment_under_repair: int
    maintenance_open: int
    service_due: int
    tools_total: int
    tools_issued: int
