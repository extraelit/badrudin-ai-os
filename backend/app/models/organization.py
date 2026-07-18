"""Организации, подразделения, должности и сотрудники (T-1.B2).

Соответствует DATABASE.md раздел 4. Имена сущностей — по канону D-009.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "organizations"

    legal_name: Mapped[str] = mapped_column(String(255))
    short_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    inn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    kpp: Mapped[str | None] = mapped_column(String(20), nullable=True)
    ogrn: Mapped[str | None] = mapped_column(String(20), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Europe/Moscow")
    base_currency: Mapped[str] = mapped_column(String(3), default="RUB")
    status: Mapped[str] = mapped_column(String(32), default="active")


class Department(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "departments"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    parent_department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # ответственный сотрудник указывается без FK во избежание циклической ссылки
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active")


class Position(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "positions"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    approval_level: Mapped[int] = mapped_column(default=0)


class Employee(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "employees"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    department_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("departments.id"), nullable=True
    )
    position_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("positions.id"), nullable=True
    )
    manager_employee_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    full_name: Mapped[str] = mapped_column(String(255))
    work_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    work_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # staff | contractor | consultant | external_specialist
    employment_type: Mapped[str] = mapped_column(String(32), default="staff")
    hire_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    dismissal_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    personnel_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
