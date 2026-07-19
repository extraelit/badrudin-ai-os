"""Бизнес-логика модуля «Подотчётные денежные средства» (DATABASE.md §32).

Жизненный цикл: выдача под отчёт → расходы с подтверждающими документами →
проверка расходов → авансовый отчёт → проверка бухгалтером → возврат/возмещение →
закрытие. Разделение ролей (инициатор/согласующий/бухгалтер), контроль лимита и
срока, запрет повторного использования чека (`duplicate_hash`), согласование
R2–R4 + MFA, все действия — в `audit_events`. Система не проводит банковских
операций (D-015): возврат/возмещение только фиксируются. Расчёты — Decimal.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    AccountableAdvance,
    AccountableExpense,
    AdvanceReport,
    AdvanceSettlement,
    Approval,
    ApprovalStep,
    ExpenseCategory,
    ExpenseDocument,
)
from app.services.access import can_access_project
from app.services.audit import record_event
from app.services.finance import large_threshold, operation_risk_level


class AccountableStateError(RuntimeError):
    """Недопустимый переход состояния подотчётной сущности."""


class AccountableValidationError(RuntimeError):
    """Нарушение бизнес-правила (лимит, отсутствие чека, дубликат)."""


class AccountableAuthorizationError(RuntimeError):
    """Недостаточно условий для подтверждения (например, отсутствует MFA для R4)."""


def _q(v: Decimal) -> Decimal:
    return Decimal(v).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ------------------------------- Выдача --------------------------------- #


def create_advance(
    session: Session,
    *,
    user,
    organization_id: uuid.UUID,
    employee_id: uuid.UUID,
    purpose: str,
    amount_issued: Decimal,
    report_due_at: datetime | None = None,
    project_id: uuid.UUID | None = None,
    site_id: uuid.UUID | None = None,
    task_id: uuid.UUID | None = None,
    expense_category_id: uuid.UUID | None = None,
    payment_method: str = "cash",
    currency_code: str = "RUB",
) -> AccountableAdvance:
    """Регистрирует выдачу под отчёт (черновик)."""
    if Decimal(amount_issued) <= 0:
        raise AccountableValidationError("сумма выдачи должна быть > 0")
    advance = AccountableAdvance(
        organization_id=organization_id, employee_id=employee_id, purpose=purpose,
        amount_issued=_q(Decimal(amount_issued)), currency_code=currency_code,
        report_due_at=report_due_at, project_id=project_id, site_id=site_id,
        task_id=task_id, expense_category_id=expense_category_id,
        payment_method=payment_method, issued_by_user_id=user.id, status="draft",
        balance_amount=_q(Decimal(amount_issued)), created_by=user.id,
    )
    session.add(advance)
    session.flush()
    record_event(
        session, actor_type="user", action="accountable.advance.created",
        actor_user_id=user.id, organization_id=organization_id,
        entity_type="accountable_advance", entity_id=advance.id,
        new_values={"amount": str(advance.amount_issued)}, commit=False,
    )
    session.commit()
    return advance


def request_advance_approval(session: Session, advance: AccountableAdvance, *, user) -> Approval:
    """Запрашивает согласование выдачи (R3, крупная — R4)."""
    if advance.status not in ("draft",):
        raise AccountableStateError(f"нельзя согласовать выдачу из '{advance.status}'")
    threshold = large_threshold(session, advance.organization_id)
    risk = operation_risk_level(Decimal(advance.amount_issued), threshold=threshold)
    approval = Approval(
        organization_id=advance.organization_id, entity_type="accountable_advance",
        entity_id=advance.id, approval_type="accountable_advance",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    advance.approval_id = approval.id
    advance.risk_level = risk
    advance.status = "pending_approval"
    record_event(
        session, actor_type="user", action="accountable.advance.approval_requested",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="accountable_advance", entity_id=advance.id, approval_id=approval.id,
        risk_level=risk, commit=False,
    )
    session.commit()
    return approval


def decide_advance(
    session: Session, advance: AccountableAdvance, *, user, decision: str,
    comment: str | None = None, mfa_verified: bool = False,
) -> AccountableAdvance:
    """Решение по выдаче. Крупная выдача (R4) требует MFA (человек в контуре)."""
    if decision not in ("approved", "rejected"):
        raise AccountableStateError(f"неизвестное решение '{decision}'")
    if advance.status != "pending_approval" or advance.approval_id is None:
        raise AccountableStateError("нет активного запроса на согласование выдачи")
    if decision == "approved" and advance.risk_level == "R4" and not mfa_verified:
        raise AccountableAuthorizationError(
            "крупная выдача (R4) требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, advance.approval_id)
    session.add(ApprovalStep(
        approval_id=approval.id, step_number=approval.current_step,
        approver_user_id=user.id, decision=decision, comment=comment,
        decided_at=datetime.now(UTC),
    ))
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    if decision == "approved":
        advance.status = "approved"
        advance.approved_by_user_id = user.id
    else:
        advance.status = "draft"
    record_event(
        session, actor_type="user", action=f"accountable.advance.{decision}",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="accountable_advance", entity_id=advance.id, approval_id=approval.id,
        reason=comment, risk_level=advance.risk_level, commit=False,
    )
    session.commit()
    return advance


def issue_advance(session: Session, advance: AccountableAdvance, *, user, payment_reference: str | None = None) -> AccountableAdvance:
    """Фиксирует фактическую выдачу средств (после согласования)."""
    if advance.status != "approved":
        raise AccountableStateError("выдать можно только согласованную сумму")
    advance.status = "issued"
    advance.issued_at = datetime.now(UTC)
    advance.payment_reference = payment_reference
    advance.balance_amount = _q(Decimal(advance.amount_issued))
    record_event(
        session, actor_type="user", action="accountable.advance.issued",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="accountable_advance", entity_id=advance.id, risk_level="R3", commit=False,
    )
    session.commit()
    return advance


# ------------------------------- Расходы -------------------------------- #


def add_expense(
    session: Session, advance: AccountableAdvance, *, user,
    expense_category_id: uuid.UUID, amount: Decimal, expense_date: date,
    description: str, supplier_id: uuid.UUID | None = None,
    vat_amount: Decimal | None = None, payment_method: str = "cash",
    created_from_mobile: bool = False,
) -> AccountableExpense:
    """Добавляет расход к выданной сумме. Проверяет лимит статьи."""
    if advance.status not in ("issued", "partially_reported"):
        raise AccountableStateError("расходы можно добавлять только к выданной сумме")
    if Decimal(amount) <= 0:
        raise AccountableValidationError("сумма расхода должна быть > 0")
    category = session.get(ExpenseCategory, expense_category_id)
    if category is None:
        raise AccountableValidationError("статья расходов не найдена")
    if category.default_limit is not None and Decimal(amount) > Decimal(category.default_limit):
        raise AccountableValidationError(
            f"сумма превышает лимит статьи ({category.default_limit})"
        )
    expense = AccountableExpense(
        advance_id=advance.id, organization_id=advance.organization_id,
        employee_id=advance.employee_id, project_id=advance.project_id,
        site_id=advance.site_id, task_id=advance.task_id, supplier_id=supplier_id,
        expense_category_id=expense_category_id, expense_date=expense_date,
        description=description, amount=_q(Decimal(amount)),
        currency_code=advance.currency_code,
        vat_amount=_q(Decimal(vat_amount)) if vat_amount is not None else None,
        payment_method=payment_method, receipt_required=bool(category.requires_receipt),
        document_status="missing", verification_status="submitted",
        created_from_mobile=created_from_mobile, created_by=user.id,
    )
    session.add(expense)
    session.flush()
    if advance.status == "issued":
        advance.status = "partially_reported"
    record_event(
        session, actor_type="user", action="accountable.expense.added",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="accountable_expense", entity_id=expense.id,
        new_values={"amount": str(expense.amount)}, commit=False,
    )
    session.commit()
    return expense


def attach_document(
    session: Session, expense: AccountableExpense, *, user, duplicate_hash: str,
    file_id: uuid.UUID | None = None, document_type: str = "receipt",
    document_number: str | None = None, document_date: date | None = None,
    seller_name: str | None = None, extracted_amount: Decimal | None = None,
) -> ExpenseDocument:
    """Прикрепляет подтверждающий документ. Один чек нельзя использовать повторно."""
    if not duplicate_hash:
        raise AccountableValidationError("не задан отпечаток документа (duplicate_hash)")
    existing = session.execute(
        select(ExpenseDocument).where(ExpenseDocument.duplicate_hash == duplicate_hash)
    ).scalars().first()
    if existing is not None:
        raise AccountableValidationError("этот документ уже использован (дубликат чека)")
    doc = ExpenseDocument(
        expense_id=expense.id, organization_id=expense.organization_id, file_id=file_id,
        document_type=document_type, document_number=document_number,
        document_date=document_date, seller_name=seller_name,
        extracted_amount=_q(Decimal(extracted_amount)) if extracted_amount is not None else None,
        ocr_status="not_required", duplicate_hash=duplicate_hash,
    )
    session.add(doc)
    expense.document_status = "attached"
    record_event(
        session, actor_type="user", action="accountable.document.attached",
        actor_user_id=user.id, organization_id=expense.organization_id,
        entity_type="expense_document", entity_id=expense.id, commit=False,
    )
    session.commit()
    return doc


def verify_expense(
    session: Session, expense: AccountableExpense, advance: AccountableAdvance, *,
    user, decision: str, reason: str | None = None,
) -> AccountableExpense:
    """Проверка расхода бухгалтером/руководителем (R2). Требует чек, если обязателен."""
    if decision not in ("approved", "rejected"):
        raise AccountableStateError(f"неизвестное решение '{decision}'")
    if expense.verification_status in ("approved", "rejected"):
        raise AccountableStateError("расход уже проверен")
    if decision == "approved" and expense.receipt_required and expense.document_status == "missing":
        raise AccountableValidationError("для расхода обязателен подтверждающий документ")
    expense.verification_status = decision
    expense.verified_by_user_id = user.id
    expense.verified_at = datetime.now(UTC)
    if decision == "rejected":
        expense.rejection_reason = reason
    else:
        expense.document_status = "verified" if expense.document_status == "attached" else expense.document_status
    _recompute_advance(session, advance)
    record_event(
        session, actor_type="user", action=f"accountable.expense.{decision}",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="accountable_expense", entity_id=expense.id, reason=reason,
        risk_level="R2", commit=False,
    )
    session.commit()
    return expense


def _recompute_advance(session: Session, advance: AccountableAdvance) -> None:
    """Пересчитывает подтверждённые расходы и остаток выдачи."""
    approved = session.execute(
        select(AccountableExpense).where(
            AccountableExpense.advance_id == advance.id,
            AccountableExpense.verification_status == "approved",
            AccountableExpense.deleted_at.is_(None),
        )
    ).scalars()
    spent = _q(sum((Decimal(e.amount or 0) for e in approved), Decimal("0")))
    issued = Decimal(advance.amount_issued or 0)
    advance.amount_spent_confirmed = spent
    advance.balance_amount = _q(issued - spent)
    advance.amount_reimbursable = _q(spent - issued) if spent > issued else Decimal("0.00")


# --------------------------- Авансовый отчёт ---------------------------- #


def submit_report(session: Session, advance: AccountableAdvance, *, user) -> AdvanceReport:
    """Формирует авансовый отчёт из проверенных расходов (на проверку бухгалтеру)."""
    if advance.status not in ("issued", "partially_reported"):
        raise AccountableStateError(f"нельзя сформировать отчёт из '{advance.status}'")
    expenses = list(session.execute(
        select(AccountableExpense).where(
            AccountableExpense.advance_id == advance.id,
            AccountableExpense.deleted_at.is_(None),
        )
    ).scalars())
    if not expenses:
        raise AccountableValidationError("нет расходов для авансового отчёта")
    submitted = _q(sum((Decimal(e.amount or 0) for e in expenses), Decimal("0")))
    approved = _q(sum((Decimal(e.amount or 0) for e in expenses if e.verification_status == "approved"), Decimal("0")))
    issued = Decimal(advance.amount_issued or 0)
    report = AdvanceReport(
        advance_id=advance.id, submitted_by_employee_id=advance.employee_id,
        submitted_at=datetime.now(UTC), total_expenses_submitted=submitted,
        total_expenses_approved=approved,
        amount_to_return=_q(issued - approved) if issued > approved else Decimal("0.00"),
        amount_to_reimburse=_q(approved - issued) if approved > issued else Decimal("0.00"),
        status="submitted",
    )
    session.add(report)
    session.flush()
    advance.status = "under_accounting_review"
    record_event(
        session, actor_type="user", action="accountable.report.submitted",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="advance_report", entity_id=report.id, commit=False,
    )
    session.commit()
    return report


def review_report(
    session: Session, report: AdvanceReport, advance: AccountableAdvance, *,
    user, decision: str, comment: str | None = None,
) -> AdvanceReport:
    """Проверка авансового отчёта бухгалтером (R2). Определяет возврат/возмещение."""
    if decision not in ("approved", "correction_required"):
        raise AccountableStateError(f"неизвестное решение '{decision}'")
    if report.status not in ("submitted", "under_review"):
        raise AccountableStateError("отчёт уже проверен")
    report.accountant_user_id = user.id
    report.accountant_reviewed_at = datetime.now(UTC)
    if decision == "correction_required":
        report.status = "correction_required"
        advance.status = "correction_required"
    else:
        _recompute_advance(session, advance)
        report.total_expenses_approved = advance.amount_spent_confirmed
        issued = Decimal(advance.amount_issued or 0)
        spent = Decimal(advance.amount_spent_confirmed or 0)
        report.amount_to_return = _q(issued - spent) if issued > spent else Decimal("0.00")
        report.amount_to_reimburse = _q(spent - issued) if spent > issued else Decimal("0.00")
        report.status = "approved"
        report.approved_by_user_id = user.id
        report.approved_at = datetime.now(UTC)
        if report.amount_to_return > 0:
            advance.status = "awaiting_return"
        elif report.amount_to_reimburse > 0:
            advance.status = "awaiting_reimbursement"
        else:
            advance.status = "closed"
            advance.closed_at = datetime.now(UTC)
            advance.closed_by_user_id = user.id
    record_event(
        session, actor_type="user", action=f"accountable.report.{decision}",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="advance_report", entity_id=report.id, reason=comment,
        risk_level="R2", commit=False,
    )
    session.commit()
    return report


# ------------------------- Возврат / возмещение ------------------------- #


def settle(
    session: Session, advance: AccountableAdvance, *, user, settlement_type: str,
    amount: Decimal, report_id: uuid.UUID | None = None, payment_method: str = "cash",
    payment_reference: str | None = None, idempotency_key: str | None = None,
) -> AdvanceSettlement:
    """Фиксирует возврат остатка или возмещение перерасхода (не банковская операция).

    Идемпотентно по `idempotency_key`. После полного расчёта выдача закрывается.
    """
    if settlement_type not in ("return", "reimbursement"):
        raise AccountableStateError(f"неизвестный тип расчёта '{settlement_type}'")
    if advance.status not in ("awaiting_return", "awaiting_reimbursement"):
        raise AccountableStateError("расчёт возможен только после проверки отчёта")
    if idempotency_key:
        existing = session.execute(
            select(AdvanceSettlement).where(AdvanceSettlement.idempotency_key == idempotency_key)
        ).scalars().first()
        if existing is not None:
            return existing
    amt = _q(Decimal(amount))
    if amt <= 0:
        raise AccountableValidationError("сумма расчёта должна быть > 0")
    settlement = AdvanceSettlement(
        advance_id=advance.id, report_id=report_id, settlement_type=settlement_type,
        amount=amt, currency_code=advance.currency_code, settled_at=datetime.now(UTC),
        payment_method=payment_method, payment_reference=payment_reference,
        processed_by_user_id=user.id, status="recorded", idempotency_key=idempotency_key,
    )
    session.add(settlement)
    if settlement_type == "return":
        advance.amount_returned = _q(Decimal(advance.amount_returned or 0) + amt)
    else:
        advance.amount_reimbursable = _q(max(Decimal(advance.amount_reimbursable or 0) - amt, Decimal("0")))
    # закрытие при полном расчёте
    if settlement_type == "return" and advance.amount_returned >= advance.balance_amount:
        advance.status = "closed"
        advance.closed_at = datetime.now(UTC)
        advance.closed_by_user_id = user.id
    if settlement_type == "reimbursement" and advance.amount_reimbursable <= 0:
        advance.status = "closed"
        advance.closed_at = datetime.now(UTC)
        advance.closed_by_user_id = user.id
    record_event(
        session, actor_type="user", action=f"accountable.settlement.{settlement_type}",
        actor_user_id=user.id, organization_id=advance.organization_id,
        entity_type="advance_settlement", entity_id=settlement.id,
        new_values={"amount": str(amt)}, risk_level="R2", commit=False,
    )
    session.commit()
    return settlement


# ------------------------------- Сводка --------------------------------- #


@dataclass
class AccountableSummary:
    advances_open: int
    advances_overdue: int
    total_issued: Decimal
    total_spent: Decimal
    total_outstanding: Decimal
    reports_pending: int


def accountable_summary(session: Session, organization_id: uuid.UUID) -> AccountableSummary:
    """Сводка по подотчётным средствам организации."""
    advances = list(session.execute(
        select(AccountableAdvance).where(
            AccountableAdvance.organization_id == organization_id,
            AccountableAdvance.deleted_at.is_(None),
        )
    ).scalars())
    now = datetime.now(UTC)

    def _overdue(a: AccountableAdvance) -> bool:
        if a.report_due_at is None or a.status in ("closed", "cancelled"):
            return False
        due = a.report_due_at if a.report_due_at.tzinfo else a.report_due_at.replace(tzinfo=UTC)
        return due < now and a.status not in ("reported", "under_accounting_review")

    open_adv = [a for a in advances if a.status not in ("closed", "cancelled")]
    issued = _q(sum((Decimal(a.amount_issued or 0) for a in advances), Decimal("0")))
    spent = _q(sum((Decimal(a.amount_spent_confirmed or 0) for a in advances), Decimal("0")))
    outstanding = _q(sum((Decimal(a.balance_amount or 0) for a in open_adv if Decimal(a.balance_amount or 0) > 0), Decimal("0")))
    reports_pending = len(list(session.execute(
        select(AdvanceReport).join(
            AccountableAdvance, AdvanceReport.advance_id == AccountableAdvance.id
        ).where(
            AccountableAdvance.organization_id == organization_id,
            AdvanceReport.status.in_(("submitted", "under_review")),
        )
    ).scalars()))
    return AccountableSummary(
        advances_open=len(open_adv), advances_overdue=len([a for a in advances if _overdue(a)]),
        total_issued=issued, total_spent=spent, total_outstanding=outstanding,
        reports_pending=reports_pending,
    )


def can_access_advance_project(session: Session, user, advance: AccountableAdvance) -> bool:
    if advance.project_id is None:
        return True
    return can_access_project(session, user, advance.project_id)
