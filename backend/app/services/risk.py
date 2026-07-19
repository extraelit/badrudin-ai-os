"""Бизнес-логика модуля «Реестр рисков» (ROADMAP этап 15, §20).

Жизненный цикл: идентификация → оценка (вероятность × влияние → серьёзность) →
план снижения → снижение → принятие / закрытие / реализация. Принятие высокого
или критического риска — решение человека (фиксируется, кто и когда). Все
значимые действия — в `audit_events`; изоляция по проекту (ABAC).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Risk, User
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

CATEGORIES = (
    "schedule", "cost", "quality", "safety", "supply", "legal", "hr", "financial", "other",
)
LEVELS = ("low", "medium", "high")
_RANK = {"low": 1, "medium": 2, "high": 3}


class RiskError(RuntimeError):
    """Нарушение правил ведения реестра рисков."""


def compute_severity(probability: str, impact: str) -> str:
    """Серьёзность из матрицы вероятность × влияние (3×3)."""
    score = _RANK.get(probability, 2) * _RANK.get(impact, 2)
    if score >= 9:
        return "critical"
    if score >= 6:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def can_access_risk(session: Session, user: User, risk: Risk) -> bool:
    if risk.project_id is None:
        return True
    return can_access_project(session, user, risk.project_id)


# ------------------------------ Действия --------------------------------- #


def register_risk(
    session: Session, *, organization_id: uuid.UUID, user: User, title: str,
    description: str | None = None, category: str = "other",
    probability: str = "medium", impact: str = "medium",
    project_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    owner_employee_id: uuid.UUID | None = None, source_type: str | None = None,
    source_id: uuid.UUID | None = None, number: str | None = None,
) -> Risk:
    if category not in CATEGORIES:
        raise RiskError(f"недопустимая категория '{category}'")
    if probability not in LEVELS or impact not in LEVELS:
        raise RiskError("вероятность и влияние — low | medium | high")
    risk = Risk(
        organization_id=organization_id, project_id=project_id, site_id=site_id,
        number=number, title=title, description=description, category=category,
        probability=probability, impact=impact,
        severity=compute_severity(probability, impact), status="identified",
        owner_employee_id=owner_employee_id, identified_by_user_id=user.id,
        source_type=source_type or "manual", source_id=source_id, created_by=user.id,
    )
    session.add(risk)
    session.flush()
    _audit(session, user, "risk.registered", organization_id, risk.id,
           {"title": title, "severity": risk.severity})
    session.commit()
    return risk


def assess_risk(
    session: Session, risk: Risk, *, user: User, probability: str, impact: str,
    owner_employee_id: uuid.UUID | None = None,
) -> Risk:
    if risk.status in ("closed", "realized"):
        raise RiskError("нельзя переоценивать закрытый риск")
    if probability not in LEVELS or impact not in LEVELS:
        raise RiskError("вероятность и влияние — low | medium | high")
    risk.probability = probability
    risk.impact = impact
    risk.severity = compute_severity(probability, impact)
    if owner_employee_id is not None:
        risk.owner_employee_id = owner_employee_id
    if risk.status == "identified":
        risk.status = "assessed"
    _audit(session, user, "risk.assessed", risk.organization_id, risk.id,
           {"severity": risk.severity})
    session.commit()
    return risk


def plan_mitigation(
    session: Session, risk: Risk, *, user: User, mitigation_plan: str,
    due_at: datetime | None = None, owner_employee_id: uuid.UUID | None = None,
) -> Risk:
    if risk.status in ("closed", "realized"):
        raise RiskError("риск закрыт")
    risk.mitigation_plan = mitigation_plan
    risk.due_at = due_at
    if owner_employee_id is not None:
        risk.owner_employee_id = owner_employee_id
    risk.status = "mitigating"
    _audit(session, user, "risk.mitigation_planned", risk.organization_id, risk.id, {})
    session.commit()
    return risk


def decide_risk(
    session: Session, risk: Risk, *, user: User, decision: str, comment: str | None = None,
) -> Risk:
    """Принятие / закрытие / фиксация реализации риска (решение человека)."""
    if decision not in ("accepted", "closed", "realized"):
        raise RiskError("решение — accepted | closed | realized")
    if risk.status in ("closed", "realized"):
        raise RiskError("риск уже закрыт")
    risk.status = decision
    risk.decided_by_user_id = user.id
    risk.decided_at = datetime.now(UTC)
    risk.decision_comment = comment
    if decision in ("closed", "realized"):
        risk.closed_at = datetime.now(UTC)
    _audit(session, user, f"risk.{decision}", risk.organization_id, risk.id,
           {"severity": risk.severity, "decision": decision})
    session.commit()
    return risk


# ------------------------------ Чтение ----------------------------------- #


def list_risks(
    session: Session, user: User, organization_id: uuid.UUID, *,
    status: str | None = None, severity: str | None = None,
) -> list[Risk]:
    allowed = accessible_project_ids(session, user)
    stmt = select(Risk).where(
        Risk.organization_id == organization_id, Risk.deleted_at.is_(None)
    )
    if status is not None:
        stmt = stmt.where(Risk.status == status)
    if severity is not None:
        stmt = stmt.where(Risk.severity == severity)
    rows = list(session.execute(stmt.order_by(Risk.created_at.desc())).scalars())
    if allowed is None:
        return rows
    return [r for r in rows if r.project_id is None or r.project_id in allowed]


def summary(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    risks = list_risks(session, user, organization_id)
    open_risks = [r for r in risks if r.status not in ("closed", "realized")]
    return {
        "total": len(risks),
        "open": len(open_risks),
        "critical": sum(1 for r in open_risks if r.severity == "critical"),
        "high": sum(1 for r in open_risks if r.severity == "high"),
        "accepted": sum(1 for r in risks if r.status == "accepted"),
        "realized": sum(1 for r in risks if r.status == "realized"),
    }


def _audit(session, user, action, org_id, risk_id, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type="risk", entity_id=risk_id,
        new_values=new_values, risk_level="R1", commit=False,
    )
