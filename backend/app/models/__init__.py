"""Реестр моделей данных.

Импорт модулей моделей здесь обеспечивает регистрацию таблиц в
`Base.metadata` (используется Alembic для миграций). Модели добавляются
задачами блока 1.B по мере реализации.
"""

from app.db.base import Base
from app.models.organization import (
    Department,
    Employee,
    Organization,
    Position,
)
from app.models.content import (
    DailyReport,
    Document,
    DocumentVersion,
    File,
    Notification,
)
from app.models.project import (
    Project,
    ProjectLocation,
    ProjectMember,
    Site,
)
from app.models.rbac import Permission, Role, RolePermission, UserRole
from app.models.task import (
    Approval,
    ApprovalStep,
    Task,
    TaskAssignment,
    TaskEvidence,
    TaskUpdate,
)
from app.models.user import User

__all__ = [
    "Base",
    "Organization",
    "Department",
    "Position",
    "Employee",
    "User",
    "Role",
    "Permission",
    "UserRole",
    "RolePermission",
    "Project",
    "Site",
    "ProjectMember",
    "ProjectLocation",
    "Task",
    "TaskAssignment",
    "TaskUpdate",
    "TaskEvidence",
    "Approval",
    "ApprovalStep",
    "File",
    "Document",
    "DocumentVersion",
    "DailyReport",
    "Notification",
]
