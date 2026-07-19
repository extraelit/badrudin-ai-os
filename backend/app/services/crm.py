"""Бизнес-логика модуля «Ядро CRM».

Правила:
- цепочка lead → deal → commercial_offer → contract → project; проект создаётся
  только после выигранной сделки и утверждённого/подписанного договора;
- согласования через общий контур `approvals`: обычные действия — R2; перевод
  сделки в «выиграна» и подписание договора — R3; крупная сделка/договор
  (сумма ≥ порога организации, по умолчанию 10 000 000 ₽) — R4 + MFA;
- коммерческие предложения не дублируются: сделка ссылается на существующее
  `commercial_offers`;
- контактные данные (телефон, e-mail) — ПДн: маскируются для пользователей без
  права `crm.contact.pii`;
- все значимые действия фиксируются в `audit_events`;
- денежные значения — Decimal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    Communication,
    Contract,
    Counterparty,
    Deal,
    DealStageHistory,
    Lead,
    PipelineStage,
    Project,
    SalesTarget,
    Task,
    User,
)
from app.services.access import can_access_project, has_permission
from app.services.audit import record_event

# Значение по умолчанию, если у организации нет строки crm_settings.
DEFAULT_DEAL_R4_AMOUNT = Decimal("10000000.00")
PII_PERMISSION = "crm.contact.pii"


class CrmStateError(RuntimeError):
    """Недопустимый переход состояния сущности CRM."""


class CrmValidationError(RuntimeError):
    """Нарушение бизнес-правила (например, проект без выигранной сделки/договора)."""


class CrmAuthorizationError(RuntimeError):
    """Недостаточно условий для подтверждения (например, отсутствует MFA для R4)."""


# ------------------------------ Настройки ------------------------------- #


def deal_r4_threshold(session: Session, organization_id: uuid.UUID) -> Decimal:
    """Порог крупной сделки/договора (R4) для организации."""
    from app.models import CrmSettings

    s = session.execute(
        select(CrmSettings).where(CrmSettings.organization_id == organization_id)
    ).scalars().first()
    if s is None:
        return DEFAULT_DEAL_R4_AMOUNT
    return Decimal(s.deal_r4_amount_threshold)


def decision_risk_level(amount: Decimal, *, threshold: Decimal) -> str:
    """Уровень риска подтверждения: R4 для крупной суммы, иначе R3."""
    return "R4" if Decimal(amount) >= threshold else "R3"


# ------------------------- Маскирование ПДн ------------------------------ #


def user_can_view_pii(session: Session, user: User) -> bool:
    """Право видеть телефоны/e-mail контактов в открытом виде."""
    return has_permission(session, user.id, PII_PERMISSION)


def mask_email(value: str | None) -> str | None:
    if not value:
        return value
    local, _, domain = value.partition("@")
    if not domain:
        return "***"
    head = local[0] if local else "*"
    return f"{head}***@{domain}"


def mask_phone(value: str | None) -> str | None:
    if not value:
        return value
    digits = [c for c in value if c.isdigit()]
    if len(digits) <= 4:
        return "***"
    return "***" + "".join(digits[-4:])


def apply_pii(value: str | None, *, allowed: bool, kind: str) -> str | None:
    """Возвращает значение как есть при наличии прав, иначе — маскированное."""
    if allowed:
        return value
    return mask_email(value) if kind == "email" else mask_phone(value)


# ------------------------------ Воронка --------------------------------- #

# Стандартный набор этапов воронки — используется в тестовых данных/инициализации.
DEFAULT_PIPELINE = [
    ("new", "Новый лид", 10, False, False),
    ("qualified", "Квалифицирован", 25, False, False),
    ("offer", "Коммерческое предложение", 50, False, False),
    ("negotiation", "Переговоры", 70, False, False),
    ("contract", "Договор", 90, False, False),
    ("won", "Выиграна", 100, True, False),
    ("lost", "Проиграна", 0, False, True),
]


def ensure_default_pipeline(
    session: Session, organization_id: uuid.UUID, *, commit: bool = True
) -> list[PipelineStage]:
    """Создаёт стандартные этапы воронки, если их ещё нет у организации."""
    existing = list(
        session.execute(
            select(PipelineStage).where(
                PipelineStage.organization_id == organization_id
            )
        ).scalars()
    )
    if existing:
        return existing
    stages: list[PipelineStage] = []
    for order, (code, name, prob, is_won, is_lost) in enumerate(DEFAULT_PIPELINE, start=1):
        stage = PipelineStage(
            organization_id=organization_id, code=code, name=name,
            sort_order=order, probability_percent=Decimal(prob),
            is_won=is_won, is_lost=is_lost,
        )
        session.add(stage)
        stages.append(stage)
    if commit:
        session.commit()
    return stages


def _stage(session: Session, org_id: uuid.UUID, *, won: bool = False, lost: bool = False):
    q = select(PipelineStage).where(
        PipelineStage.organization_id == org_id,
        PipelineStage.deleted_at.is_(None),
    )
    if won:
        q = q.where(PipelineStage.is_won.is_(True))
    if lost:
        q = q.where(PipelineStage.is_lost.is_(True))
    return session.execute(q.order_by(PipelineStage.sort_order)).scalars().first()


# ------------------------------- Лиды ----------------------------------- #


def convert_lead_to_deal(
    session: Session,
    lead: Lead,
    *,
    user: User,
    counterparty_id: uuid.UUID | None = None,
    amount: Decimal | None = None,
    responsible_employee_id: uuid.UUID | None = None,
) -> Deal:
    """Конвертирует лид в сделку (lead → deal). Оригинальный лид помечается."""
    if lead.status in ("converted", "rejected"):
        raise CrmStateError(f"лид в состоянии '{lead.status}' нельзя конвертировать")
    cp_id = counterparty_id or lead.counterparty_id
    if cp_id is None:
        raise CrmValidationError("для конвертации требуется контрагент (counterparty)")
    stage = _stage(session, lead.organization_id) or None
    deal = Deal(
        organization_id=lead.organization_id,
        counterparty_id=cp_id,
        lead_id=lead.id,
        pipeline_stage_id=stage.id if stage else None,
        title=lead.title,
        description=lead.description,
        amount=Decimal(amount if amount is not None else (lead.estimated_amount or 0)),
        currency=lead.currency,
        status="open",
        responsible_employee_id=responsible_employee_id or lead.responsible_employee_id,
        created_by=user.id,
    )
    session.add(deal)
    session.flush()
    lead.status = "converted"
    lead.counterparty_id = cp_id
    lead.converted_deal_id = deal.id
    session.add(
        DealStageHistory(
            deal_id=deal.id, from_stage_id=None,
            to_stage_id=deal.pipeline_stage_id, changed_by=user.id,
            note="Создана из лида",
        )
    )
    record_event(
        session, actor_type="user", action="crm.lead.converted",
        actor_user_id=user.id, organization_id=lead.organization_id,
        entity_type="lead", entity_id=lead.id,
        new_values={"deal_id": str(deal.id)}, commit=False,
    )
    session.commit()
    return deal


# ------------------------------ Сделки ---------------------------------- #


def move_deal_stage(
    session: Session, deal: Deal, *, user: User, stage: PipelineStage, note: str | None = None
) -> Deal:
    """Перемещает сделку по воронке (обычное действие, R2). Пишет историю."""
    if deal.status != "open":
        raise CrmStateError("перемещать по воронке можно только открытую сделку")
    if stage.is_won or stage.is_lost:
        raise CrmStateError(
            "перевод в выигранный/проигранный этап выполняется через win/lose"
        )
    old = deal.pipeline_stage_id
    deal.pipeline_stage_id = stage.id
    session.add(
        DealStageHistory(
            deal_id=deal.id, from_stage_id=old, to_stage_id=stage.id,
            changed_by=user.id, note=note,
        )
    )
    record_event(
        session, actor_type="user", action="crm.deal.stage_changed",
        actor_user_id=user.id, organization_id=deal.organization_id,
        entity_type="deal", entity_id=deal.id,
        new_values={"stage_id": str(stage.id)}, risk_level="R2", commit=False,
    )
    session.commit()
    return deal


def request_deal_win(session: Session, deal: Deal, *, user: User) -> Approval:
    """Запрашивает согласование выигрыша сделки (R3, крупная — R4)."""
    if deal.status != "open":
        raise CrmStateError(f"нельзя выиграть сделку из состояния '{deal.status}'")
    if Decimal(deal.amount or 0) <= 0:
        raise CrmValidationError("у сделки должна быть указана положительная сумма")
    threshold = deal_r4_threshold(session, deal.organization_id)
    risk = decision_risk_level(Decimal(deal.amount or 0), threshold=threshold)
    approval = Approval(
        organization_id=deal.organization_id, entity_type="deal",
        entity_id=deal.id, approval_type="deal_win",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    deal.approval_id = approval.id
    deal.risk_level = risk
    record_event(
        session, actor_type="user", action="crm.deal.win_requested",
        actor_user_id=user.id, organization_id=deal.organization_id,
        entity_type="deal", entity_id=deal.id, approval_id=approval.id,
        risk_level=risk, commit=False,
    )
    session.commit()
    return approval


def decide_deal_win(
    session: Session,
    deal: Deal,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
    mfa_verified: bool = False,
) -> Deal:
    """Фиксирует решение по выигрышу сделки. R4 требует MFA (человек в контуре)."""
    if decision not in ("approved", "rejected"):
        raise CrmStateError(f"неизвестное решение '{decision}'")
    if deal.approval_id is None or deal.status != "open":
        raise CrmStateError("нет активного запроса на выигрыш сделки")
    if decision == "approved" and deal.risk_level == "R4" and not mfa_verified:
        raise CrmAuthorizationError(
            "выигрыш крупной сделки (R4) требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, deal.approval_id)
    session.add(
        ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        )
    )
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    if decision == "approved":
        won = _stage(session, deal.organization_id, won=True)
        old = deal.pipeline_stage_id
        deal.status = "won"
        deal.closed_at = datetime.now(UTC)
        if won is not None:
            deal.pipeline_stage_id = won.id
            session.add(
                DealStageHistory(
                    deal_id=deal.id, from_stage_id=old, to_stage_id=won.id,
                    changed_by=user.id, note="Сделка выиграна",
                )
            )
    record_event(
        session, actor_type="user", action=f"crm.deal.win_{decision}",
        actor_user_id=user.id, organization_id=deal.organization_id,
        entity_type="deal", entity_id=deal.id, approval_id=approval.id,
        reason=comment, risk_level=deal.risk_level, commit=False,
    )
    session.commit()
    return deal


def lose_deal(
    session: Session,
    deal: Deal,
    *,
    user: User,
    loss_reason_id: uuid.UUID | None = None,
    comment: str | None = None,
) -> Deal:
    """Отмечает сделку проигранной (R2) с указанием причины для аналитики."""
    if deal.status != "open":
        raise CrmStateError(f"нельзя проиграть сделку из состояния '{deal.status}'")
    lost = _stage(session, deal.organization_id, lost=True)
    old = deal.pipeline_stage_id
    deal.status = "lost"
    deal.closed_at = datetime.now(UTC)
    deal.loss_reason_id = loss_reason_id
    deal.loss_comment = comment
    if lost is not None:
        deal.pipeline_stage_id = lost.id
        session.add(
            DealStageHistory(
                deal_id=deal.id, from_stage_id=old, to_stage_id=lost.id,
                changed_by=user.id, note="Сделка проиграна",
            )
        )
    record_event(
        session, actor_type="user", action="crm.deal.lost",
        actor_user_id=user.id, organization_id=deal.organization_id,
        entity_type="deal", entity_id=deal.id, reason=comment,
        new_values={"loss_reason_id": str(loss_reason_id) if loss_reason_id else None},
        risk_level="R2", commit=False,
    )
    session.commit()
    return deal


# ------------------------------ Договоры -------------------------------- #


def request_contract_approval(
    session: Session, contract: Contract, *, user: User
) -> Approval:
    """Запрашивает согласование договора (R3, крупный — R4)."""
    if contract.status not in ("draft",):
        raise CrmStateError(f"нельзя согласовать договор из состояния '{contract.status}'")
    threshold = deal_r4_threshold(session, contract.organization_id)
    risk = decision_risk_level(Decimal(contract.amount or 0), threshold=threshold)
    approval = Approval(
        organization_id=contract.organization_id, entity_type="contract",
        entity_id=contract.id, approval_type="contract_approval",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    contract.approval_id = approval.id
    contract.risk_level = risk
    contract.status = "pending_approval"
    record_event(
        session, actor_type="user", action="crm.contract.approval_requested",
        actor_user_id=user.id, organization_id=contract.organization_id,
        entity_type="contract", entity_id=contract.id, approval_id=approval.id,
        risk_level=risk, commit=False,
    )
    session.commit()
    return approval


def decide_contract(
    session: Session,
    contract: Contract,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
    mfa_verified: bool = False,
) -> Contract:
    """Фиксирует решение по договору. Крупный договор (R4) требует MFA."""
    if decision not in ("approved", "rejected"):
        raise CrmStateError(f"неизвестное решение '{decision}'")
    if contract.approval_id is None or contract.status != "pending_approval":
        raise CrmStateError("нет активного запроса на согласование договора")
    if decision == "approved" and contract.risk_level == "R4" and not mfa_verified:
        raise CrmAuthorizationError(
            "крупный договор (R4) требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, contract.approval_id)
    session.add(
        ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        )
    )
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    contract.status = "approved" if decision == "approved" else "draft"
    record_event(
        session, actor_type="user", action=f"crm.contract.{decision}",
        actor_user_id=user.id, organization_id=contract.organization_id,
        entity_type="contract", entity_id=contract.id, approval_id=approval.id,
        reason=comment, risk_level=contract.risk_level, commit=False,
    )
    session.commit()
    return contract


def sign_contract(
    session: Session, contract: Contract, *, user: User, signed_at: date | None = None
) -> Contract:
    """Фиксирует подписание утверждённого договора."""
    if contract.status not in ("approved",):
        raise CrmStateError("подписать можно только утверждённый договор")
    contract.status = "signed"
    contract.signed_at = signed_at or date.today()
    record_event(
        session, actor_type="user", action="crm.contract.signed",
        actor_user_id=user.id, organization_id=contract.organization_id,
        entity_type="contract", entity_id=contract.id,
        risk_level="R3", commit=False,
    )
    session.commit()
    return contract


# ------------------- Создание проекта из сделки ------------------------- #


def create_project_from_deal(
    session: Session,
    deal: Deal,
    *,
    user: User,
    contract: Contract,
    name: str | None = None,
    project_type: str = "construction",
) -> Project:
    """Создаёт проект из выигранной сделки при утверждённом/подписанном договоре.

    Проект создаётся только после выигранной сделки и утверждённого или
    подписанного договора (решение владельца).
    """
    if deal.status != "won":
        raise CrmValidationError("проект создаётся только по выигранной сделке")
    if contract.deal_id != deal.id:
        raise CrmValidationError("договор не относится к этой сделке")
    if contract.status not in ("approved", "signed", "active"):
        raise CrmValidationError(
            "для создания проекта договор должен быть утверждён или подписан"
        )
    if deal.project_id is not None:
        raise CrmStateError("проект по этой сделке уже создан")
    project = Project(
        organization_id=deal.organization_id,
        project_type=project_type,
        name=name or deal.title,
        customer_id=deal.counterparty_id,
        status="active",
        contract_amount=Decimal(contract.amount or deal.amount or 0),
        currency=deal.currency,
        created_by=user.id,
    )
    session.add(project)
    session.flush()
    deal.project_id = project.id
    contract.project_id = project.id
    if contract.status == "signed":
        contract.status = "active"
    record_event(
        session, actor_type="user", action="crm.project.created_from_deal",
        actor_user_id=user.id, organization_id=deal.organization_id,
        entity_type="project", entity_id=project.id,
        new_values={"deal_id": str(deal.id), "contract_id": str(contract.id)},
        risk_level="R3", commit=False,
    )
    session.commit()
    return project


# ----------------------- Сообщение → задача ----------------------------- #


def create_task_from_communication(
    session: Session,
    comm: Communication,
    *,
    user: User,
    title: str,
    owner_employee_id: uuid.UUID | None = None,
) -> Task:
    """Порождает задачу из коммуникации (единый центр коммуникаций → задачи)."""
    task = Task(
        organization_id=comm.organization_id,
        project_id=comm.project_id,
        source_type="communication",
        source_id=comm.id,
        title=title,
        status="draft",
        owner_employee_id=owner_employee_id or comm.responsible_employee_id,
        created_by_user_id=user.id,
    )
    session.add(task)
    session.flush()
    comm.linked_task_id = task.id
    comm.processing_status = "task_created"
    record_event(
        session, actor_type="user", action="crm.communication.task_created",
        actor_user_id=user.id, organization_id=comm.organization_id,
        entity_type="communication", entity_id=comm.id,
        new_values={"task_id": str(task.id)}, commit=False,
    )
    session.commit()
    return task


# ------------------------- Аналитика продаж ----------------------------- #


@dataclass
class StageFunnelRow:
    stage_id: uuid.UUID
    name: str
    sort_order: int
    deals_count: int
    amount: Decimal


@dataclass
class ManagerRow:
    employee_id: uuid.UUID | None
    deals_total: int
    won_count: int
    won_amount: Decimal
    target_amount: Decimal
    plan_fact_percent: Decimal


@dataclass
class LossReasonRow:
    reason_id: uuid.UUID | None
    count: int
    amount: Decimal


@dataclass
class SalesAnalytics:
    deals_total: int
    open_count: int
    won_count: int
    lost_count: int
    open_amount: Decimal
    won_amount: Decimal
    lost_amount: Decimal
    conversion_percent: Decimal
    funnel: list[StageFunnelRow] = field(default_factory=list)
    loss_reasons: list[LossReasonRow] = field(default_factory=list)
    managers: list[ManagerRow] = field(default_factory=list)


def sales_analytics(
    session: Session,
    organization_id: uuid.UUID,
    *,
    period_year: int | None = None,
) -> SalesAnalytics:
    """Сводная аналитика продаж по организации (без дублирования сущностей)."""
    deals = list(
        session.execute(
            select(Deal).where(
                Deal.organization_id == organization_id,
                Deal.deleted_at.is_(None),
            )
        ).scalars()
    )
    open_deals = [d for d in deals if d.status == "open"]
    won = [d for d in deals if d.status == "won"]
    lost = [d for d in deals if d.status == "lost"]

    def _sum(items: list[Deal]) -> Decimal:
        return sum((Decimal(d.amount or 0) for d in items), Decimal("0"))

    closed = len(won) + len(lost)
    conversion = (
        (Decimal(len(won)) / Decimal(closed) * Decimal(100)).quantize(Decimal("0.01"))
        if closed
        else Decimal("0.00")
    )

    # Воронка по этапам (открытые сделки).
    stages = list(
        session.execute(
            select(PipelineStage).where(
                PipelineStage.organization_id == organization_id,
                PipelineStage.deleted_at.is_(None),
            ).order_by(PipelineStage.sort_order)
        ).scalars()
    )
    funnel: list[StageFunnelRow] = []
    for st in stages:
        in_stage = [d for d in deals if d.pipeline_stage_id == st.id]
        funnel.append(
            StageFunnelRow(
                stage_id=st.id, name=st.name, sort_order=st.sort_order,
                deals_count=len(in_stage), amount=_sum(in_stage),
            )
        )

    # Причины проигрыша.
    loss_map: dict[uuid.UUID | None, list[Deal]] = {}
    for d in lost:
        loss_map.setdefault(d.loss_reason_id, []).append(d)
    loss_reasons = [
        LossReasonRow(reason_id=rid, count=len(items), amount=_sum(items))
        for rid, items in loss_map.items()
    ]

    # Показатели по ответственным менеджерам + план-факт (цели/выигрыши).
    targets = list(
        session.execute(
            select(SalesTarget).where(
                SalesTarget.organization_id == organization_id,
                SalesTarget.deleted_at.is_(None),
            )
        ).scalars()
    )
    target_by_emp: dict[uuid.UUID, Decimal] = {}
    for t in targets:
        if period_year is not None and t.period_year != period_year:
            continue
        target_by_emp[t.employee_id] = target_by_emp.get(
            t.employee_id, Decimal("0")
        ) + Decimal(t.target_amount or 0)

    emp_ids = {d.responsible_employee_id for d in deals} | set(target_by_emp)
    managers: list[ManagerRow] = []
    for emp in emp_ids:
        emp_deals = [d for d in deals if d.responsible_employee_id == emp]
        emp_won = [d for d in emp_deals if d.status == "won"]
        won_amount = _sum(emp_won)
        target = target_by_emp.get(emp, Decimal("0")) if emp else Decimal("0")
        plan_fact = (
            (won_amount / target * Decimal(100)).quantize(Decimal("0.01"))
            if target > 0
            else Decimal("0.00")
        )
        managers.append(
            ManagerRow(
                employee_id=emp, deals_total=len(emp_deals),
                won_count=len(emp_won), won_amount=won_amount,
                target_amount=target, plan_fact_percent=plan_fact,
            )
        )

    return SalesAnalytics(
        deals_total=len(deals), open_count=len(open_deals),
        won_count=len(won), lost_count=len(lost),
        open_amount=_sum(open_deals), won_amount=_sum(won), lost_amount=_sum(lost),
        conversion_percent=conversion, funnel=funnel,
        loss_reasons=loss_reasons, managers=managers,
    )


# ------------------------------ Доступ ---------------------------------- #


def can_access_deal_project(session: Session, user: User, deal: Deal) -> bool:
    """ABAC для сделки: если сделка привязана к проекту — проверяем доступ."""
    if deal.project_id is None:
        return True
    return can_access_project(session, user, deal.project_id)


def get_counterparty(session: Session, org_id: uuid.UUID, cp_id: uuid.UUID) -> Counterparty | None:
    cp = session.get(Counterparty, cp_id)
    if cp is None or cp.deleted_at is not None or cp.organization_id != org_id:
        return None
    return cp
