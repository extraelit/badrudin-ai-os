"""Проекты, строительные объекты, участники и зоны (T-1.B4).

Соответствует DATABASE.md раздел 6 и канону D-009: объект — первоклассная
сущность `sites`, связанная с `projects`; `project_locations` — зоны внутри
объекта.
"""

from __future__ import annotations

import uuid
from datetime import date

from sqlalchemy import Date, ForeignKey, Integer, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class Project(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    parent_project_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("projects.id"), nullable=True
    )
    # construction | linear_infrastructure | design_engineering | survey |
    # interior_design | architecture | public_space | maintenance | internal
    project_type: Mapped[str] = mapped_column(String(32), default="construction")
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    customer_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")
    priority: Mapped[str] = mapped_column(String(16), default="normal")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    contract_amount: Mapped[float | None] = mapped_column(
        Numeric(18, 2), nullable=True
    )
    currency: Mapped[str] = mapped_column(String(3), default="RUB")
    completion_percent: Mapped[int] = mapped_column(Integer, default=0)
    confidentiality_level: Mapped[str] = mapped_column(String(32), default="internal")


class Site(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "sites"

    organization_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("organizations.id")
    )
    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    latitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitude: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    site_manager_id: Mapped[uuid.UUID | None] = mapped_column(Uuid, nullable=True)
    responsible_foreman_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid, nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="active")
    start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    planned_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    confidentiality_level: Mapped[str] = mapped_column(String(32), default="internal")


class ProjectMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_members"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    employee_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("employees.id"))
    project_role: Mapped[str] = mapped_column(String(64))
    responsibility: Mapped[str | None] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active")


class ProjectLocation(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "project_locations"

    project_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("projects.id"))
    site_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("sites.id"), nullable=True
    )
    parent_location_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("project_locations.id"), nullable=True
    )
    location_type: Mapped[str] = mapped_column(String(64))
    name: Mapped[str] = mapped_column(String(255))
    code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    description: Mapped[str | None] = mapped_column(String(1000), nullable=True)
