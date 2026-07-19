"""API модуля «Финансы и бюджеты».

Backend — единственная точка доступа к данным. Все действия проходят серверную
проверку прав (RBAC) и изоляцию по организации/проекту (ABAC). Утверждение
бюджета и ручной статьи — R3; крупная сумма (порог организации) — R4 + MFA.
Система не проводит банковских операций. Все значимые действия — в
`audit_events`. Денежные значения — Decimal, в ответах сериализуются строкой.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.db.session import get_db
from app.models import (
    Budget,
    BudgetLine,
    Employee,
    Estimate,
    ExpenseCategory,
    FinancialCommitment,
    Project,
    User,
)
from app.schemas.finance import (
    BudgetFromEstimateIn,
    BudgetLineOut,
    BudgetOut,
    BudgetSummaryRow,
    CommitmentIn,
    CommitmentOut,
    DecisionIn,
    ExpenseCategoryIn,
    ExpenseCategoryOut,
    FinancialSummaryOut,
    ManualLineIn,
    SummaryComponentOut,
)
from app.services import finance as svc
from app.services.auth import verify_totp

router = APIRouter(prefix="/finance", tags=["finance"])


# ------------------------------ Помощники ------------------------------- #


def _org_id(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    if emp is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Сотрудник не найден")
    return emp.organization_id


def _project(db: Session, user: User, project_id: uuid.UUID) -> Project:
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    if not svc.can_access_finance_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")
    return project


def _budget(db: Session, user: User, budget_id: uuid.UUID) -> Budget:
    b = db.get(Budget, budget_id)
    if b is None or b.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Бюджет не найден")
    _project(db, user, b.project_id)
    return b


def _require_mfa(user: User, mfa_code: str | None) -> bool:
    if not user.mfa_enabled or not user.mfa_secret or not mfa_code:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Для уровня R4 требуется код MFA")
    if not verify_totp(user.mfa_secret, mfa_code):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Неверный код MFA")
    return True


# ------------------------------ Справочники ----------------------------- #


@router.get("/expense-categories", response_model=list[ExpenseCategoryOut])
def list_expense_categories(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("finance.view")),
) -> list[ExpenseCategoryOut]:
    org = _org_id(db, user)
    rows = db.execute(
        select(ExpenseCategory).where(
            ExpenseCategory.organization_id == org,
            ExpenseCategory.deleted_at.is_(None),
        )
    ).scalars()
    return [
        ExpenseCategoryOut(id=c.id, code=c.code, name=c.name, kind=c.kind,
                           parent_id=c.parent_id, status=c.status)
        for c in rows
    ]


@router.post("/expense-categories", response_model=ExpenseCategoryOut, status_code=status.HTTP_201_CREATED)
def create_expense_category(
    payload: ExpenseCategoryIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.manage")),
) -> ExpenseCategoryOut:
    org = _org_id(db, user)
    c = ExpenseCategory(
        organization_id=org, code=payload.code, name=payload.name,
        kind=payload.kind, parent_id=payload.parent_id, created_by=user.id,
    )
    db.add(c)
    db.commit()
    return ExpenseCategoryOut(id=c.id, code=c.code, name=c.name, kind=c.kind,
                             parent_id=c.parent_id, status=c.status)


# ------------------------------- Бюджет --------------------------------- #


def _line_out(l: BudgetLine) -> BudgetLineOut:
    return BudgetLineOut(
        id=l.id, cost_code=l.cost_code, category=l.category, description=l.description,
        planned_amount=str(l.planned_amount), approved_amount=str(l.approved_amount),
        source=l.source, is_manual=l.is_manual, source_reference=l.source_reference,
        status=l.status, expense_category_id=l.expense_category_id,
    )


def _budget_out(db: Session, b: Budget) -> BudgetOut:
    lines = list(
        db.execute(
            select(BudgetLine).where(BudgetLine.budget_id == b.id).order_by(BudgetLine.created_at)
        ).scalars()
    )
    return BudgetOut(
        id=b.id, project_id=b.project_id, source_estimate_id=b.source_estimate_id,
        name=b.name, version=b.version, currency=b.currency, status=b.status,
        planned_total=str(b.planned_total), approved_total=str(b.approved_total),
        risk_level=b.risk_level, approval_id=b.approval_id,
        lines=[_line_out(l) for l in lines],
    )


@router.get("/projects/{project_id}/budgets", response_model=list[BudgetSummaryRow])
def list_budgets(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("finance.view")),
) -> list[BudgetSummaryRow]:
    _project(db, user, project_id)
    rows = db.execute(
        select(Budget).where(Budget.project_id == project_id, Budget.deleted_at.is_(None))
        .order_by(Budget.created_at.desc())
    ).scalars()
    return [
        BudgetSummaryRow(id=b.id, name=b.name, version=b.version, status=b.status,
                         planned_total=str(b.planned_total), approved_total=str(b.approved_total))
        for b in rows
    ]


@router.post(
    "/projects/{project_id}/budgets/from-estimate",
    response_model=BudgetOut,
    status_code=status.HTTP_201_CREATED,
)
def create_budget_from_estimate(
    project_id: uuid.UUID,
    payload: BudgetFromEstimateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.manage")),
) -> BudgetOut:
    project = _project(db, user, project_id)
    estimate = db.get(Estimate, payload.estimate_id)
    if estimate is None or estimate.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Смета не найдена")
    try:
        budget = svc.build_budget_from_estimate(db, project, estimate, user=user)
    except svc.FinanceValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.FinanceStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    if payload.name:
        budget.name = payload.name
        db.commit()
    return _budget_out(db, budget)


@router.get("/budgets/{budget_id}", response_model=BudgetOut)
def get_budget(
    budget_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("finance.view")),
) -> BudgetOut:
    return _budget_out(db, _budget(db, user, budget_id))


@router.post("/budgets/{budget_id}/manual-lines", response_model=BudgetLineOut, status_code=status.HTTP_201_CREATED)
def add_manual_line(
    budget_id: uuid.UUID,
    payload: ManualLineIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.manage")),
) -> BudgetLineOut:
    budget = _budget(db, user, budget_id)
    try:
        line = svc.add_manual_line(
            db, budget, user=user, description=payload.description,
            amount=Decimal(str(payload.amount)), source_reference=payload.source_reference,
            category=payload.category, expense_category_id=payload.expense_category_id,
            cost_code=payload.cost_code,
        )
    except svc.FinanceValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return _line_out(line)


@router.post("/budget-lines/{line_id}/decision", response_model=BudgetLineOut)
def decide_manual_line(
    line_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.approve")),
) -> BudgetLineOut:
    line = db.get(BudgetLine, line_id)
    if line is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Статья не найдена")
    budget = _budget(db, user, line.budget_id)
    threshold = svc.large_threshold(db, budget.organization_id)
    risk = svc.operation_risk_level(Decimal(line.planned_amount or 0), threshold=threshold)
    mfa_verified = False
    if risk == "R4" and payload.decision == "approved":
        mfa_verified = _require_mfa(user, payload.mfa_code)
    try:
        svc.decide_manual_line(
            db, line, budget, user=user, decision=payload.decision,
            comment=payload.comment, mfa_verified=mfa_verified,
        )
    except (svc.FinanceStateError, svc.FinanceAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _line_out(line)


@router.post("/budgets/{budget_id}/request-approval", response_model=BudgetOut)
def request_budget_approval(
    budget_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.manage")),
) -> BudgetOut:
    budget = _budget(db, user, budget_id)
    try:
        svc.request_budget_approval(db, budget, user=user)
    except svc.FinanceValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.FinanceStateError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _budget_out(db, budget)


@router.post("/budgets/{budget_id}/decision", response_model=BudgetOut)
def decide_budget(
    budget_id: uuid.UUID,
    payload: DecisionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.approve")),
) -> BudgetOut:
    budget = _budget(db, user, budget_id)
    mfa_verified = False
    if budget.risk_level == "R4" and payload.decision == "approved":
        mfa_verified = _require_mfa(user, payload.mfa_code)
    try:
        svc.decide_budget(
            db, budget, user=user, decision=payload.decision,
            comment=payload.comment, mfa_verified=mfa_verified,
        )
    except (svc.FinanceStateError, svc.FinanceAuthorizationError) as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    return _budget_out(db, budget)


# --------------------------- Обязательства ------------------------------ #


def _commitment_out(c: FinancialCommitment) -> CommitmentOut:
    return CommitmentOut(
        id=c.id, project_id=c.project_id, description=c.description,
        amount=str(c.amount), currency=c.currency, source_type=c.source_type,
        source_reference=c.source_reference, counterparty_id=c.counterparty_id,
        due_date=c.due_date, status=c.status, risk_level=c.risk_level,
    )


@router.get("/projects/{project_id}/commitments", response_model=list[CommitmentOut])
def list_commitments(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("finance.view")),
) -> list[CommitmentOut]:
    _project(db, user, project_id)
    rows = db.execute(
        select(FinancialCommitment).where(
            FinancialCommitment.project_id == project_id,
            FinancialCommitment.deleted_at.is_(None),
        )
    ).scalars()
    return [_commitment_out(c) for c in rows]


@router.post("/projects/{project_id}/commitments", response_model=CommitmentOut, status_code=status.HTTP_201_CREATED)
def create_commitment(
    project_id: uuid.UUID,
    payload: CommitmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("budget.manage")),
) -> CommitmentOut:
    project = _project(db, user, project_id)
    threshold = svc.large_threshold(db, project.organization_id)
    risk = svc.operation_risk_level(Decimal(str(payload.amount)), threshold=threshold)
    mfa_verified = False
    if risk == "R4":
        mfa_verified = _require_mfa(user, payload.mfa_code)
    try:
        commitment = svc.create_commitment(
            db, project, user=user, description=payload.description,
            amount=Decimal(str(payload.amount)), source_reference=payload.source_reference,
            counterparty_id=payload.counterparty_id, budget_line_id=payload.budget_line_id,
            due_date=payload.due_date, mfa_verified=mfa_verified,
        )
    except svc.FinanceValidationError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    except svc.FinanceAuthorizationError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(exc)) from exc
    return _commitment_out(commitment)


# ---------------------------- Сводка проекта ---------------------------- #


def _summary_out(s: svc.ProjectFinancialSummary) -> FinancialSummaryOut:
    return FinancialSummaryOut(
        project_id=s.project_id, currency=s.currency,
        approved_budget=str(s.approved_budget), planned_budget=str(s.planned_budget),
        committed=str(s.committed), actual=str(s.actual), remaining=str(s.remaining),
        forecast=str(s.forecast), forecast_deviation=str(s.forecast_deviation),
        has_approved_budget=s.has_approved_budget,
        committed_breakdown=[
            SummaryComponentOut(label=c.label, amount=str(c.amount), source=c.source)
            for c in s.committed_breakdown
        ],
        actual_breakdown=[
            SummaryComponentOut(label=c.label, amount=str(c.amount), source=c.source)
            for c in s.actual_breakdown
        ],
    )


@router.get("/projects/{project_id}/financial-summary", response_model=FinancialSummaryOut)
def financial_summary(
    project_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("finance.view")),
) -> FinancialSummaryOut:
    project = _project(db, user, project_id)
    return _summary_out(svc.project_financial_summary(db, project))


@router.get("/projects/{project_id}/financial-summary/export")
def export_financial_summary(
    project_id: uuid.UUID,
    format: str = "csv",
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("finance.view")),
) -> Response:
    project = _project(db, user, project_id)
    if format not in ("csv", "json"):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Формат: csv или json")
    summary = svc.project_financial_summary(db, project)
    body = svc.export_summary(summary, fmt=format)
    media = "text/csv" if format == "csv" else "application/json"
    filename = f"financial-summary-{project_id}.{format}"
    return Response(
        content=body, media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
