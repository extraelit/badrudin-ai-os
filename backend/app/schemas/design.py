"""Pydantic-схемы модуля «Проектирование и дизайн»."""

from __future__ import annotations

import uuid
from datetime import date

from pydantic import BaseModel, Field


# ------------------------------ Разделы ---------------------------------- #


class DisciplineIn(BaseModel):
    name: str
    code: str | None = None
    discipline_type: str = "other"
    responsible_employee_id: uuid.UUID | None = None
    due_date: date | None = None
    completion_percent: int = Field(0, ge=0, le=100)
    milestone_id: uuid.UUID | None = None


class DisciplineOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    code: str | None
    name: str
    discipline_type: str
    responsible_employee_id: uuid.UUID | None
    due_date: date | None
    completion_percent: int
    gip_status: str
    status: str


# ------------------------------- Бриф/ТЗ --------------------------------- #


class BriefIn(BaseModel):
    title: str = "Техническое задание"
    client_requirements: str | None = None
    functional_requirements: str | None = None
    style_preferences: str | None = None
    budget_range: str | None = None
    target_completion_date: date | None = None


class BriefOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    title: str
    client_requirements: str | None
    functional_requirements: str | None
    style_preferences: str | None
    budget_range: str | None
    target_completion_date: date | None
    status: str


# ------------------------------ Концепции -------------------------------- #


class ConceptIn(BaseModel):
    name: str
    description: str | None = None


class ConceptOut(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    version: int
    status: str
    client_feedback: str | None


# ----------------------------- Спецификации ------------------------------ #


class SpecificationIn(BaseModel):
    category: str = "other"
    material_id: uuid.UUID | None = None
    supplier_product_id: uuid.UUID | None = None
    custom_description: str | None = None
    quantity: float = Field(0, ge=0)
    unit: str | None = None
    planned_unit_price: float | None = None
    concept_id: uuid.UUID | None = None
    location_id: uuid.UUID | None = None


class SpecificationOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    category: str
    material_id: uuid.UUID | None
    supplier_product_id: uuid.UUID | None
    custom_description: str | None
    quantity: str
    unit: str | None
    planned_unit_price: str | None
    approved_analog_allowed: bool
    status: str


class RealizabilityOut(BaseModel):
    id: uuid.UUID
    design_specification_id: uuid.UUID
    availability_status: str
    supplier_count: int | None
    minimum_price: str | None
    maximum_price: str | None
    lead_time_days: int | None
    regional_delivery_possible: bool | None
    recommended_option: str | None
    risk_notes: str | None
    source: str


# ------------------------------ Замечания -------------------------------- #


class IssueIn(BaseModel):
    title: str
    description: str | None = None
    source: str = "internal"
    severity: str = "normal"
    due_date: date | None = None
    discipline_id: uuid.UUID | None = None
    document_id: uuid.UUID | None = None
    responsible_employee_id: uuid.UUID | None = None
    create_task: bool = True


class IssueOut(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    source: str
    title: str
    severity: str
    status: str
    due_date: date | None
    responsible_employee_id: uuid.UUID | None
    linked_task_id: uuid.UUID | None


# --------------------------- Выпуск документации ------------------------- #


class ReleaseRequestIn(BaseModel):
    document_id: uuid.UUID


class ReleaseDecisionIn(BaseModel):
    approval_id: uuid.UUID
    decision: str = Field(pattern="^(approved|rejected)$")
    comment: str | None = None


class AnnulIn(BaseModel):
    reason: str
    mfa_code: str | None = None


# ------------------------------- Каталог --------------------------------- #


class SupplierOut(BaseModel):
    id: uuid.UUID
    name: str
    supplier_categories: str | None
    regions: str | None
    lead_time_days: int | None
    rating: str | None
    status: str


class MaterialOut(BaseModel):
    id: uuid.UUID
    code: str | None
    name: str
    category: str | None
    unit: str
    status: str


# ------------------------------- Сводка ГИП ------------------------------ #


class ProjectDesignOverview(BaseModel):
    project_id: uuid.UUID
    disciplines_total: int
    disciplines_issued: int
    avg_completion: int
    brief_status: str | None
    concepts_total: int
    specifications_total: int
    issues_open: int
    issues_critical: int
