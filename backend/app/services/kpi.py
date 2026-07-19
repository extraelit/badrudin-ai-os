"""Бизнес-логика модуля «KPI и независимый аудит» (ROADMAP этап 15, §20).

KPI вычисляются ТОЛЬКО для чтения из существующих данных (никакие проверяемые
сущности не изменяются). Независимый аудитор фиксирует находки как отдельные записи
`audit_findings`; сканирование — детерминированное (без ИИ, правила воспроизводимы),
идемпотентное (повторный запуск не создаёт дублей открытых находок по той же
сущности). Человек рассматривает и закрывает находку. Все действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AuditFinding,
    DailyReport,
    Project,
    Risk,
    Task,
    User,
)
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

# финальные статусы задач (не считаются просроченными)
TASK_FINAL = ("completed", "cancelled", "closed")
RISK_CLOSED = ("closed", "realized")
CATEGORIES = (
    "overdue_task", "risk_no_owner", "missing_evidence", "bypassed_approval",
    "unusual_change", "anomalous_expense", "incomplete_log", "agent_quality", "other",
)


class KpiError(RuntimeError):
    """Нарушение правил модуля KPI/аудита."""


# ------------------------------ KPI (чтение) ----------------------------- #


def _project_scope(session: Session, user: User, organization_id: uuid.UUID):
    """Множество id проектов организации, доступных пользователю (или None = все)."""
    allowed = accessible_project_ids(session, user)
    org_projects = set(session.execute(
        select(Project.id).where(Project.organization_id == organization_id)
    ).scalars())
    if allowed is None:
        return org_projects, None
    return org_projects & allowed, allowed


def kpi_summary(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    now = datetime.now(UTC)
    scope, allowed = _project_scope(session, user, organization_id)

    tasks = list(session.execute(
        select(Task).where(
            Task.organization_id == organization_id, Task.deleted_at.is_(None)
        )
    ).scalars())
    if allowed is not None:
        tasks = [t for t in tasks if t.project_id is None or t.project_id in allowed]
    tasks_total = len(tasks)
    tasks_completed = sum(1 for t in tasks if t.status in ("completed", "closed"))
    tasks_overdue = sum(
        1 for t in tasks
        if t.status not in TASK_FINAL and t.due_at is not None and _aware(t.due_at) < now
    )
    overdue_ratio = round(tasks_overdue / tasks_total, 3) if tasks_total else 0.0

    risks = list(session.execute(
        select(Risk).where(
            Risk.organization_id == organization_id, Risk.deleted_at.is_(None)
        )
    ).scalars())
    if allowed is not None:
        risks = [r for r in risks if r.project_id is None or r.project_id in allowed]
    risks_open = sum(1 for r in risks if r.status not in RISK_CLOSED)
    risks_high = sum(
        1 for r in risks if r.status not in RISK_CLOSED and r.severity in ("high", "critical")
    )

    week_ago = (now - timedelta(days=7)).date()
    reports = list(session.execute(
        select(DailyReport).where(
            DailyReport.report_date >= week_ago, DailyReport.deleted_at.is_(None)
        )
    ).scalars())
    if scope is not None:
        reports = [d for d in reports if d.project_id in scope]
    reports_7d = len(reports)

    findings = _open_findings(session, user, organization_id)
    findings_open = len(findings)
    findings_high = sum(1 for f in findings if f.severity == "high")

    return {
        "tasks_total": tasks_total,
        "tasks_completed": tasks_completed,
        "tasks_overdue": tasks_overdue,
        "overdue_ratio": overdue_ratio,
        "risks_open": risks_open,
        "risks_high": risks_high,
        "daily_reports_7d": reports_7d,
        "findings_open": findings_open,
        "findings_high": findings_high,
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


# --------------------------- Находки аудита ------------------------------ #


def _open_findings(session: Session, user: User, organization_id: uuid.UUID) -> list[AuditFinding]:
    allowed = accessible_project_ids(session, user)
    rows = list(session.execute(
        select(AuditFinding).where(
            AuditFinding.organization_id == organization_id,
            AuditFinding.deleted_at.is_(None),
            AuditFinding.status.in_(("open", "acknowledged")),
        )
    ).scalars())
    if allowed is None:
        return rows
    return [f for f in rows if f.project_id is None or f.project_id in allowed]


def list_findings(
    session: Session, user: User, organization_id: uuid.UUID, *, status: str | None = None,
) -> list[AuditFinding]:
    allowed = accessible_project_ids(session, user)
    stmt = select(AuditFinding).where(
        AuditFinding.organization_id == organization_id,
        AuditFinding.deleted_at.is_(None),
    )
    if status is not None:
        stmt = stmt.where(AuditFinding.status == status)
    rows = list(session.execute(stmt.order_by(AuditFinding.created_at.desc())).scalars())
    if allowed is None:
        return rows
    return [f for f in rows if f.project_id is None or f.project_id in allowed]


def can_access_finding(session: Session, user: User, finding: AuditFinding) -> bool:
    if finding.project_id is None:
        return True
    return can_access_project(session, user, finding.project_id)


def create_finding(
    session: Session, *, organization_id: uuid.UUID, user: User, category: str, title: str,
    severity: str = "medium", detail: str | None = None, project_id: uuid.UUID | None = None,
    entity_type: str | None = None, entity_id: uuid.UUID | None = None,
    detected_by: str = "manual",
) -> AuditFinding:
    if category not in CATEGORIES:
        raise KpiError(f"недопустимая категория '{category}'")
    if severity not in ("low", "medium", "high"):
        raise KpiError(f"недопустимая важность '{severity}'")
    finding = AuditFinding(
        organization_id=organization_id, project_id=project_id, category=category,
        severity=severity, title=title, detail=detail, entity_type=entity_type,
        entity_id=entity_id, status="open", detected_by=detected_by, created_by=user.id,
    )
    session.add(finding)
    session.flush()
    _audit(session, user, "audit.finding_created", organization_id,
           finding.id, {"category": category, "severity": severity})
    session.commit()
    return finding


def resolve_finding(
    session: Session, finding: AuditFinding, *, user: User, status: str,
    note: str | None = None,
) -> AuditFinding:
    """Человеческий разбор находки. Проверяемые данные не изменяются."""
    if status not in ("acknowledged", "resolved", "false_positive"):
        raise KpiError(f"недопустимый статус '{status}'")
    if finding.status in ("resolved", "false_positive"):
        raise KpiError("находка уже закрыта")
    finding.status = status
    finding.resolution_note = note
    finding.owner_user_id = user.id
    _audit(session, user, f"audit.finding_{status}", finding.organization_id,
           finding.id, {"status": status})
    session.commit()
    return finding


def run_scan(session: Session, *, organization_id: uuid.UUID, user: User) -> dict:
    """Детерминированное сканирование данных на аномалии (идемпотентно).

    Правила (без ИИ, воспроизводимы):
      • overdue_task — задача просрочена (due_at в прошлом, статус не финальный);
      • risk_no_owner — активный риск без ответственного.
    Повторный запуск не создаёт дублей открытых находок по той же сущности.
    """
    now = datetime.now(UTC)
    existing = {
        (f.category, f.entity_id)
        for f in session.execute(
            select(AuditFinding).where(
                AuditFinding.organization_id == organization_id,
                AuditFinding.deleted_at.is_(None),
                AuditFinding.status.in_(("open", "acknowledged")),
            )
        ).scalars()
    }
    created = 0

    tasks = session.execute(
        select(Task).where(
            Task.organization_id == organization_id, Task.deleted_at.is_(None)
        )
    ).scalars()
    for t in tasks:
        if (t.status not in TASK_FINAL and t.due_at is not None
                and _aware(t.due_at) < now and ("overdue_task", t.id) not in existing):
            session.add(AuditFinding(
                organization_id=organization_id, project_id=t.project_id,
                category="overdue_task", severity="medium",
                title=f"Просроченная задача: {t.title[:120]}",
                detail="Срок задачи истёк, статус не завершён.",
                entity_type="task", entity_id=t.id, status="open", detected_by="scan",
                created_by=user.id,
            ))
            existing.add(("overdue_task", t.id))
            created += 1

    risks = session.execute(
        select(Risk).where(
            Risk.organization_id == organization_id, Risk.deleted_at.is_(None)
        )
    ).scalars()
    for r in risks:
        if (r.status not in RISK_CLOSED and r.owner_employee_id is None
                and ("risk_no_owner", r.id) not in existing):
            session.add(AuditFinding(
                organization_id=organization_id, project_id=r.project_id,
                category="risk_no_owner", severity="high" if r.severity in ("high", "critical") else "medium",
                title=f"Риск без ответственного: {r.title[:120]}",
                detail="Активный риск не имеет назначенного владельца.",
                entity_type="risk", entity_id=r.id, status="open", detected_by="scan",
                created_by=user.id,
            ))
            existing.add(("risk_no_owner", r.id))
            created += 1

    _audit(session, user, "audit.scan_run", organization_id, None, {"created": created})
    session.commit()
    return {"created": created}


def _audit(session, user, action, org_id, entity_id, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type="audit_finding", entity_id=entity_id,
        new_values=new_values, risk_level="R1", commit=False,
    )
