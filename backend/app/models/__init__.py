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
from app.models.access_grant import ProjectAccess
from app.models.agent import AgentRun, AIAgent
from app.models.audit import AuditEvent
from app.models.content import (
    DailyReport,
    Document,
    DocumentVersion,
    File,
    Notification,
)
from app.models.project import (
    Project,
    ProjectDiscipline,
    ProjectLocation,
    ProjectMember,
    ProjectMilestone,
    Site,
)
from app.models.design import (
    Counterparty,
    DesignBrief,
    DesignConcept,
    DesignIssue,
    DesignSpecification,
    MarketAvailabilityCheck,
    Material,
    Supplier,
    SupplierProduct,
)
from app.models.personnel import (
    DailyReportHeadcount,
    DailyReportIssue,
    ForemanJournal,
    PayrollDraft,
    PayrollLine,
    SafetyClearance,
    SiteWorkerAssignment,
    WorkPermit,
    WorkShift,
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
    "AIAgent",
    "AgentRun",
    "AuditEvent",
    "ProjectAccess",
    "SiteWorkerAssignment",
    "WorkShift",
    "PayrollDraft",
    "PayrollLine",
    "SafetyClearance",
    "WorkPermit",
    "ForemanJournal",
    "DailyReportHeadcount",
    "DailyReportIssue",
    "ProjectMilestone",
    "ProjectDiscipline",
    "Counterparty",
    "Supplier",
    "Material",
    "SupplierProduct",
    "DesignBrief",
    "DesignConcept",
    "DesignSpecification",
    "MarketAvailabilityCheck",
    "DesignIssue",
]
