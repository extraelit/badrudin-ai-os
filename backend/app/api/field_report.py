"""API модуля «Мобильный ежедневный отчёт прораба».

Backend — единственная точка доступа к данным. Все действия проходят серверную
проверку прав (RBAC) и изоляцию по проекту (ABAC). Фото/файлы-доказательства
сохраняются в MinIO через сервис хранения (валидация типа и размера). Проверку
отчёта выполняет руководитель. Все значимые действия — в `audit_events`.
"""

from __future__ import annotations

import base64
import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import DailyReport, Employee, File, Project, User
from app.schemas.field_report import (
    EquipmentIn,
    EquipmentOut,
    EvidenceIn,
    EvidenceOut,
    HeadcountIn,
    HeadcountOut,
    IssueIn,
    IssueOut,
    ReportDetailOut,
    ReportIn,
    ReportOut,
    ReportSummaryOut,
    ReviewIn,
    WorkItemIn,
    WorkItemOut,
)
from app.services import field_report as svc

router = APIRouter(prefix="/field-reports", tags=["field-reports"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    from app.services.access import can_access_project

    if not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return project


def _report(db: Session, user: User, report_id: uuid.UUID) -> DailyReport:
    r = db.get(DailyReport, report_id)
    if r is None or r.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отчёт не найден")
    if not svc.can_access_report(db, user, r):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к отчёту")
    return r


def _out(r: DailyReport) -> ReportOut:
    return ReportOut(
        id=r.id, project_id=r.project_id, site_id=r.site_id, report_date=r.report_date,
        status=r.status, summary=r.summary, reviewed_by_user_id=r.reviewed_by_user_id,
        review_comment=r.review_comment, submitted_at=r.submitted_at,
    )


def _guard(exc: svc.FieldReportError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ------------------------------- Отчёты ---------------------------------- #


@router.get("/summary", response_model=ReportSummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.view")),
) -> ReportSummaryOut:
    return ReportSummaryOut(**svc.report_summary(db, _org(db, user)))


@router.get("/projects/{project_id}", response_model=list[ReportOut])
def list_reports(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.view")),
) -> list[ReportOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(DailyReport).where(
            DailyReport.project_id == project_id, DailyReport.deleted_at.is_(None)
        ).order_by(DailyReport.report_date.desc())
    ).scalars()
    return [_out(r) for r in rows]


@router.post("/projects/{project_id}", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def create_report(
    project_id: uuid.UUID,
    payload: ReportIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> ReportOut:
    project = _project(db, user, project_id)
    r = svc.create_report(
        db, project, user=user, report_date=payload.report_date, site_id=payload.site_id,
        weather_summary=payload.weather_summary, summary=payload.summary,
        work_completed=payload.work_completed, problems=payload.problems,
        plan_next_day=payload.plan_next_day,
    )
    return _out(r)


@router.get("/{report_id}", response_model=ReportDetailOut)
def get_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.view")),
) -> ReportDetailOut:
    r = _report(db, user, report_id)
    ch = svc.get_children(db, r)
    file_names = {
        f.id: f.original_name
        for f in db.execute(
            select(File).where(File.id.in_([e.file_id for e in ch["files"]] or [uuid.uuid4()]))
        ).scalars()
    }
    return ReportDetailOut(
        **_out(r).model_dump(), weather_summary=r.weather_summary,
        work_completed=r.work_completed, problems=r.problems, plan_next_day=r.plan_next_day,
        work_items=[
            WorkItemOut(id=w.id, work_type=w.work_type, task_id=w.task_id,
                        actual_quantity=str(w.actual_quantity),
                        planned_quantity=str(w.planned_quantity) if w.planned_quantity is not None else None,
                        verification_status=w.verification_status)
            for w in ch["work_items"]
        ],
        headcount=[HeadcountOut(id=h.id, profession=h.profession, count=h.count) for h in ch["headcount"]],
        equipment=[
            EquipmentOut(id=e.id, name=e.name, equipment_type=e.equipment_type,
                         count=e.count, hours=str(e.hours), status=e.status)
            for e in ch["equipment"]
        ],
        issues=[IssueOut(id=i.id, issue_type=i.issue_type, description=i.description, severity=i.severity) for i in ch["issues"]],
        evidence=[
            EvidenceOut(id=f.id, file_id=f.file_id, kind=f.kind, caption=f.caption,
                        original_name=file_names.get(f.file_id))
            for f in ch["files"]
        ],
    )


# ------------------------- Наполнение отчёта ----------------------------- #


@router.post("/{report_id}/work-items", response_model=WorkItemOut, status_code=status.HTTP_201_CREATED)
def add_work_item(
    report_id: uuid.UUID, payload: WorkItemIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> WorkItemOut:
    r = _report(db, user, report_id)
    try:
        w = svc.add_work_item(
            db, r, user=user, work_type=payload.work_type, task_id=payload.task_id,
            estimate_position_id=payload.estimate_position_id, unit_id=payload.unit_id,
            planned_quantity=Decimal(str(payload.planned_quantity)) if payload.planned_quantity is not None else None,
            actual_quantity=Decimal(str(payload.actual_quantity)), notes=payload.notes,
        )
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return WorkItemOut(id=w.id, work_type=w.work_type, task_id=w.task_id,
                       actual_quantity=str(w.actual_quantity),
                       planned_quantity=str(w.planned_quantity) if w.planned_quantity is not None else None,
                       verification_status=w.verification_status)


@router.post("/{report_id}/headcount", response_model=HeadcountOut, status_code=status.HTTP_201_CREATED)
def add_headcount(
    report_id: uuid.UUID, payload: HeadcountIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> HeadcountOut:
    r = _report(db, user, report_id)
    try:
        h = svc.add_headcount(db, r, user=user, profession=payload.profession,
                              count=payload.count, employee_id=payload.employee_id)
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return HeadcountOut(id=h.id, profession=h.profession, count=h.count)


@router.post("/{report_id}/equipment", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def add_equipment(
    report_id: uuid.UUID, payload: EquipmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> EquipmentOut:
    r = _report(db, user, report_id)
    try:
        e = svc.add_equipment(db, r, user=user, name=payload.name,
                              equipment_type=payload.equipment_type, count=payload.count,
                              hours=Decimal(str(payload.hours)), status=payload.status,
                              note=payload.note)
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return EquipmentOut(id=e.id, name=e.name, equipment_type=e.equipment_type,
                        count=e.count, hours=str(e.hours), status=e.status)


@router.post("/{report_id}/issues", response_model=IssueOut, status_code=status.HTTP_201_CREATED)
def add_issue(
    report_id: uuid.UUID, payload: IssueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> IssueOut:
    r = _report(db, user, report_id)
    try:
        i = svc.add_issue(db, r, user=user, issue_type=payload.issue_type,
                          description=payload.description, severity=payload.severity)
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return IssueOut(id=i.id, issue_type=i.issue_type, description=i.description, severity=i.severity)


@router.post("/{report_id}/evidence", response_model=EvidenceOut, status_code=status.HTTP_201_CREATED)
def add_evidence(
    report_id: uuid.UUID, payload: EvidenceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> EvidenceOut:
    r = _report(db, user, report_id)
    try:
        content = base64.b64decode(payload.content_base64, validate=True)
    except (ValueError, TypeError) as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Некорректное содержимое файла (base64)") from exc
    try:
        link = svc.attach_evidence(
            db, r, user=user, original_name=payload.original_name, content=content,
            mime_type=payload.mime_type, kind=payload.kind, caption=payload.caption,
            work_item_id=payload.work_item_id,
        )
    except svc.UploadValidationError as exc:
        raise HTTPException(422, str(exc)) from exc
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return EvidenceOut(id=link.id, file_id=link.file_id, kind=link.kind,
                       caption=link.caption, original_name=payload.original_name)


# --------------------- Отправка и проверка ------------------------------- #


@router.post("/{report_id}/submit", response_model=ReportOut)
def submit_report(
    report_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.manage")),
) -> ReportOut:
    r = _report(db, user, report_id)
    try:
        svc.submit_report(db, r, user=user)
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return _out(r)


@router.post("/{report_id}/review", response_model=ReportOut)
def review_report(
    report_id: uuid.UUID, payload: ReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("daily_report.approve")),
) -> ReportOut:
    r = _report(db, user, report_id)
    try:
        svc.review_report(db, r, user=user, decision=payload.decision, comment=payload.comment)
    except svc.FieldReportError as exc:
        raise _guard(exc) from exc
    return _out(r)
