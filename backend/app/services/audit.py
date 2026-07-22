"""Сервис записи в единый журнал аудита `audit_events` (T-1.D1).

Соответствует DATABASE.md раздел 20 и ACCESS_CONTROL.md раздел 20. Запись
только добавляется (append-only); изменение и удаление запрещены (T-1.D2).
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditEvent, Employee, User


def _resolve_actor_position_id(
    session: Session, actor_user_id: uuid.UUID | None
) -> uuid.UUID | None:
    """Должность актора на момент действия (снимок по текущей должности сотрудника).

    Значение фиксируется в записи и далее не меняется даже при переводе — это и
    есть «должность на момент действия» (ACCESS_CONTROL.md раздел 20).
    """
    if actor_user_id is None:
        return None
    row = session.execute(
        select(Employee.position_id)
        .join(User, User.employee_id == Employee.id)
        .where(User.id == actor_user_id)
    ).first()
    return row[0] if row else None


def record_event(
    session: Session,
    *,
    actor_type: str,
    action: str,
    actor_user_id: uuid.UUID | None = None,
    actor_agent_id: uuid.UUID | None = None,
    actor_position_id: uuid.UUID | None = None,
    organization_id: uuid.UUID | None = None,
    entity_type: str | None = None,
    entity_id: uuid.UUID | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    reason: str | None = None,
    approval_id: uuid.UUID | None = None,
    request_id: str | None = None,
    ip_address: str | None = None,
    user_agent: str | None = None,
    session_id: str | None = None,
    auth_level: str | None = None,
    risk_level: str = "R0",
    commit: bool = True,
) -> AuditEvent:
    """Создаёт событие аудита. Секреты и ПДн в журнал не помещаются.

    Должность актора определяется автоматически по пользователю, если явно не
    передана (снимок на момент действия).
    """
    if actor_position_id is None:
        actor_position_id = _resolve_actor_position_id(session, actor_user_id)
    event = AuditEvent(
        actor_type=actor_type,
        action=action,
        actor_user_id=actor_user_id,
        actor_agent_id=actor_agent_id,
        actor_position_id=actor_position_id,
        organization_id=organization_id,
        entity_type=entity_type,
        entity_id=entity_id,
        old_values_json=old_values,
        new_values_json=new_values,
        reason=reason,
        approval_id=approval_id,
        request_id=request_id,
        ip_address=ip_address,
        user_agent=user_agent,
        session_id=session_id,
        auth_level=auth_level,
        risk_level=risk_level,
    )
    session.add(event)
    if commit:
        session.commit()
    return event
