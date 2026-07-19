"""API модуля «Управленческие сводки руководителю».

Backend — единственная точка доступа. Только чтение: утренняя и вечерняя сводка
по организации на реальных данных. RBAC: `management.view` (управленческая роль).
ABAC: задачи ограничены доступными проектами пользователя; операционные сводки —
в пределах организации. Ничего не изменяет; агрегирует существующие модули.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import Employee, User
from app.schemas.digest import ApprovalRefOut, DigestOut, TaskRefOut
from app.services import digest as svc

router = APIRouter(prefix="/management", tags=["management"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


@router.get("/digest", response_model=DigestOut)
def digest(
    kind: str = Query("morning", pattern="^(morning|evening)$"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("management.view")),
) -> DigestOut:
    d = svc.build_digest(db, user, _org(db, user), kind=kind)
    return DigestOut(
        kind=d.kind, generated_at=d.generated_at, period_label=d.period_label,
        projects_active=d.projects_active, tasks=d.tasks,
        approvals_pending=d.approvals_pending,
        approvals=[
            ApprovalRefOut(id=a.id, entity_type=a.entity_type,
                           approval_type=a.approval_type, entity_id=a.entity_id)
            for a in d.approvals
        ],
        finance=d.finance, procurement=d.procurement, warehouse=d.warehouse,
        field_reports=d.field_reports, accountable=d.accountable, risks=d.risks,
        top_overdue=[
            TaskRefOut(id=t.id, title=t.title, status=t.status, risk_level=t.risk_level,
                       due_at=t.due_at, escalation_level=t.escalation_level)
            for t in d.top_overdue
        ],
    )
