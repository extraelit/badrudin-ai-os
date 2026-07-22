"""Сервис строительного контроля и качества (этап F, PR-F).

Контрольные карты (шаблоны по видам работ) и проверки. Итоговое решение о
соответствии норме принимает уполномоченный специалист (строительный контроль/
главный инженер/директор) — ИИ только подсказывает возможное отклонение
(PROCESS_CORE_PLAN.md §5). Разделение обязанностей: исполнитель работы не
принимает результат собственной проверки качества (проверяющий — специалист
контроля, не исполнитель).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import QualityControlCard, QualityControlCheck
from app.models.quality import CHECK_RESULTS, CONTROL_KINDS, FINAL_DECISIONS
from app.services.access import get_role_codes
from app.services.audit import record_event

# Роли, уполномоченные выносить итоговое решение о соответствии норме.
QUALITY_DECIDER_ROLES = {
    "system_owner", "construction_control_engineer", "chief_engineer",
    "general_director", "executive_director",
}


class QualityError(Exception):
    """Ошибка бизнес-правил строительного контроля."""


def _now() -> datetime:
    return datetime.now(UTC)


def create_card(
    session: Session,
    organization_id: uuid.UUID,
    *,
    work_type: str,
    name: str,
    controlled_parameter: str,
    control_kind: str = "operational",
    project_id: uuid.UUID | None = None,
    normative_item_id: uuid.UUID | None = None,
    allowed_value: str | None = None,
    check_method: str | None = None,
    responsible_position: str | None = None,
    requires_document: bool = False,
    requires_photo: bool = True,
    requires_measurement: bool = False,
    actor_user_id: uuid.UUID | None = None,
) -> QualityControlCard:
    if control_kind not in CONTROL_KINDS:
        raise QualityError(f"Недопустимый вид контроля: {control_kind}")
    card = QualityControlCard(
        organization_id=organization_id, project_id=project_id, work_type=work_type,
        name=name, control_kind=control_kind, normative_item_id=normative_item_id,
        controlled_parameter=controlled_parameter, allowed_value=allowed_value,
        check_method=check_method, responsible_position=responsible_position,
        requires_document=requires_document, requires_photo=requires_photo,
        requires_measurement=requires_measurement, status="active",
    )
    session.add(card)
    session.flush()
    record_event(
        session, actor_type="user", action="quality.card.create",
        actor_user_id=actor_user_id, organization_id=organization_id,
        entity_type="quality_control_card", entity_id=card.id,
        new_values={"work_type": work_type, "control_kind": control_kind},
        risk_level="R1", commit=True,
    )
    return card


def list_cards(
    session: Session, organization_id: uuid.UUID, *, control_kind: str | None = None
) -> list[QualityControlCard]:
    q = select(QualityControlCard).where(
        QualityControlCard.organization_id == organization_id,
        QualityControlCard.deleted_at.is_(None),
    )
    if control_kind:
        q = q.where(QualityControlCard.control_kind == control_kind)
    return list(session.execute(q).scalars())


def record_check(
    session: Session,
    card: QualityControlCard,
    *,
    result: str,
    checked_by: uuid.UUID | None = None,
    measured_value: str | None = None,
    instrument: str | None = None,
    instrument_verification: str | None = None,
    remark: str | None = None,
    defect_deadline: datetime | None = None,
    process_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None,
    ai_suggestion: str | None = None,
) -> QualityControlCheck:
    """Фиксирует результат проверки. При `fail`/`conditional` — срок устранения и
    признак повторной проверки."""
    if result not in CHECK_RESULTS:
        raise QualityError(f"Недопустимый результат: {result}")
    if card.requires_measurement and not measured_value:
        raise QualityError("Карта требует измерения — укажите измеренное значение")
    check = QualityControlCheck(
        organization_id=card.organization_id, card_id=card.id,
        project_id=project_id or card.project_id, process_id=process_id,
        checked_by=checked_by, checked_at=_now(), measured_value=measured_value,
        instrument=instrument, instrument_verification=instrument_verification,
        result=result, remark=remark, defect_deadline=defect_deadline,
        recheck_required=result in ("fail", "conditional"),
        ai_suggestion=ai_suggestion,
    )
    session.add(check)
    session.flush()
    record_event(
        session, actor_type="user", action="quality.check.record",
        actor_user_id=checked_by, organization_id=card.organization_id,
        entity_type="quality_control_check", entity_id=check.id,
        new_values={"result": result, "card_id": str(card.id)},
        risk_level="R2", commit=True,
    )
    return check


def create_recheck(
    session: Session,
    original: QualityControlCheck,
    *,
    result: str,
    checked_by: uuid.UUID | None = None,
    measured_value: str | None = None,
    instrument: str | None = None,
    remark: str | None = None,
) -> QualityControlCheck:
    """Повторная проверка после устранения замечания (ссылается на исходную)."""
    card = session.get(QualityControlCard, original.card_id)
    check = QualityControlCheck(
        organization_id=original.organization_id, card_id=original.card_id,
        project_id=original.project_id, process_id=original.process_id,
        checked_by=checked_by, checked_at=_now(), measured_value=measured_value,
        instrument=instrument, result=result, remark=remark,
        recheck_required=result in ("fail", "conditional"),
        recheck_of_check_id=original.id,
    )
    if card is not None and card.requires_measurement and not measured_value:
        raise QualityError("Карта требует измерения — укажите измеренное значение")
    session.add(check)
    session.flush()
    record_event(
        session, actor_type="user", action="quality.check.recheck",
        actor_user_id=checked_by, organization_id=original.organization_id,
        entity_type="quality_control_check", entity_id=check.id,
        old_values={"recheck_of": str(original.id)},
        new_values={"result": result}, risk_level="R2", commit=True,
    )
    return check


def finalize_check(
    session: Session,
    check: QualityControlCheck,
    *,
    decider_user_id: uuid.UUID,
    decision: str,
    comment: str | None = None,
) -> QualityControlCheck:
    """Итоговое решение уполномоченного специалиста (не ИИ, не исполнитель работы).

    Требуется роль специалиста контроля/руководителя. Исполнитель проверки не может
    быть тем, кто её фактически выполнял (SoD): решающий ≠ `checked_by`.
    """
    if decision not in FINAL_DECISIONS:
        raise QualityError("Решение: accepted | rejected")
    if check.final_decision is not None:
        raise QualityError("Итоговое решение уже вынесено")
    roles = get_role_codes(session, decider_user_id)
    if not (roles & QUALITY_DECIDER_ROLES):
        raise QualityError(
            "Итоговое решение о соответствии норме выносит уполномоченный "
            "специалист (строительный контроль/главный инженер/директор)"
        )
    if decision == "accepted" and check.checked_by == decider_user_id:
        raise QualityError(
            "Проверяющий не может единолично утвердить собственную проверку (SoD)"
        )
    check.final_decision = decision
    check.final_decision_by = decider_user_id
    check.final_decision_at = _now()
    if comment:
        check.remark = ((check.remark + " | ") if check.remark else "") + comment
    record_event(
        session, actor_type="user", action="quality.check.finalize",
        actor_user_id=decider_user_id, organization_id=check.organization_id,
        entity_type="quality_control_check", entity_id=check.id,
        new_values={"final_decision": decision}, reason=comment, risk_level="R3",
        commit=True,
    )
    return check


def list_checks(
    session: Session, organization_id: uuid.UUID, *, card_id: uuid.UUID | None = None
) -> list[QualityControlCheck]:
    q = select(QualityControlCheck).where(
        QualityControlCheck.organization_id == organization_id
    )
    if card_id:
        q = q.where(QualityControlCheck.card_id == card_id)
    return list(session.execute(q.order_by(QualityControlCheck.created_at.desc())).scalars())
