"""API ежедневного отчёта: ИИ-черновик и правила отправки (этап E, PR-E).

Backend — единственная точка доступа. RBAC переиспользует права ежедневного отчёта:
`daily_report.view` (просмотр черновика/предупреждений), `daily_report.manage`
(генерация черновика, отметка «работы не велись», отправка), `daily_report.approve`
(подтверждение/отклонение черновика; отправка-исключение — дополнительно ограничена
ролью уполномоченного руководителя в сервисе). ABAC: доступ к отчёту ограничен
доступом к его проекту. ИИ не утверждает отчёт — подтверждает человек (D-010).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import AgentProposal, DailyReport, User
from app.schemas.daily_report_ai import (
    AiDraftOut,
    DecisionIn,
    ExceptionSubmitIn,
    MediaWarningsOut,
    NoWorkIn,
    ReportStatusOut,
)
from app.services import daily_report_ai as svc
from app.services.access import can_access_project

router = APIRouter(prefix="/daily-reports", tags=["daily-reports"])


def _report(db: Session, user: User, rid: uuid.UUID) -> DailyReport:
    r = db.get(DailyReport, rid)
    if r is None or r.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отчёт не найден")
    if not can_access_project(db, user, r.project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту отчёта")
    return r


def _proposal(db: Session, report: DailyReport, pid: uuid.UUID) -> AgentProposal:
    p = db.get(AgentProposal, pid)
    if p is None or p.project_id != report.project_id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Черновик не найден")
    return p


def _draft_out(p: AgentProposal) -> AiDraftOut:
    return AiDraftOut(
        proposal_id=p.id, status=p.status, summary=p.summary, payload=p.payload_json
    )


def _status_out(r: DailyReport) -> ReportStatusOut:
    return ReportStatusOut(
        id=r.id, status=r.status, no_work=r.no_work,
        no_work_reason=r.no_work_reason, submitted_at=r.submitted_at,
    )


def _guard(exc: svc.DailyReportError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


@router.post("/{rid}/ai-draft", response_model=AiDraftOut, status_code=201)
def generate_ai_draft(
    rid: uuid.UUID,
    current: User = Depends(require_permission("daily_report.manage")),
    db: Session = Depends(get_db),
) -> AiDraftOut:
    r = _report(db, current, rid)
    p = svc.generate_ai_draft(db, r, actor_user_id=current.id)
    return _draft_out(p)


@router.post("/{rid}/ai-draft/{pid}/confirm", response_model=AiDraftOut)
def confirm_ai_draft(
    rid: uuid.UUID, pid: uuid.UUID,
    current: User = Depends(require_permission("daily_report.approve")),
    db: Session = Depends(get_db),
) -> AiDraftOut:
    r = _report(db, current, rid)
    p = _proposal(db, r, pid)
    try:
        svc.confirm_ai_draft(db, p, actor_user_id=current.id)
    except svc.DailyReportError as exc:
        raise _guard(exc) from exc
    return _draft_out(p)


@router.post("/{rid}/ai-draft/{pid}/reject", response_model=AiDraftOut)
def reject_ai_draft(
    rid: uuid.UUID, pid: uuid.UUID, payload: DecisionIn,
    current: User = Depends(require_permission("daily_report.approve")),
    db: Session = Depends(get_db),
) -> AiDraftOut:
    r = _report(db, current, rid)
    p = _proposal(db, r, pid)
    try:
        svc.reject_ai_draft(db, p, actor_user_id=current.id, comment=payload.comment)
    except svc.DailyReportError as exc:
        raise _guard(exc) from exc
    return _draft_out(p)


@router.get("/{rid}/media-warnings", response_model=MediaWarningsOut)
def media_warnings(
    rid: uuid.UUID,
    current: User = Depends(require_permission("daily_report.view")),
    db: Session = Depends(get_db),
) -> MediaWarningsOut:
    r = _report(db, current, rid)
    return MediaWarningsOut(warnings=svc.media_metadata_warnings(db, r))


@router.post("/{rid}/no-work", response_model=ReportStatusOut)
def mark_no_work(
    rid: uuid.UUID, payload: NoWorkIn,
    current: User = Depends(require_permission("daily_report.manage")),
    db: Session = Depends(get_db),
) -> ReportStatusOut:
    r = _report(db, current, rid)
    try:
        svc.mark_no_work(db, r, reason=payload.reason, actor_user_id=current.id)
    except svc.DailyReportError as exc:
        raise _guard(exc) from exc
    return _status_out(r)


@router.post("/{rid}/submit", response_model=ReportStatusOut)
def submit_report(
    rid: uuid.UUID,
    current: User = Depends(require_permission("daily_report.manage")),
    db: Session = Depends(get_db),
) -> ReportStatusOut:
    r = _report(db, current, rid)
    try:
        svc.submit_report(db, r, actor_user_id=current.id)
    except svc.DailyReportError as exc:
        raise _guard(exc) from exc
    return _status_out(r)


@router.post("/{rid}/submit-exception", response_model=ReportStatusOut)
def submit_exception(
    rid: uuid.UUID, payload: ExceptionSubmitIn,
    current: User = Depends(require_permission("daily_report.approve")),
    db: Session = Depends(get_db),
) -> ReportStatusOut:
    r = _report(db, current, rid)
    try:
        svc.submit_without_media_exception(
            db, r, actor_user_id=current.id, reason=payload.reason
        )
    except svc.DailyReportError as exc:
        # роль не разрешает исключение — 403; прочее — 409
        code = status.HTTP_403_FORBIDDEN if "руководител" in str(exc) else status.HTTP_409_CONFLICT
        raise HTTPException(code, str(exc)) from exc
    return _status_out(r)
