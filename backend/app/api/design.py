"""API модуля «Проектирование и дизайн».

Backend — единственная точка доступа к данным (ARCHITECTURE.md раздел 5.2).
Все действия проходят серверную проверку прав (RBAC) и изоляцию по проекту
(ABAC). Выпуск документации — R3 (подтверждение человека), аннулирование — R4
с MFA; замечания превращаются в задачи; все действия — в `audit_events`.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    Approval,
    Counterparty,
    DesignBrief,
    DesignConcept,
    DesignIssue,
    DesignSpecification,
    Material,
    Project,
    ProjectDiscipline,
    Supplier,
    User,
)
from app.schemas.design import (
    AnnulIn,
    BriefIn,
    BriefOut,
    ConceptIn,
    ConceptOut,
    DisciplineIn,
    DisciplineOut,
    IssueIn,
    IssueOut,
    MaterialOut,
    ProjectDesignOverview,
    RealizabilityOut,
    ReleaseDecisionIn,
    ReleaseRequestIn,
    SpecificationIn,
    SpecificationOut,
    SupplierOut,
)
from app.services import design as svc
from app.services.auth import verify_totp

router = APIRouter(prefix="/design", tags=["design"])


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    if not svc.can_access_project_id(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return project


# ------------------------------- Разделы --------------------------------- #


def _discipline_out(d: ProjectDiscipline) -> DisciplineOut:
    return DisciplineOut(
        id=d.id, project_id=d.project_id, code=d.code, name=d.name,
        discipline_type=d.discipline_type,
        responsible_employee_id=d.responsible_employee_id, due_date=d.due_date,
        completion_percent=d.completion_percent, gip_status=d.gip_status,
        status=d.status,
    )


@router.get("/projects/{project_id}/disciplines", response_model=list[DisciplineOut])
def list_disciplines(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.view")),
) -> list[DisciplineOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(ProjectDiscipline).where(
            ProjectDiscipline.project_id == project_id,
            ProjectDiscipline.deleted_at.is_(None),
        )
    ).scalars()
    return [_discipline_out(d) for d in rows]


@router.post(
    "/projects/{project_id}/disciplines",
    response_model=DisciplineOut,
    status_code=status.HTTP_201_CREATED,
)
def create_discipline(
    project_id: uuid.UUID,
    payload: DisciplineIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.manage")),
) -> DisciplineOut:
    _project(db, user, project_id)
    d = ProjectDiscipline(
        project_id=project_id, code=payload.code, name=payload.name,
        discipline_type=payload.discipline_type,
        responsible_employee_id=payload.responsible_employee_id,
        due_date=payload.due_date, completion_percent=payload.completion_percent,
        milestone_id=payload.milestone_id, created_by=user.id,
    )
    db.add(d)
    db.flush()
    svc.record_event(
        db, actor_type="user", action="design.discipline.created",
        actor_user_id=user.id, entity_type="project_discipline", entity_id=d.id,
        new_values={"name": payload.name}, commit=False,
    )
    db.commit()
    return _discipline_out(d)


# -------------------------------- Бриф/ТЗ -------------------------------- #


def _brief_out(b: DesignBrief) -> BriefOut:
    return BriefOut(
        id=b.id, project_id=b.project_id, title=b.title,
        client_requirements=b.client_requirements,
        functional_requirements=b.functional_requirements,
        style_preferences=b.style_preferences, budget_range=b.budget_range,
        target_completion_date=b.target_completion_date, status=b.status,
    )


@router.get("/projects/{project_id}/brief", response_model=BriefOut | None)
def get_brief(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.view")),
) -> BriefOut | None:
    _project(db, user, project_id)
    b = db.execute(
        select(DesignBrief).where(
            DesignBrief.project_id == project_id, DesignBrief.deleted_at.is_(None)
        )
    ).scalars().first()
    return _brief_out(b) if b else None


@router.post(
    "/projects/{project_id}/brief",
    response_model=BriefOut,
    status_code=status.HTTP_201_CREATED,
)
def create_brief(
    project_id: uuid.UUID,
    payload: BriefIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.manage")),
) -> BriefOut:
    project = _project(db, user, project_id)
    b = DesignBrief(
        organization_id=project.organization_id, project_id=project_id,
        title=payload.title, client_requirements=payload.client_requirements,
        functional_requirements=payload.functional_requirements,
        style_preferences=payload.style_preferences,
        budget_range=payload.budget_range,
        target_completion_date=payload.target_completion_date, created_by=user.id,
    )
    db.add(b)
    db.commit()
    return _brief_out(b)


@router.post("/briefs/{brief_id}/approve", response_model=BriefOut)
def approve_brief(
    brief_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.brief.approve")),
) -> BriefOut:
    b = db.get(DesignBrief, brief_id)
    if b is None or b.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "ТЗ не найдено")
    _project(db, user, b.project_id)
    try:
        svc.approve_brief(db, b, user=user)
    except svc.DesignStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _brief_out(b)


# ------------------------------ Концепции -------------------------------- #


@router.get("/projects/{project_id}/concepts", response_model=list[ConceptOut])
def list_concepts(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.view")),
) -> list[ConceptOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(DesignConcept).where(
            DesignConcept.project_id == project_id,
            DesignConcept.deleted_at.is_(None),
        )
    ).scalars()
    return [
        ConceptOut(id=c.id, name=c.name, description=c.description, version=c.version,
                   status=c.status, client_feedback=c.client_feedback)
        for c in rows
    ]


@router.post(
    "/projects/{project_id}/concepts",
    response_model=ConceptOut,
    status_code=status.HTTP_201_CREATED,
)
def create_concept(
    project_id: uuid.UUID,
    payload: ConceptIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.manage")),
) -> ConceptOut:
    _project(db, user, project_id)
    c = DesignConcept(
        project_id=project_id, name=payload.name, description=payload.description,
        prepared_by=user.id, created_by=user.id,
    )
    db.add(c)
    db.commit()
    return ConceptOut(id=c.id, name=c.name, description=c.description,
                      version=c.version, status=c.status, client_feedback=c.client_feedback)


# ----------------------------- Спецификации ------------------------------ #


def _spec_out(s: DesignSpecification) -> SpecificationOut:
    return SpecificationOut(
        id=s.id, project_id=s.project_id, category=s.category,
        material_id=s.material_id, supplier_product_id=s.supplier_product_id,
        custom_description=s.custom_description, quantity=str(s.quantity),
        unit=s.unit,
        planned_unit_price=str(s.planned_unit_price) if s.planned_unit_price is not None else None,
        approved_analog_allowed=s.approved_analog_allowed, status=s.status,
    )


@router.get(
    "/projects/{project_id}/specifications", response_model=list[SpecificationOut]
)
def list_specifications(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.view")),
) -> list[SpecificationOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(DesignSpecification).where(
            DesignSpecification.project_id == project_id,
            DesignSpecification.deleted_at.is_(None),
        )
    ).scalars()
    return [_spec_out(s) for s in rows]


@router.post(
    "/projects/{project_id}/specifications",
    response_model=SpecificationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_specification(
    project_id: uuid.UUID,
    payload: SpecificationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.manage")),
) -> SpecificationOut:
    _project(db, user, project_id)
    s = DesignSpecification(
        project_id=project_id, concept_id=payload.concept_id,
        location_id=payload.location_id, category=payload.category,
        material_id=payload.material_id,
        supplier_product_id=payload.supplier_product_id,
        custom_description=payload.custom_description, quantity=payload.quantity,
        unit=payload.unit, planned_unit_price=payload.planned_unit_price,
        created_by=user.id,
    )
    db.add(s)
    db.commit()
    return _spec_out(s)


@router.post(
    "/specifications/{spec_id}/realizability", response_model=RealizabilityOut
)
def check_realizability(
    spec_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.manage")),
) -> RealizabilityOut:
    s = db.get(DesignSpecification, spec_id)
    if s is None or s.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Спецификация не найдена")
    _project(db, user, s.project_id)
    check = svc.run_realizability_check(db, s, user=user)
    return RealizabilityOut(
        id=check.id, design_specification_id=check.design_specification_id,
        availability_status=check.availability_status,
        supplier_count=check.supplier_count,
        minimum_price=str(check.minimum_price) if check.minimum_price is not None else None,
        maximum_price=str(check.maximum_price) if check.maximum_price is not None else None,
        lead_time_days=check.lead_time_days,
        regional_delivery_possible=check.regional_delivery_possible,
        recommended_option=check.recommended_option, risk_notes=check.risk_notes,
        source=check.source,
    )


# ------------------------------- Замечания ------------------------------- #


@router.get("/projects/{project_id}/issues", response_model=list[IssueOut])
def list_issues(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.view")),
) -> list[IssueOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(DesignIssue).where(
            DesignIssue.project_id == project_id, DesignIssue.deleted_at.is_(None)
        )
    ).scalars()
    return [
        IssueOut(
            id=i.id, project_id=i.project_id, source=i.source, title=i.title,
            severity=i.severity, status=i.status, due_date=i.due_date,
            responsible_employee_id=i.responsible_employee_id,
            linked_task_id=i.linked_task_id,
        )
        for i in rows
    ]


@router.post(
    "/projects/{project_id}/issues",
    response_model=IssueOut,
    status_code=status.HTTP_201_CREATED,
)
def create_issue(
    project_id: uuid.UUID,
    payload: IssueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.issue.manage")),
) -> IssueOut:
    project = _project(db, user, project_id)
    issue = svc.create_issue_with_task(
        db, organization_id=project.organization_id, project_id=project_id,
        title=payload.title, user=user, description=payload.description,
        source=payload.source, severity=payload.severity, due_date=payload.due_date,
        discipline_id=payload.discipline_id, document_id=payload.document_id,
        responsible_employee_id=payload.responsible_employee_id,
        create_task=payload.create_task,
    )
    return IssueOut(
        id=issue.id, project_id=issue.project_id, source=issue.source,
        title=issue.title, severity=issue.severity, status=issue.status,
        due_date=issue.due_date,
        responsible_employee_id=issue.responsible_employee_id,
        linked_task_id=issue.linked_task_id,
    )


# --------------------------- Выпуск документации ------------------------- #


@router.post("/disciplines/{discipline_id}/request-release", response_model=dict)
def request_release(
    discipline_id: uuid.UUID,
    payload: ReleaseRequestIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.release")),
) -> dict:
    d = db.get(ProjectDiscipline, discipline_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")
    _project(db, user, d.project_id)
    try:
        approval = svc.request_documentation_release(
            db, d, document_id=payload.document_id, user=user
        )
    except svc.DesignStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return {"approval_id": str(approval.id), "risk_level": svc.RELEASE_RISK, "status": "pending"}


@router.post("/disciplines/{discipline_id}/release-decision", response_model=DisciplineOut)
def release_decision(
    discipline_id: uuid.UUID,
    payload: ReleaseDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.release")),
) -> DisciplineOut:
    d = db.get(ProjectDiscipline, discipline_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")
    _project(db, user, d.project_id)
    approval = db.get(Approval, payload.approval_id)
    if approval is None or approval.entity_id != d.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Согласование не найдено")
    try:
        svc.record_release_decision(
            db, approval, user=user, decision=payload.decision, comment=payload.comment
        )
    except svc.DesignStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _discipline_out(d)


@router.post("/disciplines/{discipline_id}/annul", response_model=DisciplineOut)
def annul_release(
    discipline_id: uuid.UUID,
    payload: AnnulIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.release")),
) -> DisciplineOut:
    d = db.get(ProjectDiscipline, discipline_id)
    if d is None or d.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Раздел не найден")
    _project(db, user, d.project_id)
    # Аннулирование утверждённой документации — R4 с усиленной аутентификацией.
    if not user.mfa_enabled or not user.mfa_secret or not payload.mfa_code:
        raise HTTPException(
            status.HTTP_401_UNAUTHORIZED,
            "Аннулирование (R4) требует кода MFA",
        )
    if not verify_totp(user.mfa_secret, payload.mfa_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
    try:
        svc.annul_documentation(
            db, d, user=user, reason=payload.reason, mfa_verified=True
        )
    except svc.ReleaseAuthorizationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return _discipline_out(d)


# ------------------------------- Каталог --------------------------------- #


@router.get("/suppliers", response_model=list[SupplierOut])
def list_suppliers(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("supplier.view")),
) -> list[SupplierOut]:
    rows = db.execute(
        select(Supplier, Counterparty)
        .join(Counterparty, Counterparty.id == Supplier.counterparty_id)
        .where(Supplier.deleted_at.is_(None))
    ).all()
    return [
        SupplierOut(
            id=s.id, name=cp.name, supplier_categories=s.supplier_categories,
            regions=s.regions, lead_time_days=s.lead_time_days,
            rating=str(s.rating) if s.rating is not None else None, status=s.status,
        )
        for s, cp in rows
    ]


@router.get("/materials", response_model=list[MaterialOut])
def list_materials(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("supplier.view")),
) -> list[MaterialOut]:
    rows = db.execute(
        select(Material).where(Material.deleted_at.is_(None))
    ).scalars()
    return [
        MaterialOut(id=m.id, code=m.code, name=m.name, category=m.category,
                    unit=m.unit, status=m.status)
        for m in rows
    ]


# ------------------------------- Сводка ГИП ------------------------------ #


@router.get(
    "/projects/{project_id}/overview", response_model=ProjectDesignOverview
)
def project_overview(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("design.view")),
) -> ProjectDesignOverview:
    _project(db, user, project_id)
    disciplines = list(
        db.execute(
            select(ProjectDiscipline).where(
                ProjectDiscipline.project_id == project_id,
                ProjectDiscipline.deleted_at.is_(None),
            )
        ).scalars()
    )
    brief = db.execute(
        select(DesignBrief).where(
            DesignBrief.project_id == project_id, DesignBrief.deleted_at.is_(None)
        )
    ).scalars().first()
    concepts = db.scalar(
        select(func.count(DesignConcept.id)).where(
            DesignConcept.project_id == project_id,
            DesignConcept.deleted_at.is_(None),
        )
    )
    specs = db.scalar(
        select(func.count(DesignSpecification.id)).where(
            DesignSpecification.project_id == project_id,
            DesignSpecification.deleted_at.is_(None),
        )
    )
    issues = list(
        db.execute(
            select(DesignIssue).where(
                DesignIssue.project_id == project_id,
                DesignIssue.deleted_at.is_(None),
            )
        ).scalars()
    )
    avg = (
        round(sum(d.completion_percent for d in disciplines) / len(disciplines))
        if disciplines
        else 0
    )
    return ProjectDesignOverview(
        project_id=project_id,
        disciplines_total=len(disciplines),
        disciplines_issued=len([d for d in disciplines if d.status == "issued"]),
        avg_completion=avg,
        brief_status=brief.status if brief else None,
        concepts_total=int(concepts or 0),
        specifications_total=int(specs or 0),
        issues_open=len([i for i in issues if i.status in ("open", "in_progress")]),
        issues_critical=len([i for i in issues if i.severity == "critical"]),
    )
