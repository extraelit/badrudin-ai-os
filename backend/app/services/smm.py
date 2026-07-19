"""Бизнес-логика модуля «SMM и внешние публикации» — внутренний контур (§14).

Контент-план и публикации как черновики на утверждение. Модуль НИЧЕГО не публикует:
статусы отражают внутреннюю подготовку, обязательные проверки (права на материалы,
персональные данные, юридическая/репутационная проверка) и человеческое утверждение.
Утверждённая публикация переходит в `approved`/`scheduled` (готова к публикации
официальным утверждённым инструментом вне модуля) — фактическая публикация здесь не
выполняется. Все действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    ContentPlanItem,
    SocialPublication,
    SocialPublicationAsset,
    User,
)
from app.services.access import accessible_project_ids, can_access_project
from app.services.audit import record_event

CHANNELS = ("email", "telegram", "whatsapp_business", "instagram", "webhook", "internal")


class SmmError(RuntimeError):
    """Нарушение правил внутреннего контура SMM."""


# ------------------------------ Контент-план ----------------------------- #


def create_plan_item(
    session: Session, *, organization_id: uuid.UUID, user: User, title: str,
    theme: str | None = None, channel: str = "internal",
    planned_date: date | None = None, project_id: uuid.UUID | None = None,
    notes: str | None = None,
) -> ContentPlanItem:
    if channel not in CHANNELS:
        raise SmmError(f"недопустимый канал '{channel}'")
    item = ContentPlanItem(
        organization_id=organization_id, title=title, theme=theme, channel=channel,
        planned_date=planned_date, project_id=project_id, notes=notes,
        status="idea", created_by=user.id,
    )
    session.add(item)
    session.flush()
    _audit(session, user, "smm.plan_created", organization_id,
           "content_plan_item", item.id, {"title": title, "channel": channel})
    session.commit()
    return item


def set_plan_status(
    session: Session, item: ContentPlanItem, *, user: User, status: str,
) -> ContentPlanItem:
    if status not in ("idea", "planned", "in_progress", "done", "cancelled"):
        raise SmmError(f"недопустимый статус '{status}'")
    item.status = status
    _audit(session, user, "smm.plan_status", item.organization_id,
           "content_plan_item", item.id, {"status": status})
    session.commit()
    return item


# ------------------------------ Публикации ------------------------------- #


def create_publication(
    session: Session, *, organization_id: uuid.UUID, user: User, channel: str = "internal",
    title: str | None = None, body_text: str | None = None, hashtags: str | None = None,
    plan_item_id: uuid.UUID | None = None, connector_id: uuid.UUID | None = None,
    project_id: uuid.UUID | None = None, scheduled_for: datetime | None = None,
) -> SocialPublication:
    """Создаёт публикацию в статусе черновика (никогда не публикуется модулем)."""
    if channel not in CHANNELS:
        raise SmmError(f"недопустимый канал '{channel}'")
    pub = SocialPublication(
        organization_id=organization_id, channel=channel, title=title, body_text=body_text,
        hashtags=hashtags, plan_item_id=plan_item_id, connector_id=connector_id,
        project_id=project_id, scheduled_for=scheduled_for, status="draft",
        created_by=user.id,
    )
    session.add(pub)
    session.flush()
    _audit(session, user, "smm.publication_drafted", organization_id,
           "social_publication", pub.id, {"channel": channel})
    session.commit()
    return pub


def set_checks(
    session: Session, pub: SocialPublication, *, user: User,
    rights_confirmed: bool | None = None, pii_checked: bool | None = None,
    legal_checked: bool | None = None,
) -> SocialPublication:
    """Отмечает обязательные проверки перед утверждением (права, ПДн, юр./репутация)."""
    if pub.status in ("approved", "scheduled", "cancelled"):
        raise SmmError("публикация уже обработана")
    if rights_confirmed is not None:
        pub.rights_confirmed = rights_confirmed
    if pii_checked is not None:
        pub.pii_checked = pii_checked
    if legal_checked is not None:
        pub.legal_checked = legal_checked
    if pub.status == "draft":
        pub.status = "fact_check"
    _audit(session, user, "smm.publication_checks", pub.organization_id,
           "social_publication", pub.id, {
               "rights_confirmed": pub.rights_confirmed,
               "pii_checked": pub.pii_checked, "legal_checked": pub.legal_checked,
           })
    session.commit()
    return pub


def add_asset(
    session: Session, pub: SocialPublication, *, user: User,
    file_id: uuid.UUID | None = None, caption: str | None = None,
    quality_ok: bool = False, rights_ok: bool = False,
) -> SocialPublicationAsset:
    if pub.status in ("approved", "scheduled", "cancelled"):
        raise SmmError("нельзя менять материалы обработанной публикации")
    asset = SocialPublicationAsset(
        publication_id=pub.id, file_id=file_id, caption=caption,
        quality_ok=quality_ok, rights_ok=rights_ok, created_by=user.id,
    )
    session.add(asset)
    session.flush()
    _audit(session, user, "smm.asset_added", pub.organization_id,
           "social_publication_asset", asset.id, {"publication_id": str(pub.id)})
    session.commit()
    return asset


def submit_publication(session: Session, pub: SocialPublication, *, user: User) -> Approval:
    """Отправляет публикацию на утверждение руководителем (§14, критерии этапа 17).

    До утверждения обязательны: непустой текст, подтверждённые права на материалы,
    проверка персональных данных и юридическая/репутационная проверка.
    """
    if pub.status not in ("draft", "fact_check"):
        raise SmmError(f"нельзя отправить на утверждение из '{pub.status}'")
    if not (pub.body_text or pub.title):
        raise SmmError("пустая публикация")
    if not (pub.rights_confirmed and pub.pii_checked and pub.legal_checked):
        raise SmmError("не пройдены обязательные проверки (права/ПДн/юридическая)")
    approval = Approval(
        organization_id=pub.organization_id, entity_type="social_publication",
        entity_id=pub.id, approval_type="social_publication_approval",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    pub.status = "pending_approval"
    pub.approval_id = approval.id
    _audit(session, user, "smm.publication_submitted", pub.organization_id,
           "social_publication", pub.id, {}, approval_id=approval.id)
    session.commit()
    return approval


def decide_publication(
    session: Session, pub: SocialPublication, *, user: User, decision: str,
    comment: str | None = None,
) -> SocialPublication:
    """Утверждение/отклонение публикации человеком.

    `approved`/`scheduled` означает «готово к публикации официальным утверждённым
    инструментом вне модуля» — фактическая публикация здесь не производится.
    """
    if decision not in ("approved", "rejected"):
        raise SmmError("решение — approved | rejected")
    if pub.status != "pending_approval":
        raise SmmError("публикация не на утверждении")
    if pub.approval_id is not None:
        approval = session.get(Approval, pub.approval_id)
        approval.status = decision
        approval.completed_at = datetime.now(UTC)
        session.add(ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        ))
    if decision == "approved":
        pub.status = "scheduled" if pub.scheduled_for is not None else "approved"
        pub.approved_by_user_id = user.id
        pub.approved_at = datetime.now(UTC)
    else:
        pub.status = "cancelled"
        pub.rejection_reason = comment
    _audit(session, user, f"smm.publication_{decision}", pub.organization_id,
           "social_publication", pub.id, {"decision": decision, "status": pub.status},
           approval_id=pub.approval_id)
    session.commit()
    return pub


def cancel_publication(
    session: Session, pub: SocialPublication, *, user: User, reason: str,
) -> SocialPublication:
    if pub.status in ("approved", "scheduled", "cancelled"):
        raise SmmError("публикация уже обработана")
    pub.status = "cancelled"
    pub.rejection_reason = reason
    _audit(session, user, "smm.publication_cancelled", pub.organization_id,
           "social_publication", pub.id, {"reason": reason})
    session.commit()
    return pub


# ------------------------------ Чтение ----------------------------------- #


def list_plan(
    session: Session, user: User, organization_id: uuid.UUID,
) -> list[ContentPlanItem]:
    allowed = accessible_project_ids(session, user)
    rows = list(session.execute(
        select(ContentPlanItem).where(
            ContentPlanItem.organization_id == organization_id,
            ContentPlanItem.deleted_at.is_(None),
        ).order_by(ContentPlanItem.created_at.desc())
    ).scalars())
    if allowed is None:
        return rows
    return [i for i in rows if i.project_id is None or i.project_id in allowed]


def list_publications(
    session: Session, user: User, organization_id: uuid.UUID, *, status: str | None = None,
) -> list[SocialPublication]:
    allowed = accessible_project_ids(session, user)
    stmt = select(SocialPublication).where(
        SocialPublication.organization_id == organization_id,
        SocialPublication.deleted_at.is_(None),
    )
    if status is not None:
        stmt = stmt.where(SocialPublication.status == status)
    rows = list(session.execute(stmt.order_by(SocialPublication.created_at.desc())).scalars())
    if allowed is None:
        return rows
    return [p for p in rows if p.project_id is None or p.project_id in allowed]


def list_assets(session: Session, pub: SocialPublication) -> list[SocialPublicationAsset]:
    return list(session.execute(
        select(SocialPublicationAsset).where(
            SocialPublicationAsset.publication_id == pub.id
        ).order_by(SocialPublicationAsset.created_at)
    ).scalars())


def can_access_publication(session: Session, user: User, pub: SocialPublication) -> bool:
    if pub.project_id is None:
        return True
    return can_access_project(session, user, pub.project_id)


def summary(session: Session, user: User, organization_id: uuid.UUID) -> dict:
    plan = list_plan(session, user, organization_id)
    pubs = list_publications(session, user, organization_id)
    return {
        "plan_total": len(plan),
        "plan_active": sum(1 for i in plan if i.status in ("planned", "in_progress")),
        "publications_draft": sum(1 for p in pubs if p.status in ("draft", "fact_check")),
        "publications_pending": sum(1 for p in pubs if p.status == "pending_approval"),
        "publications_approved": sum(1 for p in pubs if p.status in ("approved", "scheduled")),
    }


def _audit(session, user, action, org_id, entity_type, entity_id, new_values, *, approval_id=None):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        new_values=new_values, approval_id=approval_id, risk_level="R3", commit=False,
    )
