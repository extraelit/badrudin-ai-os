"""API модуля «Персонал объектов» (T — производственный учёт персонала).

Backend — единственная точка доступа к данным (ARCHITECTURE.md раздел 5.2).
Все чтения/действия проходят серверную проверку прав (RBAC) и изоляцию по
объектам (ABAC). Выплаты и критические изменения — через согласование R3/R4;
все действия пишутся в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import (
    Employee,
    ForemanJournal,
    PayrollDraft,
    PayrollLine,
    SafetyClearance,
    Site,
    SiteWorkerAssignment,
    User,
    WorkPermit,
    WorkShift,
)
from app.schemas.personnel import (
    DirectorSummaryOut,
    JournalOut,
    PayoutDecisionIn,
    PayrollDraftOut,
    PayrollLineOut,
    SafetyClearanceOut,
    ShiftIn,
    ShiftOut,
    SiteSummaryRow,
    WorkerAssignmentIn,
    WorkerAssignmentOut,
)
from app.services import personnel as svc
from app.services.access import accessible_project_ids
from app.services.auth import verify_totp

router = APIRouter(prefix="/personnel", tags=["personnel"])


def _load_site(db: Session, user: User, site_id: uuid.UUID) -> Site:
    site = db.get(Site, site_id)
    if site is None or site.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Объект не найден")
    if not svc.can_access_site(db, user, site):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к объекту")
    return site


def _employee_names(db: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = db.execute(
        select(Employee.id, Employee.full_name).where(Employee.id.in_(ids))
    ).all()
    return {r[0]: r[1] for r in rows}


# ------------------------------ Работники -------------------------------- #


@router.get(
    "/sites/{site_id}/workers", response_model=list[WorkerAssignmentOut]
)
def list_workers(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.view")),
) -> list[WorkerAssignmentOut]:
    _load_site(db, user, site_id)
    rows = list(
        db.execute(
            select(SiteWorkerAssignment).where(
                SiteWorkerAssignment.site_id == site_id,
                SiteWorkerAssignment.deleted_at.is_(None),
            )
        ).scalars()
    )
    names = _employee_names(db, {r.employee_id for r in rows})
    clearances = {
        c.employee_id: c.status
        for c in db.execute(
            select(SafetyClearance).where(
                SafetyClearance.employee_id.in_({r.employee_id for r in rows} or {uuid.uuid4()})
            )
        ).scalars()
    }
    return [
        WorkerAssignmentOut(
            id=r.id,
            employee_id=r.employee_id,
            full_name=names.get(r.employee_id),
            brigade=r.brigade,
            profession=r.profession,
            is_responsible=r.is_responsible,
            status=r.status,
            clearance_status=clearances.get(r.employee_id),
        )
        for r in rows
    ]


@router.post(
    "/sites/{site_id}/workers",
    response_model=WorkerAssignmentOut,
    status_code=status.HTTP_201_CREATED,
)
def add_worker(
    site_id: uuid.UUID,
    payload: WorkerAssignmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.manage")),
) -> WorkerAssignmentOut:
    site = _load_site(db, user, site_id)
    assignment = SiteWorkerAssignment(
        organization_id=site.organization_id,
        site_id=site.id,
        project_id=site.project_id,
        employee_id=payload.employee_id,
        brigade=payload.brigade,
        profession=payload.profession,
        is_responsible=payload.is_responsible,
        start_date=payload.start_date,
        created_by=user.id,
    )
    db.add(assignment)
    db.flush()
    svc.record_event(
        db,
        actor_type="user",
        action="personnel.worker.assigned",
        actor_user_id=user.id,
        organization_id=site.organization_id,
        entity_type="site_worker_assignment",
        entity_id=assignment.id,
        new_values={"site_id": str(site.id), "employee_id": str(payload.employee_id)},
        commit=False,
    )
    db.commit()
    names = _employee_names(db, {assignment.employee_id})
    return WorkerAssignmentOut(
        id=assignment.id,
        employee_id=assignment.employee_id,
        full_name=names.get(assignment.employee_id),
        brigade=assignment.brigade,
        profession=assignment.profession,
        is_responsible=assignment.is_responsible,
        status=assignment.status,
    )


# -------------------------------- Табель --------------------------------- #


@router.get("/sites/{site_id}/timesheet", response_model=list[ShiftOut])
def list_timesheet(
    site_id: uuid.UUID,
    date_from: date | None = None,
    date_to: date | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.view")),
) -> list[ShiftOut]:
    _load_site(db, user, site_id)
    stmt = select(WorkShift).where(WorkShift.site_id == site_id)
    if date_from is not None:
        stmt = stmt.where(WorkShift.work_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(WorkShift.work_date <= date_to)
    rows = list(db.execute(stmt).scalars())
    return [
        ShiftOut(
            id=s.id,
            employee_id=s.employee_id,
            work_date=s.work_date,
            shift_type=s.shift_type,
            hours_worked=float(s.hours_worked),
            overtime_hours=float(s.overtime_hours),
            idle_hours=float(s.idle_hours),
            absence_type=s.absence_type,
            status=s.status,
        )
        for s in rows
    ]


@router.post(
    "/sites/{site_id}/shifts",
    response_model=ShiftOut,
    status_code=status.HTTP_201_CREATED,
)
def create_shift(
    site_id: uuid.UUID,
    payload: ShiftIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.manage")),
) -> ShiftOut:
    site = _load_site(db, user, site_id)
    # Гейт охраны труда: нельзя засчитать отработанные часы без допуска.
    if payload.hours_worked > 0 and not payload.absence_type:
        try:
            svc.assert_can_mark_worked(
                db,
                employee_id=payload.employee_id,
                on_date=payload.work_date,
                required_permits=tuple(payload.required_permits),
            )
        except svc.ClearanceRequiredError as exc:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                f"Работник не допущен к работе: {exc}",
            ) from exc
    shift = WorkShift(
        organization_id=site.organization_id,
        site_id=site.id,
        employee_id=payload.employee_id,
        work_date=payload.work_date,
        shift_type=payload.shift_type,
        arrival_time=payload.arrival_time,
        departure_time=payload.departure_time,
        hours_worked=payload.hours_worked,
        overtime_hours=payload.overtime_hours,
        idle_hours=payload.idle_hours,
        absence_type=payload.absence_type,
        status="confirmed",
        created_by=user.id,
    )
    db.add(shift)
    db.flush()
    svc.record_event(
        db,
        actor_type="user",
        action="personnel.shift.recorded",
        actor_user_id=user.id,
        organization_id=site.organization_id,
        entity_type="work_shift",
        entity_id=shift.id,
        new_values={"employee_id": str(payload.employee_id), "date": str(payload.work_date)},
        commit=False,
    )
    db.commit()
    return ShiftOut(
        id=shift.id,
        employee_id=shift.employee_id,
        work_date=shift.work_date,
        shift_type=shift.shift_type,
        hours_worked=float(shift.hours_worked),
        overtime_hours=float(shift.overtime_hours),
        idle_hours=float(shift.idle_hours),
        absence_type=shift.absence_type,
        status=shift.status,
    )


# ------------------------------ Охрана труда ----------------------------- #


@router.get("/sites/{site_id}/safety", response_model=list[SafetyClearanceOut])
def list_safety(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.view")),
) -> list[SafetyClearanceOut]:
    _load_site(db, user, site_id)
    rows = list(
        db.execute(
            select(SafetyClearance).where(SafetyClearance.site_id == site_id)
        ).scalars()
    )
    names = _employee_names(db, {r.employee_id for r in rows})
    out: list[SafetyClearanceOut] = []
    for c in rows:
        permits = [
            {
                "permit_type": p.permit_type,
                "valid_until": p.valid_until.isoformat() if p.valid_until else None,
                "status": p.status,
            }
            for p in db.execute(
                select(WorkPermit).where(WorkPermit.clearance_id == c.id)
            ).scalars()
        ]
        out.append(
            SafetyClearanceOut(
                id=c.id,
                employee_id=c.employee_id,
                full_name=names.get(c.employee_id),
                intro_briefing_at=c.intro_briefing_at,
                primary_briefing_at=c.primary_briefing_at,
                targeted_briefing_at=c.targeted_briefing_at,
                signed_by_worker=c.signed_by_worker,
                medical_valid_until=c.medical_valid_until,
                status=c.status,
                permits=permits,
            )
        )
    return out


# ------------------------------- Журналы --------------------------------- #


@router.get("/sites/{site_id}/journals", response_model=list[JournalOut])
def list_journals(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.view")),
) -> list[JournalOut]:
    _load_site(db, user, site_id)
    rows = list(
        db.execute(
            select(ForemanJournal).where(
                ForemanJournal.site_id == site_id,
                ForemanJournal.deleted_at.is_(None),
            )
        ).scalars()
    )
    return [
        JournalOut(
            id=j.id,
            site_id=j.site_id,
            journal_type=j.journal_type,
            responsible_employee_id=j.responsible_employee_id,
            status=j.status,
            due_date=j.due_date,
            attachments_count=j.attachments_count,
        )
        for j in rows
    ]


# ------------------------------ Начисления ------------------------------- #


def _draft_out(db: Session, draft: PayrollDraft) -> PayrollDraftOut:
    lines = list(
        db.execute(
            select(PayrollLine).where(PayrollLine.payroll_draft_id == draft.id)
        ).scalars()
    )
    return PayrollDraftOut(
        id=draft.id,
        site_id=draft.site_id,
        period_start=draft.period_start,
        period_end=draft.period_end,
        status=draft.status,
        total_accrued=str(draft.total_accrued),
        total_advance=str(draft.total_advance),
        total_deduction=str(draft.total_deduction),
        total_to_pay=str(draft.total_to_pay),
        currency=draft.currency,
        risk_level=draft.risk_level,
        approval_id=draft.approval_id,
        lines=[
            PayrollLineOut(
                id=x.id,
                employee_id=x.employee_id,
                scheme=x.scheme,
                rate=str(x.rate),
                quantity=str(x.quantity),
                unit=x.unit,
                accrued=str(x.accrued),
                advance=str(x.advance),
                deduction=str(x.deduction),
                to_pay=str(x.to_pay),
                status=x.status,
            )
            for x in lines
        ],
    )


def _load_draft(db: Session, user: User, draft_id: uuid.UUID) -> PayrollDraft:
    draft = db.get(PayrollDraft, draft_id)
    if draft is None or draft.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Расчёт не найден")
    _load_site(db, user, draft.site_id)  # проверка доступа к объекту
    return draft


@router.get("/sites/{site_id}/payroll", response_model=list[PayrollDraftOut])
def list_payroll(
    site_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("payroll.view")),
) -> list[PayrollDraftOut]:
    _load_site(db, user, site_id)
    drafts = list(
        db.execute(
            select(PayrollDraft).where(
                PayrollDraft.site_id == site_id,
                PayrollDraft.deleted_at.is_(None),
            )
        ).scalars()
    )
    return [_draft_out(db, d) for d in drafts]


@router.post("/payroll/{draft_id}/recalc", response_model=PayrollDraftOut)
def recalc_payroll(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("payroll.manage")),
) -> PayrollDraftOut:
    draft = _load_draft(db, user, draft_id)
    svc.recalc_draft(db, draft)
    db.commit()
    return _draft_out(db, draft)


@router.post("/payroll/{draft_id}/request-payout", response_model=PayrollDraftOut)
def request_payout(
    draft_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("payroll.manage")),
) -> PayrollDraftOut:
    draft = _load_draft(db, user, draft_id)
    try:
        svc.request_payout(db, draft, user=user)
    except svc.PayrollStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _draft_out(db, draft)


@router.post("/payroll/{draft_id}/decision", response_model=PayrollDraftOut)
def decide_payout(
    draft_id: uuid.UUID,
    payload: PayoutDecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("payroll.approve")),
) -> PayrollDraftOut:
    draft = _load_draft(db, user, draft_id)
    mfa_verified = False
    if draft.risk_level == "R4" and payload.decision == "approved":
        # Усиленная аутентификация для действий уровня R4 (D-002).
        if not user.mfa_enabled or not user.mfa_secret or not payload.mfa_code:
            raise HTTPException(
                status.HTTP_401_UNAUTHORIZED,
                "Для подтверждения выплаты R4 требуется код MFA",
            )
        if not verify_totp(user.mfa_secret, payload.mfa_code):
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
        mfa_verified = True
    try:
        svc.record_payout_decision(
            db,
            draft,
            user=user,
            decision=payload.decision,
            comment=payload.comment,
            mfa_verified=mfa_verified,
        )
    except (svc.PayrollStateError, svc.PayoutAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _draft_out(db, draft)


# ------------------------------- Сводка ---------------------------------- #


@router.get("/director/summary", response_model=DirectorSummaryOut)
def director_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("personnel.view")),
) -> DirectorSummaryOut:
    allowed = accessible_project_ids(db, user)  # None → полный доступ
    stmt = select(Site).where(Site.deleted_at.is_(None))
    if allowed is not None:
        if not allowed:
            return DirectorSummaryOut(
                sites=[],
                total_workers=0,
                total_on_site=0,
                total_without_clearance=0,
                total_unfilled_journals=0,
            )
        stmt = stmt.where(Site.project_id.in_(allowed))
    sites = list(db.execute(stmt).scalars())

    rows: list[SiteSummaryRow] = []
    t_workers = t_on = t_noclear = t_journ = 0
    for site in sites:
        assignments = list(
            db.execute(
                select(SiteWorkerAssignment).where(
                    SiteWorkerAssignment.site_id == site.id,
                    SiteWorkerAssignment.deleted_at.is_(None),
                    SiteWorkerAssignment.status == "active",
                )
            ).scalars()
        )
        shifts = list(
            db.execute(
                select(WorkShift).where(WorkShift.site_id == site.id)
            ).scalars()
        )
        on_site = sum(
            1 for s in shifts if s.hours_worked and float(s.hours_worked) > 0
        )
        hours_day = sum(float(s.hours_worked) for s in shifts)
        overtime = sum(float(s.overtime_hours) for s in shifts)
        idle = sum(float(s.idle_hours) for s in shifts)
        without_clearance = len(
            [
                c
                for c in db.execute(
                    select(SafetyClearance).where(
                        SafetyClearance.site_id == site.id,
                        SafetyClearance.status != "cleared",
                    )
                ).scalars()
            ]
        )
        unfilled = len(
            [
                j
                for j in db.execute(
                    select(ForemanJournal).where(
                        ForemanJournal.site_id == site.id,
                        ForemanJournal.deleted_at.is_(None),
                        ForemanJournal.status.in_(("not_filled", "overdue")),
                    )
                ).scalars()
            ]
        )
        rows.append(
            SiteSummaryRow(
                site_id=site.id,
                site_name=site.name,
                workers=len(assignments),
                on_site=on_site,
                hours_day=hours_day,
                overtime=overtime,
                idle=idle,
                without_clearance=without_clearance,
                unfilled_journals=unfilled,
            )
        )
        t_workers += len(assignments)
        t_on += on_site
        t_noclear += without_clearance
        t_journ += unfilled

    return DirectorSummaryOut(
        sites=rows,
        total_workers=t_workers,
        total_on_site=t_on,
        total_without_clearance=t_noclear,
        total_unfilled_journals=t_journ,
    )
