"""API модуля «Подотчётные денежные средства» (DATABASE.md §32).

Backend — единственная точка доступа. RBAC (`require_permission`) и ABAC (доступ к
проекту выдачи) на сервере; согласование выдачи — R3, крупная — R4 + MFA; проверка
расходов и отчёта — R2. Разделение ролей: инициатор (`accountable.manage`),
согласующий (`accountable.approve`), бухгалтер (`accountable.account`). Все действия
— в `audit_events`. Суммы — Decimal, в ответах — строкой.
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
    AccountableAdvance,
    AccountableExpense,
    AdvanceReport,
    Employee,
    ExpenseCategory,
    User,
)
from app.schemas.accountable import (
    AccountableSummaryOut,
    AdvanceIn,
    AdvanceOut,
    CategoryOut,
    DecisionIn,
    DocumentIn,
    DocumentOut,
    ExpenseIn,
    ExpenseOut,
    IssueIn,
    ReportOut,
    ReviewReportIn,
    SettlementIn,
    SettlementOut,
    VerifyExpenseIn,
)
from app.services import accountable as svc
from app.services.accountable import large_threshold, operation_risk_level
from app.services.auth import verify_totp

router = APIRouter(prefix="/accountable", tags=["accountable"])


# ------------------------------ Помощники ------------------------------- #


def _org_id(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сотрудник не найден")
    return emp.organization_id


def _advance(db: Session, user: User, advance_id: uuid.UUID) -> AccountableAdvance:
    a = db.get(AccountableAdvance, advance_id)
    org = _org_id(db, user)
    if a is None or a.deleted_at is not None or a.organization_id != org:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Выдача не найдена")
    if not svc.can_access_advance_project(db, user, a):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту выдачи")
    return a


def _require_mfa(user: User, mfa_code: str | None) -> bool:
    if not user.mfa_enabled or not user.mfa_secret or not mfa_code:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Для уровня R4 требуется код MFA")
    if not verify_totp(user.mfa_secret, mfa_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
    return True


def _adv_out(a: AccountableAdvance) -> AdvanceOut:
    return AdvanceOut(
        id=a.id, employee_id=a.employee_id, project_id=a.project_id, purpose=a.purpose,
        amount_issued=str(a.amount_issued), amount_spent_confirmed=str(a.amount_spent_confirmed),
        amount_returned=str(a.amount_returned), amount_reimbursable=str(a.amount_reimbursable),
        balance_amount=str(a.balance_amount), currency_code=a.currency_code, status=a.status,
        risk_level=a.risk_level, report_due_at=a.report_due_at, approval_id=a.approval_id,
    )


def _exp_out(e: AccountableExpense) -> ExpenseOut:
    return ExpenseOut(
        id=e.id, advance_id=e.advance_id, expense_category_id=e.expense_category_id,
        amount=str(e.amount), expense_date=e.expense_date, description=e.description,
        payment_method=e.payment_method, receipt_required=e.receipt_required,
        document_status=e.document_status, verification_status=e.verification_status,
    )


def _rep_out(r: AdvanceReport) -> ReportOut:
    return ReportOut(
        id=r.id, advance_id=r.advance_id, total_expenses_submitted=str(r.total_expenses_submitted),
        total_expenses_approved=str(r.total_expenses_approved), amount_to_return=str(r.amount_to_return),
        amount_to_reimburse=str(r.amount_to_reimburse), status=r.status,
    )


# ------------------------------ Справочник ------------------------------ #


@router.get("/expense-categories", response_model=list[CategoryOut])
def list_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.view")),
) -> list[CategoryOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(ExpenseCategory).where(
            ExpenseCategory.organization_id == org, ExpenseCategory.deleted_at.is_(None)
        )
    ).scalars()
    return [
        CategoryOut(id=c.id, code=c.code, name=c.name, requires_receipt=c.requires_receipt,
                    requires_preapproval=c.requires_preapproval,
                    default_limit=str(c.default_limit) if c.default_limit is not None else None)
        for c in rows
    ]


# ------------------------------- Выдача --------------------------------- #


@router.get("/advances", response_model=list[AdvanceOut])
def list_advances(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.view")),
) -> list[AdvanceOut]:
    org = _org_id(db, user)
    rows = list(db.execute(
        select(AccountableAdvance).where(
            AccountableAdvance.organization_id == org, AccountableAdvance.deleted_at.is_(None)
        ).order_by(AccountableAdvance.created_at.desc())
    ).scalars())
    return [_adv_out(a) for a in rows if svc.can_access_advance_project(db, user, a)]


@router.post("/advances", response_model=AdvanceOut, status_code=status.HTTP_201_CREATED)
def create_advance(
    payload: AdvanceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.manage")),
) -> AdvanceOut:
    org = _org_id(db, user)
    try:
        a = svc.create_advance(
            db, user=user, organization_id=org, employee_id=payload.employee_id,
            purpose=payload.purpose, amount_issued=Decimal(str(payload.amount_issued)),
            report_due_at=payload.report_due_at, project_id=payload.project_id,
            site_id=payload.site_id, task_id=payload.task_id,
            expense_category_id=payload.expense_category_id,
            payment_method=payload.payment_method, currency_code=payload.currency_code,
        )
    except svc.AccountableValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _adv_out(a)


@router.get("/advances/{advance_id}", response_model=AdvanceOut)
def get_advance(
    advance_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.view")),
) -> AdvanceOut:
    return _adv_out(_advance(db, user, advance_id))


@router.post("/advances/{advance_id}/request-approval", response_model=AdvanceOut)
def request_approval(
    advance_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.manage")),
) -> AdvanceOut:
    a = _advance(db, user, advance_id)
    try:
        svc.request_advance_approval(db, a, user=user)
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _adv_out(a)


@router.post("/advances/{advance_id}/decision", response_model=AdvanceOut)
def decide_advance(
    advance_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.approve")),
) -> AdvanceOut:
    a = _advance(db, user, advance_id)
    mfa_verified = False
    if a.risk_level == "R4" and payload.decision == "approved":
        mfa_verified = _require_mfa(user, payload.mfa_code)
    try:
        svc.decide_advance(db, a, user=user, decision=payload.decision,
                           comment=payload.comment, mfa_verified=mfa_verified)
    except (svc.AccountableStateError, svc.AccountableAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _adv_out(a)


@router.post("/advances/{advance_id}/issue", response_model=AdvanceOut)
def issue_advance(
    advance_id: uuid.UUID,
    payload: IssueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.approve")),
) -> AdvanceOut:
    a = _advance(db, user, advance_id)
    try:
        svc.issue_advance(db, a, user=user, payment_reference=payload.payment_reference)
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _adv_out(a)


# ------------------------------- Расходы -------------------------------- #


@router.get("/advances/{advance_id}/expenses", response_model=list[ExpenseOut])
def list_expenses(
    advance_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.view")),
) -> list[ExpenseOut]:
    _advance(db, user, advance_id)
    rows = db.execute(
        select(AccountableExpense).where(
            AccountableExpense.advance_id == advance_id, AccountableExpense.deleted_at.is_(None)
        ).order_by(AccountableExpense.created_at.desc())
    ).scalars()
    return [_exp_out(e) for e in rows]


@router.post("/advances/{advance_id}/expenses", response_model=ExpenseOut, status_code=status.HTTP_201_CREATED)
def add_expense(
    advance_id: uuid.UUID,
    payload: ExpenseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.manage")),
) -> ExpenseOut:
    a = _advance(db, user, advance_id)
    try:
        e = svc.add_expense(
            db, a, user=user, expense_category_id=payload.expense_category_id,
            amount=Decimal(str(payload.amount)), expense_date=payload.expense_date,
            description=payload.description, supplier_id=payload.supplier_id,
            vat_amount=Decimal(str(payload.vat_amount)) if payload.vat_amount is not None else None,
            payment_method=payload.payment_method, created_from_mobile=payload.created_from_mobile,
        )
    except svc.AccountableValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _exp_out(e)


def _expense(db: Session, user: User, expense_id: uuid.UUID) -> tuple[AccountableExpense, AccountableAdvance]:
    e = db.get(AccountableExpense, expense_id)
    if e is None or e.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Расход не найден")
    a = _advance(db, user, e.advance_id)
    return e, a


@router.post("/expenses/{expense_id}/documents", response_model=DocumentOut, status_code=status.HTTP_201_CREATED)
def attach_document(
    expense_id: uuid.UUID,
    payload: DocumentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.manage")),
) -> DocumentOut:
    e, _ = _expense(db, user, expense_id)
    try:
        doc = svc.attach_document(
            db, e, user=user, duplicate_hash=payload.duplicate_hash, file_id=payload.file_id,
            document_type=payload.document_type, document_number=payload.document_number,
            document_date=payload.document_date, seller_name=payload.seller_name,
            extracted_amount=Decimal(str(payload.extracted_amount)) if payload.extracted_amount is not None else None,
        )
    except svc.AccountableValidationError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return DocumentOut(id=doc.id, expense_id=doc.expense_id, document_type=doc.document_type,
                       document_number=doc.document_number, ocr_status=doc.ocr_status)


@router.post("/expenses/{expense_id}/verify", response_model=ExpenseOut)
def verify_expense(
    expense_id: uuid.UUID,
    payload: VerifyExpenseIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.account")),
) -> ExpenseOut:
    e, a = _expense(db, user, expense_id)
    try:
        svc.verify_expense(db, e, a, user=user, decision=payload.decision, reason=payload.reason)
    except svc.AccountableValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _exp_out(e)


# --------------------------- Авансовый отчёт ---------------------------- #


@router.post("/advances/{advance_id}/report", response_model=ReportOut, status_code=status.HTTP_201_CREATED)
def submit_report(
    advance_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.manage")),
) -> ReportOut:
    a = _advance(db, user, advance_id)
    try:
        r = svc.submit_report(db, a, user=user)
    except svc.AccountableValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _rep_out(r)


@router.post("/reports/{report_id}/review", response_model=ReportOut)
def review_report(
    report_id: uuid.UUID,
    payload: ReviewReportIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.account")),
) -> ReportOut:
    r = db.get(AdvanceReport, report_id)
    if r is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Отчёт не найден")
    a = _advance(db, user, r.advance_id)
    try:
        svc.review_report(db, r, a, user=user, decision=payload.decision, comment=payload.comment)
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _rep_out(r)


# ------------------------- Возврат / возмещение ------------------------- #


@router.post("/advances/{advance_id}/settlements", response_model=SettlementOut, status_code=status.HTTP_201_CREATED)
def settle(
    advance_id: uuid.UUID,
    payload: SettlementIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.account")),
) -> SettlementOut:
    a = _advance(db, user, advance_id)
    try:
        s = svc.settle(
            db, a, user=user, settlement_type=payload.settlement_type,
            amount=Decimal(str(payload.amount)), report_id=payload.report_id,
            payment_method=payload.payment_method, payment_reference=payload.payment_reference,
            idempotency_key=payload.idempotency_key,
        )
    except svc.AccountableValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.AccountableStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return SettlementOut(id=s.id, advance_id=s.advance_id, settlement_type=s.settlement_type,
                         amount=str(s.amount), status=s.status)


# ------------------------------- Сводка --------------------------------- #


@router.get("/summary", response_model=AccountableSummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("accountable.view")),
) -> AccountableSummaryOut:
    org = _org_id(db, user)
    s = svc.accountable_summary(db, org)
    return AccountableSummaryOut(
        advances_open=s.advances_open, advances_overdue=s.advances_overdue,
        total_issued=str(s.total_issued), total_spent=str(s.total_spent),
        total_outstanding=str(s.total_outstanding), reports_pending=s.reports_pending,
    )
