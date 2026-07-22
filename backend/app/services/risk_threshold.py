"""Сервис настраиваемых порогов согласований (этап G, PR-G).

Пороговые суммы/сроки и уровни согласования настраиваются, а не зашиты в код
(PROCESS_CORE_PLAN.md §3). `resolve` подбирает наиболее специфичное применимое
правило (проект+вид > вид > организация) и возвращает уровень риска, число
согласующих и необходимость MFA. Если правил нет — уровень по умолчанию R1.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import RiskThreshold
from app.models.risk_threshold import THRESHOLD_METRICS
from app.services.audit import record_event


class RiskThresholdError(Exception):
    """Ошибка настройки порога согласования."""


def set_threshold(
    session: Session,
    organization_id: uuid.UUID,
    *,
    metric: str,
    risk_level: str,
    min_value: Decimal | None = None,
    max_value: Decimal | None = None,
    process_kind: str | None = None,
    project_id: uuid.UUID | None = None,
    required_approvals: int = 1,
    requires_mfa: bool = False,
    description: str | None = None,
    actor_user_id: uuid.UUID | None = None,
) -> RiskThreshold:
    if metric not in THRESHOLD_METRICS:
        raise RiskThresholdError(f"Недопустимая метрика: {metric}")
    if risk_level not in ("R1", "R2", "R3", "R4"):
        raise RiskThresholdError(f"Недопустимый уровень риска: {risk_level}")
    if required_approvals < 0:
        raise RiskThresholdError("Число согласующих не может быть отрицательным")
    row = RiskThreshold(
        organization_id=organization_id, project_id=project_id,
        process_kind=process_kind, metric=metric, min_value=min_value,
        max_value=max_value, risk_level=risk_level,
        required_approvals=required_approvals, requires_mfa=requires_mfa,
        description=description, active=True,
    )
    session.add(row)
    session.flush()
    record_event(
        session, actor_type="user", action="risk_threshold.set",
        actor_user_id=actor_user_id, organization_id=organization_id,
        entity_type="risk_threshold", entity_id=row.id,
        new_values={"metric": metric, "risk_level": risk_level,
                    "process_kind": process_kind},
        risk_level="R1", commit=True,
    )
    return row


def list_thresholds(
    session: Session, organization_id: uuid.UUID, *, process_kind: str | None = None
) -> list[RiskThreshold]:
    q = select(RiskThreshold).where(
        RiskThreshold.organization_id == organization_id,
        RiskThreshold.deleted_at.is_(None),
        RiskThreshold.active.is_(True),
    )
    if process_kind is not None:
        q = q.where(
            (RiskThreshold.process_kind == process_kind)
            | (RiskThreshold.process_kind.is_(None))
        )
    return list(session.execute(q).scalars())


def _specificity(t: RiskThreshold) -> int:
    score = 0
    if t.process_kind is not None:
        score += 2
    if t.project_id is not None:
        score += 1
    return score


def _matches(t: RiskThreshold, value: Decimal) -> bool:
    if t.min_value is not None and value < t.min_value:
        return False
    if t.max_value is not None and value >= t.max_value:
        return False
    return True


def resolve(
    session: Session,
    organization_id: uuid.UUID,
    *,
    process_kind: str | None = None,
    project_id: uuid.UUID | None = None,
    amount: Decimal | None = None,
    duration_days: int | None = None,
) -> dict:
    """Определяет уровень риска по настроенным порогам (наиболее специфичное правило)."""
    candidates = [
        t for t in list_thresholds(session, organization_id, process_kind=process_kind)
        if t.project_id in (None, project_id)
    ]
    metric_value: dict[str, Decimal | None] = {
        "amount": amount,
        "duration_days": Decimal(duration_days) if duration_days is not None else None,
    }
    best: RiskThreshold | None = None
    for t in candidates:
        if t.metric == "default":
            matched = True
        else:
            v = metric_value.get(t.metric)
            matched = v is not None and _matches(t, v)
        if not matched:
            continue
        if best is None or _specificity(t) > _specificity(best):
            best = t
    if best is None:
        return {"risk_level": "R1", "required_approvals": 1, "requires_mfa": False}
    return {
        "risk_level": best.risk_level,
        "required_approvals": best.required_approvals,
        "requires_mfa": best.requires_mfa,
    }
