"""API модуля «Ядро CRM».

Backend — единственная точка доступа к данным. Все действия проходят серверную
проверку прав (RBAC) и изоляцию по организации/проекту (ABAC). Обычные операции —
R2; выигрыш сделки и подписание договора — R3; крупная сделка/договор — R4 + MFA
(порог настраивается для организации). Телефоны и e-mail контактов маскируются
для пользователей без права `crm.contact.pii`. Все значимые действия — в
`audit_events`. Денежные значения — Decimal, в ответах сериализуются строкой.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    Communication,
    Contract,
    Counterparty,
    CounterpartyContact,
    Deal,
    DealLossReason,
    Employee,
    Lead,
    LeadSource,
    PipelineStage,
    SalesTarget,
    User,
)
from app.schemas.crm import (
    AnalyticsOut,
    CommTaskIn,
    CommunicationIn,
    CommunicationOut,
    ContactIn,
    ContactOut,
    ContractIn,
    ContractOut,
    CounterpartyIn,
    CounterpartyOut,
    CreateProjectIn,
    DealIn,
    DealOut,
    DecisionIn,
    FunnelRowOut,
    LeadConvertIn,
    LeadIn,
    LeadOut,
    LeadSourceIn,
    LeadSourceOut,
    LossReasonIn,
    LossReasonOut,
    LoseDealIn,
    ManagerRowOut,
    MoveStageIn,
    SalesTargetIn,
    SalesTargetOut,
    SignContractIn,
    StageIn,
    StageOut,
)
from app.schemas.crm import LossReasonRowOut
from app.services import crm as svc
from app.services.auth import verify_totp

router = APIRouter(prefix="/crm", tags=["crm"])


# ------------------------------ Помощники ------------------------------- #


def _org_id(db: Session, user: User) -> uuid.UUID:
    """Организация пользователя (CRM-сущности изолируются по организации)."""
    if user.employee_id is None:
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником"
        )
    emp = db.get(Employee, user.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сотрудник не найден")
    return emp.organization_id


def _counterparty(db: Session, org_id: uuid.UUID, cp_id: uuid.UUID) -> Counterparty:
    cp = svc.get_counterparty(db, org_id, cp_id)
    if cp is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Контрагент не найден")
    return cp


def _deal(db: Session, org_id: uuid.UUID, user: User, deal_id: uuid.UUID) -> Deal:
    deal = db.get(Deal, deal_id)
    if deal is None or deal.deleted_at is not None or deal.organization_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Сделка не найдена")
    if not svc.can_access_deal_project(db, user, deal):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту сделки")
    return deal


def _contract(db: Session, org_id: uuid.UUID, contract_id: uuid.UUID) -> Contract:
    c = db.get(Contract, contract_id)
    if c is None or c.deleted_at is not None or c.organization_id != org_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Договор не найден")
    return c


def _require_mfa(user: User, mfa_code: str | None) -> bool:
    if not user.mfa_enabled or not user.mfa_secret or not mfa_code:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Для уровня R4 требуется код MFA")
    if not verify_totp(user.mfa_secret, mfa_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
    return True


# ------------------------------ Воронка --------------------------------- #


def _stage_out(s: PipelineStage) -> StageOut:
    return StageOut(
        id=s.id, code=s.code, name=s.name, sort_order=s.sort_order,
        probability_percent=str(s.probability_percent), is_won=s.is_won,
        is_lost=s.is_lost, status=s.status,
    )


@router.get("/pipeline/stages", response_model=list[StageOut])
def list_stages(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[StageOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(PipelineStage).where(
            PipelineStage.organization_id == org,
            PipelineStage.deleted_at.is_(None),
        ).order_by(PipelineStage.sort_order)
    ).scalars()
    return [_stage_out(s) for s in rows]


@router.post("/pipeline/init", response_model=list[StageOut])
def init_pipeline(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> list[StageOut]:
    org = _org_id(db, user)
    stages = svc.ensure_default_pipeline(db, org)
    return [_stage_out(s) for s in stages]


@router.post("/pipeline/stages", response_model=StageOut, status_code=status.HTTP_201_CREATED)
def create_stage(
    payload: StageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> StageOut:
    org = _org_id(db, user)
    s = PipelineStage(
        organization_id=org, code=payload.code, name=payload.name,
        sort_order=payload.sort_order,
        probability_percent=Decimal(str(payload.probability_percent)),
        is_won=payload.is_won, is_lost=payload.is_lost, created_by=user.id,
    )
    db.add(s)
    db.commit()
    return _stage_out(s)


# ------------------------------ Справочники ----------------------------- #


@router.get("/lead-sources", response_model=list[LeadSourceOut])
def list_lead_sources(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[LeadSourceOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(LeadSource).where(
            LeadSource.organization_id == org, LeadSource.deleted_at.is_(None)
        )
    ).scalars()
    return [LeadSourceOut(id=r.id, code=r.code, name=r.name, status=r.status) for r in rows]


@router.post("/lead-sources", response_model=LeadSourceOut, status_code=status.HTTP_201_CREATED)
def create_lead_source(
    payload: LeadSourceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> LeadSourceOut:
    org = _org_id(db, user)
    r = LeadSource(organization_id=org, code=payload.code, name=payload.name, created_by=user.id)
    db.add(r)
    db.commit()
    return LeadSourceOut(id=r.id, code=r.code, name=r.name, status=r.status)


@router.get("/loss-reasons", response_model=list[LossReasonOut])
def list_loss_reasons(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[LossReasonOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(DealLossReason).where(
            DealLossReason.organization_id == org, DealLossReason.deleted_at.is_(None)
        )
    ).scalars()
    return [LossReasonOut(id=r.id, code=r.code, name=r.name, status=r.status) for r in rows]


@router.post("/loss-reasons", response_model=LossReasonOut, status_code=status.HTTP_201_CREATED)
def create_loss_reason(
    payload: LossReasonIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> LossReasonOut:
    org = _org_id(db, user)
    r = DealLossReason(organization_id=org, code=payload.code, name=payload.name, created_by=user.id)
    db.add(r)
    db.commit()
    return LossReasonOut(id=r.id, code=r.code, name=r.name, status=r.status)


# ------------------------------ Контрагенты ----------------------------- #


@router.get("/counterparties", response_model=list[CounterpartyOut])
def list_counterparties(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[CounterpartyOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(Counterparty).where(
            Counterparty.organization_id == org, Counterparty.deleted_at.is_(None)
        )
    ).scalars()
    return [
        CounterpartyOut(id=c.id, name=c.name, inn=c.inn,
                        counterparty_type=c.counterparty_type, status=c.status)
        for c in rows
    ]


@router.post("/counterparties", response_model=CounterpartyOut, status_code=status.HTTP_201_CREATED)
def create_counterparty(
    payload: CounterpartyIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> CounterpartyOut:
    org = _org_id(db, user)
    c = Counterparty(
        organization_id=org, name=payload.name, inn=payload.inn,
        counterparty_type=payload.counterparty_type, created_by=user.id,
    )
    db.add(c)
    db.commit()
    return CounterpartyOut(id=c.id, name=c.name, inn=c.inn,
                           counterparty_type=c.counterparty_type, status=c.status)


def _contact_out(c: CounterpartyContact, *, allowed: bool) -> ContactOut:
    return ContactOut(
        id=c.id, counterparty_id=c.counterparty_id, full_name=c.full_name,
        position=c.position,
        email=svc.apply_pii(c.email, allowed=allowed, kind="email"),
        phone=svc.apply_pii(c.phone, allowed=allowed, kind="phone"),
        messenger=c.messenger, is_primary=c.is_primary,
        consent_given=c.consent_given, consent_date=c.consent_date,
        pii_masked=not allowed, status=c.status,
    )


@router.get("/counterparties/{counterparty_id}/contacts", response_model=list[ContactOut])
def list_contacts(
    counterparty_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[ContactOut]:
    org = _org_id(db, user)
    _counterparty(db, org, counterparty_id)
    allowed = svc.user_can_view_pii(db, user)
    rows = db.execute(
        select(CounterpartyContact).where(
            CounterpartyContact.counterparty_id == counterparty_id,
            CounterpartyContact.deleted_at.is_(None),
        )
    ).scalars()
    return [_contact_out(c, allowed=allowed) for c in rows]


@router.post(
    "/counterparties/{counterparty_id}/contacts",
    response_model=ContactOut,
    status_code=status.HTTP_201_CREATED,
)
def create_contact(
    counterparty_id: uuid.UUID,
    payload: ContactIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> ContactOut:
    org = _org_id(db, user)
    _counterparty(db, org, counterparty_id)
    c = CounterpartyContact(
        organization_id=org, counterparty_id=counterparty_id,
        full_name=payload.full_name, position=payload.position,
        email=payload.email, phone=payload.phone, messenger=payload.messenger,
        is_primary=payload.is_primary, consent_given=payload.consent_given,
        consent_date=payload.consent_date, created_by=user.id,
    )
    db.add(c)
    db.commit()
    return _contact_out(c, allowed=svc.user_can_view_pii(db, user))


# ------------------------------- Лиды ----------------------------------- #


def _lead_out(lead: Lead, *, allowed: bool) -> LeadOut:
    return LeadOut(
        id=lead.id, number=lead.number, title=lead.title, status=lead.status,
        lead_source_id=lead.lead_source_id, counterparty_id=lead.counterparty_id,
        contact_name=lead.contact_name,
        contact_phone=svc.apply_pii(lead.contact_phone, allowed=allowed, kind="phone"),
        contact_email=svc.apply_pii(lead.contact_email, allowed=allowed, kind="email"),
        company_name=lead.company_name,
        estimated_amount=str(lead.estimated_amount or 0), currency=lead.currency,
        responsible_employee_id=lead.responsible_employee_id,
        converted_deal_id=lead.converted_deal_id, pii_masked=not allowed,
    )


@router.get("/leads", response_model=list[LeadOut])
def list_leads(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[LeadOut]:
    org = _org_id(db, user)
    allowed = svc.user_can_view_pii(db, user)
    rows = db.execute(
        select(Lead).where(Lead.organization_id == org, Lead.deleted_at.is_(None))
    ).scalars()
    return [_lead_out(x, allowed=allowed) for x in rows]


@router.post("/leads", response_model=LeadOut, status_code=status.HTTP_201_CREATED)
def create_lead(
    payload: LeadIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> LeadOut:
    org = _org_id(db, user)
    lead = Lead(
        organization_id=org, title=payload.title, description=payload.description,
        lead_source_id=payload.lead_source_id, counterparty_id=payload.counterparty_id,
        contact_name=payload.contact_name, contact_phone=payload.contact_phone,
        contact_email=payload.contact_email, company_name=payload.company_name,
        estimated_amount=Decimal(str(payload.estimated_amount)), currency=payload.currency,
        responsible_employee_id=payload.responsible_employee_id, created_by=user.id,
    )
    db.add(lead)
    db.commit()
    return _lead_out(lead, allowed=svc.user_can_view_pii(db, user))


@router.post("/leads/{lead_id}/convert", response_model=DealOut, status_code=status.HTTP_201_CREATED)
def convert_lead(
    lead_id: uuid.UUID,
    payload: LeadConvertIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> DealOut:
    org = _org_id(db, user)
    lead = db.get(Lead, lead_id)
    if lead is None or lead.deleted_at is not None or lead.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Лид не найден")
    try:
        deal = svc.convert_lead_to_deal(
            db, lead, user=user, counterparty_id=payload.counterparty_id,
            amount=Decimal(str(payload.amount)) if payload.amount is not None else None,
            responsible_employee_id=payload.responsible_employee_id,
        )
    except svc.CrmValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _deal_out(deal)


# ------------------------------ Сделки ---------------------------------- #


def _deal_out(d: Deal) -> DealOut:
    return DealOut(
        id=d.id, number=d.number, title=d.title, counterparty_id=d.counterparty_id,
        lead_id=d.lead_id, pipeline_stage_id=d.pipeline_stage_id,
        commercial_offer_id=d.commercial_offer_id, contract_id=d.contract_id,
        project_id=d.project_id, amount=str(d.amount), currency=d.currency,
        status=d.status, risk_level=d.risk_level,
        responsible_employee_id=d.responsible_employee_id,
        expected_close_date=d.expected_close_date, loss_reason_id=d.loss_reason_id,
        approval_id=d.approval_id,
    )


@router.get("/deals", response_model=list[DealOut])
def list_deals(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[DealOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(Deal).where(Deal.organization_id == org, Deal.deleted_at.is_(None))
    ).scalars()
    return [_deal_out(d) for d in rows if svc.can_access_deal_project(db, user, d)]


@router.post("/deals", response_model=DealOut, status_code=status.HTTP_201_CREATED)
def create_deal(
    payload: DealIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> DealOut:
    org = _org_id(db, user)
    _counterparty(db, org, payload.counterparty_id)
    deal = Deal(
        organization_id=org, counterparty_id=payload.counterparty_id,
        title=payload.title, description=payload.description,
        amount=Decimal(str(payload.amount)), currency=payload.currency,
        pipeline_stage_id=payload.pipeline_stage_id,
        commercial_offer_id=payload.commercial_offer_id,
        responsible_employee_id=payload.responsible_employee_id,
        expected_close_date=payload.expected_close_date, created_by=user.id,
    )
    db.add(deal)
    db.commit()
    return _deal_out(deal)


@router.get("/deals/{deal_id}", response_model=DealOut)
def get_deal(
    deal_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> DealOut:
    org = _org_id(db, user)
    return _deal_out(_deal(db, org, user, deal_id))


@router.post("/deals/{deal_id}/move-stage", response_model=DealOut)
def move_stage(
    deal_id: uuid.UUID,
    payload: MoveStageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> DealOut:
    org = _org_id(db, user)
    deal = _deal(db, org, user, deal_id)
    stage = db.get(PipelineStage, payload.pipeline_stage_id)
    if stage is None or stage.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Этап воронки не найден")
    try:
        svc.move_deal_stage(db, deal, user=user, stage=stage, note=payload.note)
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _deal_out(deal)


@router.post("/deals/{deal_id}/request-win", response_model=DealOut)
def request_win(
    deal_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> DealOut:
    org = _org_id(db, user)
    deal = _deal(db, org, user, deal_id)
    try:
        svc.request_deal_win(db, deal, user=user)
    except svc.CrmValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _deal_out(deal)


@router.post("/deals/{deal_id}/win-decision", response_model=DealOut)
def win_decision(
    deal_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("deal.approve")),
) -> DealOut:
    org = _org_id(db, user)
    deal = _deal(db, org, user, deal_id)
    mfa_verified = False
    if deal.risk_level == "R4" and payload.decision == "approved":
        mfa_verified = _require_mfa(user, payload.mfa_code)
    try:
        svc.decide_deal_win(
            db, deal, user=user, decision=payload.decision,
            comment=payload.comment, mfa_verified=mfa_verified,
        )
    except (svc.CrmStateError, svc.CrmAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _deal_out(deal)


@router.post("/deals/{deal_id}/lose", response_model=DealOut)
def lose(
    deal_id: uuid.UUID,
    payload: LoseDealIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> DealOut:
    org = _org_id(db, user)
    deal = _deal(db, org, user, deal_id)
    try:
        svc.lose_deal(db, deal, user=user, loss_reason_id=payload.loss_reason_id, comment=payload.comment)
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _deal_out(deal)


@router.post("/deals/{deal_id}/create-project", response_model=DealOut, status_code=status.HTTP_201_CREATED)
def create_project(
    deal_id: uuid.UUID,
    payload: CreateProjectIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("deal.approve")),
) -> DealOut:
    org = _org_id(db, user)
    deal = _deal(db, org, user, deal_id)
    contract = _contract(db, org, payload.contract_id)
    try:
        svc.create_project_from_deal(
            db, deal, user=user, contract=contract,
            name=payload.name, project_type=payload.project_type,
        )
    except svc.CrmValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _deal_out(deal)


# ------------------------------ Договоры -------------------------------- #


def _contract_out(c: Contract) -> ContractOut:
    return ContractOut(
        id=c.id, counterparty_id=c.counterparty_id, deal_id=c.deal_id,
        commercial_offer_id=c.commercial_offer_id, project_id=c.project_id,
        contract_type=c.contract_type, number=c.number, subject=c.subject,
        amount=str(c.amount), currency=c.currency, status=c.status,
        risk_level=c.risk_level, signed_at=c.signed_at, approval_id=c.approval_id,
    )


@router.get("/contracts", response_model=list[ContractOut])
def list_contracts(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[ContractOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(Contract).where(Contract.organization_id == org, Contract.deleted_at.is_(None))
    ).scalars()
    return [_contract_out(c) for c in rows]


@router.post("/contracts", response_model=ContractOut, status_code=status.HTTP_201_CREATED)
def create_contract(
    payload: ContractIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> ContractOut:
    org = _org_id(db, user)
    _counterparty(db, org, payload.counterparty_id)
    c = Contract(
        organization_id=org, counterparty_id=payload.counterparty_id,
        deal_id=payload.deal_id, commercial_offer_id=payload.commercial_offer_id,
        document_id=payload.document_id, contract_type=payload.contract_type,
        number=payload.number, subject=payload.subject,
        amount=Decimal(str(payload.amount)), currency=payload.currency,
        payment_terms=payload.payment_terms, start_date=payload.start_date,
        end_date=payload.end_date, responsible_employee_id=payload.responsible_employee_id,
        created_by=user.id,
    )
    db.add(c)
    db.commit()
    return _contract_out(c)


@router.post("/contracts/{contract_id}/request-approval", response_model=ContractOut)
def request_contract_approval(
    contract_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> ContractOut:
    org = _org_id(db, user)
    c = _contract(db, org, contract_id)
    try:
        svc.request_contract_approval(db, c, user=user)
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _contract_out(c)


@router.post("/contracts/{contract_id}/decision", response_model=ContractOut)
def decide_contract(
    contract_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("deal.approve")),
) -> ContractOut:
    org = _org_id(db, user)
    c = _contract(db, org, contract_id)
    mfa_verified = False
    if c.risk_level == "R4" and payload.decision == "approved":
        mfa_verified = _require_mfa(user, payload.mfa_code)
    try:
        svc.decide_contract(
            db, c, user=user, decision=payload.decision,
            comment=payload.comment, mfa_verified=mfa_verified,
        )
    except (svc.CrmStateError, svc.CrmAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _contract_out(c)


@router.post("/contracts/{contract_id}/sign", response_model=ContractOut)
def sign_contract(
    contract_id: uuid.UUID,
    payload: SignContractIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("deal.approve")),
) -> ContractOut:
    org = _org_id(db, user)
    c = _contract(db, org, contract_id)
    try:
        svc.sign_contract(db, c, user=user, signed_at=payload.signed_at)
    except svc.CrmStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _contract_out(c)


# ------------------------- Коммуникации --------------------------------- #


def _comm_out(c: Communication) -> CommunicationOut:
    return CommunicationOut(
        id=c.id, channel=c.channel, direction=c.direction,
        counterparty_id=c.counterparty_id, deal_id=c.deal_id, subject=c.subject,
        processing_status=c.processing_status, linked_task_id=c.linked_task_id,
    )


@router.get("/communications", response_model=list[CommunicationOut])
def list_communications(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[CommunicationOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(Communication).where(
            Communication.organization_id == org, Communication.deleted_at.is_(None)
        ).order_by(Communication.created_at.desc())
    ).scalars()
    return [_comm_out(c) for c in rows]


@router.post("/communications", response_model=CommunicationOut, status_code=status.HTTP_201_CREATED)
def create_communication(
    payload: CommunicationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> CommunicationOut:
    org = _org_id(db, user)
    c = Communication(
        organization_id=org, channel=payload.channel, direction=payload.direction,
        counterparty_id=payload.counterparty_id, contact_id=payload.contact_id,
        lead_id=payload.lead_id, deal_id=payload.deal_id, project_id=payload.project_id,
        subject=payload.subject, body_text=payload.body_text,
        responsible_employee_id=payload.responsible_employee_id, created_by=user.id,
    )
    db.add(c)
    db.commit()
    return _comm_out(c)


@router.post("/communications/{comm_id}/create-task", response_model=CommunicationOut)
def communication_create_task(
    comm_id: uuid.UUID,
    payload: CommTaskIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> CommunicationOut:
    org = _org_id(db, user)
    c = db.get(Communication, comm_id)
    if c is None or c.deleted_at is not None or c.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Коммуникация не найдена")
    svc.create_task_from_communication(
        db, c, user=user, title=payload.title, owner_employee_id=payload.owner_employee_id
    )
    return _comm_out(c)


# --------------------------- Цели менеджеров ---------------------------- #


@router.get("/sales-targets", response_model=list[SalesTargetOut])
def list_targets(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> list[SalesTargetOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(SalesTarget).where(
            SalesTarget.organization_id == org, SalesTarget.deleted_at.is_(None)
        )
    ).scalars()
    return [
        SalesTargetOut(
            id=t.id, employee_id=t.employee_id, period_year=t.period_year,
            period_month=t.period_month, target_amount=str(t.target_amount),
            target_deals_count=t.target_deals_count, currency=t.currency,
        )
        for t in rows
    ]


@router.post("/sales-targets", response_model=SalesTargetOut, status_code=status.HTTP_201_CREATED)
def create_target(
    payload: SalesTargetIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.manage")),
) -> SalesTargetOut:
    org = _org_id(db, user)
    t = SalesTarget(
        organization_id=org, employee_id=payload.employee_id,
        period_year=payload.period_year, period_month=payload.period_month,
        target_amount=Decimal(str(payload.target_amount)),
        target_deals_count=payload.target_deals_count, currency=payload.currency,
        created_by=user.id,
    )
    db.add(t)
    db.commit()
    return SalesTargetOut(
        id=t.id, employee_id=t.employee_id, period_year=t.period_year,
        period_month=t.period_month, target_amount=str(t.target_amount),
        target_deals_count=t.target_deals_count, currency=t.currency,
    )


# ------------------------------ Аналитика ------------------------------- #


@router.get("/analytics/summary", response_model=AnalyticsOut)
def analytics_summary(
    period_year: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("crm.view")),
) -> AnalyticsOut:
    org = _org_id(db, user)
    a = svc.sales_analytics(db, org, period_year=period_year)
    return AnalyticsOut(
        deals_total=a.deals_total, open_count=a.open_count, won_count=a.won_count,
        lost_count=a.lost_count, open_amount=str(a.open_amount),
        won_amount=str(a.won_amount), lost_amount=str(a.lost_amount),
        conversion_percent=str(a.conversion_percent),
        funnel=[
            FunnelRowOut(stage_id=r.stage_id, name=r.name, sort_order=r.sort_order,
                         deals_count=r.deals_count, amount=str(r.amount))
            for r in a.funnel
        ],
        loss_reasons=[
            LossReasonRowOut(reason_id=r.reason_id, count=r.count, amount=str(r.amount))
            for r in a.loss_reasons
        ],
        managers=[
            ManagerRowOut(
                employee_id=r.employee_id, deals_total=r.deals_total,
                won_count=r.won_count, won_amount=str(r.won_amount),
                target_amount=str(r.target_amount),
                plan_fact_percent=str(r.plan_fact_percent),
            )
            for r in a.managers
        ],
    )
