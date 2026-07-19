"""Бизнес-логика модуля «Финансы и бюджеты».

Правила:
- базовый бюджет формируется из утверждённой сметы (`estimates`); суммы не
  копируются как «план-факт», а берутся из сметных итогов;
- ручная статья бюджета допускается только для расхода вне сметы, с обязательным
  указанием источника (`source_reference`) и согласованием (R3/R4 + MFA);
- утверждение бюджета — R3 (крупный бюджет ≥ порога организации — R4 + MFA);
- финансовая сводка проекта агрегирует существующие данные без дублирования:
  план — из бюджета/сметы; обязательства — из `purchase_orders`, расходных
  `contracts` и ручных `financial_commitments`; факт — из полученных заказов и
  утверждённого ФОТ (`payroll_drafts`);
- система не проводит банковских операций; все значимые действия — в
  `audit_events`; все расчёты — Decimal.
"""

from __future__ import annotations

import csv
import io
import json
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    Budget,
    BudgetLine,
    Contract,
    Counterparty,
    Estimate,
    FinanceSettings,
    FinancialCommitment,
    PayrollDraft,
    Project,
    PurchaseOrder,
    Site,
    User,
)
from app.services.access import can_access_project
from app.services.audit import record_event

DEFAULT_LARGE_THRESHOLD = Decimal("10000000.00")

# Статусы заказов: обязательства (ещё не получены) и факт (получены).
PO_COMMITTED = ("approved", "sent", "partially_received")
PO_ACTUAL = ("received", "closed")
# Расходные договоры (не заказчик) в активных статусах — обязательства.
CONTRACT_COMMITTED = ("approved", "signed", "active")
CONTRACT_EXPENSE_TYPES = ("contractor", "supplier", "designer", "other")
# ФОТ, попавший в факт.
PAYROLL_ACTUAL = ("approved", "exported")


class FinanceStateError(RuntimeError):
    """Недопустимый переход состояния финансовой сущности."""


class FinanceValidationError(RuntimeError):
    """Нарушение бизнес-правила (например, ручная статья без источника)."""


class FinanceAuthorizationError(RuntimeError):
    """Недостаточно условий для подтверждения (например, отсутствует MFA для R4)."""


def _q(value: Decimal) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


# ------------------------------ Настройки ------------------------------- #


def large_threshold(session: Session, organization_id: uuid.UUID) -> Decimal:
    """Порог крупной финансовой операции (R4) для организации."""
    s = session.execute(
        select(FinanceSettings).where(
            FinanceSettings.organization_id == organization_id
        )
    ).scalars().first()
    if s is None:
        return DEFAULT_LARGE_THRESHOLD
    return Decimal(s.large_operation_threshold)


def operation_risk_level(amount: Decimal, *, threshold: Decimal) -> str:
    """Уровень риска финансовой операции: R4 для крупной суммы, иначе R3."""
    return "R4" if Decimal(amount) >= threshold else "R3"


# --------------------- Формирование бюджета из сметы -------------------- #

# Плановые статьи базового бюджета — сметные итоги (без дублирования позиций).
_ESTIMATE_BUCKETS = [
    ("MAT", "material", "Материалы", "material_total"),
    ("LAB", "labor", "Труд (ФОТ)", "labor_total"),
    ("MCH", "machine", "Машины и механизмы", "machine_total"),
    ("OVH", "overhead", "Накладные расходы", "overhead_total"),
    ("PRF", "other", "Сметная прибыль", "profit_total"),
]


def build_budget_from_estimate(
    session: Session, project: Project, estimate: Estimate, *, user: User
) -> Budget:
    """Создаёт черновик бюджета проекта из утверждённой сметы (план = итоги сметы)."""
    if estimate.status != "approved":
        raise FinanceValidationError("бюджет формируется только из утверждённой сметы")
    if estimate.project_id != project.id:
        raise FinanceValidationError("смета относится к другому проекту")
    existing = session.execute(
        select(Budget).where(
            Budget.project_id == project.id,
            Budget.source_estimate_id == estimate.id,
            Budget.deleted_at.is_(None),
        )
    ).scalars().first()
    if existing is not None:
        raise FinanceStateError("бюджет по этой смете уже сформирован")
    budget = Budget(
        organization_id=project.organization_id,
        project_id=project.id,
        source_estimate_id=estimate.id,
        name=f"Бюджет проекта · смета {estimate.number or estimate.name}",
        currency=estimate.currency,
        status="draft",
        created_by=user.id,
    )
    session.add(budget)
    session.flush()
    planned_total = Decimal("0")
    for cost_code, category, title, attr in _ESTIMATE_BUCKETS:
        amount = _q(Decimal(getattr(estimate, attr) or 0))
        if amount <= 0:
            continue
        session.add(
            BudgetLine(
                budget_id=budget.id, cost_code=cost_code, category=category,
                description=title, planned_amount=amount, source="estimate",
                is_manual=False, status="approved",
            )
        )
        planned_total += amount
    budget.planned_total = _q(planned_total)
    record_event(
        session, actor_type="user", action="finance.budget.created_from_estimate",
        actor_user_id=user.id, organization_id=budget.organization_id,
        entity_type="budget", entity_id=budget.id,
        new_values={"estimate_id": str(estimate.id), "planned_total": str(budget.planned_total)},
        commit=False,
    )
    session.commit()
    return budget


def recompute_budget_totals(session: Session, budget: Budget) -> Budget:
    """Пересчитывает плановую/утверждённую суммы бюджета по действующим статьям."""
    lines = list(
        session.execute(
            select(BudgetLine).where(
                BudgetLine.budget_id == budget.id,
                BudgetLine.status != "rejected",
            )
        ).scalars()
    )
    budget.planned_total = _q(sum((Decimal(l.planned_amount or 0) for l in lines), Decimal("0")))
    budget.approved_total = _q(sum((Decimal(l.approved_amount or 0) for l in lines), Decimal("0")))
    return budget


# ------------------------- Ручные статьи бюджета ------------------------ #


def add_manual_line(
    session: Session,
    budget: Budget,
    *,
    user: User,
    description: str,
    amount: Decimal,
    source_reference: str,
    category: str = "other",
    expense_category_id: uuid.UUID | None = None,
    cost_code: str | None = None,
) -> BudgetLine:
    """Добавляет ручную статью (расход вне сметы). Требует источник и согласование."""
    if not source_reference or not source_reference.strip():
        raise FinanceValidationError(
            "для ручной статьи обязателен источник (source_reference)"
        )
    if Decimal(amount) <= 0:
        raise FinanceValidationError("сумма ручной статьи должна быть > 0")
    threshold = large_threshold(session, budget.organization_id)
    risk = operation_risk_level(Decimal(amount), threshold=threshold)
    approval = Approval(
        organization_id=budget.organization_id, entity_type="budget_line",
        entity_id=budget.id, approval_type="budget_manual_line",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    line = BudgetLine(
        budget_id=budget.id, expense_category_id=expense_category_id,
        cost_code=cost_code, category=category, description=description,
        planned_amount=_q(Decimal(amount)), source="manual", is_manual=True,
        source_reference=source_reference, status="pending_approval",
        approval_id=approval.id,
    )
    session.add(line)
    session.flush()
    approval.entity_id = line.id
    record_event(
        session, actor_type="user", action="finance.budget_line.manual_requested",
        actor_user_id=user.id, organization_id=budget.organization_id,
        entity_type="budget_line", entity_id=line.id, approval_id=approval.id,
        new_values={"amount": str(line.planned_amount), "source": source_reference},
        risk_level=risk, commit=False,
    )
    session.commit()
    return line


def decide_manual_line(
    session: Session,
    line: BudgetLine,
    budget: Budget,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
    mfa_verified: bool = False,
) -> BudgetLine:
    """Согласование/отклонение ручной статьи. Крупная сумма (R4) требует MFA."""
    if decision not in ("approved", "rejected"):
        raise FinanceStateError(f"неизвестное решение '{decision}'")
    if line.status != "pending_approval" or line.approval_id is None:
        raise FinanceStateError("нет активного запроса на согласование статьи")
    threshold = large_threshold(session, budget.organization_id)
    risk = operation_risk_level(Decimal(line.planned_amount or 0), threshold=threshold)
    if decision == "approved" and risk == "R4" and not mfa_verified:
        raise FinanceAuthorizationError(
            "крупная ручная статья (R4) требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, line.approval_id)
    session.add(
        ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        )
    )
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    line.status = "approved" if decision == "approved" else "rejected"
    if decision == "approved":
        line.approved_amount = line.planned_amount
    recompute_budget_totals(session, budget)
    record_event(
        session, actor_type="user", action=f"finance.budget_line.manual_{decision}",
        actor_user_id=user.id, organization_id=budget.organization_id,
        entity_type="budget_line", entity_id=line.id, approval_id=approval.id,
        reason=comment, risk_level=risk, commit=False,
    )
    session.commit()
    return line


# ----------------------------- Утверждение ------------------------------ #


def request_budget_approval(session: Session, budget: Budget, *, user: User) -> Approval:
    """Запрашивает утверждение бюджета (R3, крупный — R4)."""
    if budget.status not in ("draft",):
        raise FinanceStateError(f"нельзя утвердить бюджет из состояния '{budget.status}'")
    recompute_budget_totals(session, budget)
    if Decimal(budget.planned_total or 0) <= 0:
        raise FinanceValidationError("бюджет не содержит статей с положительной суммой")
    threshold = large_threshold(session, budget.organization_id)
    risk = operation_risk_level(Decimal(budget.planned_total or 0), threshold=threshold)
    approval = Approval(
        organization_id=budget.organization_id, entity_type="budget",
        entity_id=budget.id, approval_type="budget_approval",
        requested_by_user_id=user.id, status="pending", current_step=1,
    )
    session.add(approval)
    session.flush()
    budget.approval_id = approval.id
    budget.risk_level = risk
    budget.status = "pending_approval"
    record_event(
        session, actor_type="user", action="finance.budget.approval_requested",
        actor_user_id=user.id, organization_id=budget.organization_id,
        entity_type="budget", entity_id=budget.id, approval_id=approval.id,
        risk_level=risk, commit=False,
    )
    session.commit()
    return approval


def decide_budget(
    session: Session,
    budget: Budget,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
    mfa_verified: bool = False,
) -> Budget:
    """Фиксирует решение по бюджету. Крупный бюджет (R4) требует MFA."""
    if decision not in ("approved", "rejected"):
        raise FinanceStateError(f"неизвестное решение '{decision}'")
    if budget.status != "pending_approval" or budget.approval_id is None:
        raise FinanceStateError("нет активного запроса на утверждение бюджета")
    if decision == "approved" and budget.risk_level == "R4" and not mfa_verified:
        raise FinanceAuthorizationError(
            "крупный бюджет (R4) требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, budget.approval_id)
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
        # утверждаем плановые значения статей из сметы как approved_amount
        for line in session.execute(
            select(BudgetLine).where(
                BudgetLine.budget_id == budget.id,
                BudgetLine.status == "approved",
                BudgetLine.is_manual.is_(False),
            )
        ).scalars():
            if Decimal(line.approved_amount or 0) == 0:
                line.approved_amount = line.planned_amount
        recompute_budget_totals(session, budget)
        # предыдущие утверждённые бюджеты проекта — устаревшие
        for prev in session.execute(
            select(Budget).where(
                Budget.project_id == budget.project_id,
                Budget.status == "approved",
                Budget.id != budget.id,
            )
        ).scalars():
            prev.status = "superseded"
        budget.status = "approved"
        budget.approved_at = datetime.now(UTC)
        budget.approved_by = user.id
    else:
        budget.status = "draft"
    record_event(
        session, actor_type="user", action=f"finance.budget.{decision}",
        actor_user_id=user.id, organization_id=budget.organization_id,
        entity_type="budget", entity_id=budget.id, approval_id=approval.id,
        reason=comment, new_values={"approved_total": str(budget.approved_total)},
        risk_level=budget.risk_level, commit=False,
    )
    session.commit()
    return budget


# ---------------------- Ручные обязательства ---------------------------- #


def create_commitment(
    session: Session,
    project: Project,
    *,
    user: User,
    description: str,
    amount: Decimal,
    source_reference: str,
    counterparty_id: uuid.UUID | None = None,
    budget_line_id: uuid.UUID | None = None,
    due_date=None,
    mfa_verified: bool = False,
) -> FinancialCommitment:
    """Создаёт ручное обязательство («решение»). Крупное (R4) требует MFA."""
    if not source_reference or not source_reference.strip():
        raise FinanceValidationError("для обязательства обязателен источник")
    if Decimal(amount) <= 0:
        raise FinanceValidationError("сумма обязательства должна быть > 0")
    threshold = large_threshold(session, project.organization_id)
    risk = operation_risk_level(Decimal(amount), threshold=threshold)
    if risk == "R4" and not mfa_verified:
        raise FinanceAuthorizationError(
            "крупное обязательство (R4) требует подтверждения усиленной аутентификацией"
        )
    commitment = FinancialCommitment(
        organization_id=project.organization_id, project_id=project.id,
        budget_line_id=budget_line_id, counterparty_id=counterparty_id,
        source_type="manual", source_reference=source_reference,
        description=description, amount=_q(Decimal(amount)),
        currency=project.currency, due_date=due_date, status="open",
        risk_level=risk, created_by=user.id,
    )
    session.add(commitment)
    session.flush()
    record_event(
        session, actor_type="user", action="finance.commitment.created",
        actor_user_id=user.id, organization_id=project.organization_id,
        entity_type="financial_commitment", entity_id=commitment.id,
        new_values={"amount": str(commitment.amount), "source": source_reference},
        risk_level=risk, commit=False,
    )
    session.commit()
    return commitment


# ----------------------- Финансовая сводка проекта ---------------------- #


@dataclass
class SummaryComponent:
    label: str
    amount: Decimal
    source: str


@dataclass
class ProjectFinancialSummary:
    project_id: uuid.UUID
    currency: str
    approved_budget: Decimal
    planned_budget: Decimal
    committed: Decimal
    actual: Decimal
    remaining: Decimal
    forecast: Decimal
    forecast_deviation: Decimal
    committed_breakdown: list[SummaryComponent] = field(default_factory=list)
    actual_breakdown: list[SummaryComponent] = field(default_factory=list)
    has_approved_budget: bool = False


def _project_site_ids(session: Session, project_id: uuid.UUID) -> list[uuid.UUID]:
    return [
        r[0]
        for r in session.execute(
            select(Site.id).where(Site.project_id == project_id)
        ).all()
    ]


def project_financial_summary(
    session: Session, project: Project
) -> ProjectFinancialSummary:
    """Агрегирует бюджет, обязательства, факт, остаток и прогноз без дублирования."""
    # План: утверждённый бюджет проекта (иначе — плановый черновик).
    approved_budget = session.execute(
        select(Budget).where(
            Budget.project_id == project.id, Budget.status == "approved",
            Budget.deleted_at.is_(None),
        ).order_by(Budget.created_at.desc())
    ).scalars().first()
    any_budget = approved_budget or session.execute(
        select(Budget).where(
            Budget.project_id == project.id, Budget.deleted_at.is_(None),
        ).order_by(Budget.created_at.desc())
    ).scalars().first()
    approved_total = _q(Decimal(approved_budget.approved_total)) if approved_budget else Decimal("0.00")
    planned_total = _q(Decimal(any_budget.planned_total)) if any_budget else Decimal("0.00")

    # Обязательства: заказы (не полученные) + расходные договоры + ручные.
    po_committed = _q(sum((
        Decimal(po.total_amount or 0)
        for po in session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.project_id == project.id,
                PurchaseOrder.status.in_(PO_COMMITTED),
            )
        ).scalars()
    ), Decimal("0")))
    contract_committed = Decimal("0")
    for c in session.execute(
        select(Contract).where(
            Contract.project_id == project.id,
            Contract.status.in_(CONTRACT_COMMITTED),
            Contract.deleted_at.is_(None),
        )
    ).scalars():
        cp = session.get(Counterparty, c.counterparty_id)
        if cp is not None and cp.counterparty_type in CONTRACT_EXPENSE_TYPES:
            contract_committed += Decimal(c.amount or 0)
    contract_committed = _q(contract_committed)
    manual_committed = _q(sum((
        Decimal(m.amount or 0)
        for m in session.execute(
            select(FinancialCommitment).where(
                FinancialCommitment.project_id == project.id,
                FinancialCommitment.status == "open",
                FinancialCommitment.deleted_at.is_(None),
            )
        ).scalars()
    ), Decimal("0")))
    committed = _q(po_committed + contract_committed + manual_committed)

    # Факт: полученные заказы + утверждённый ФОТ по объектам проекта.
    po_actual = _q(sum((
        Decimal(po.total_amount or 0)
        for po in session.execute(
            select(PurchaseOrder).where(
                PurchaseOrder.project_id == project.id,
                PurchaseOrder.status.in_(PO_ACTUAL),
            )
        ).scalars()
    ), Decimal("0")))
    site_ids = _project_site_ids(session, project.id)
    payroll_actual = Decimal("0")
    if site_ids:
        payroll_actual = sum((
            Decimal(p.total_to_pay or 0)
            for p in session.execute(
                select(PayrollDraft).where(
                    PayrollDraft.site_id.in_(site_ids),
                    PayrollDraft.status.in_(PAYROLL_ACTUAL),
                    PayrollDraft.deleted_at.is_(None),
                )
            ).scalars()
        ), Decimal("0"))
    payroll_actual = _q(payroll_actual)
    actual = _q(po_actual + payroll_actual)

    base = approved_total if approved_budget else planned_total
    remaining = _q(base - actual)
    forecast = _q(actual + committed)
    deviation = _q(forecast - base)

    return ProjectFinancialSummary(
        project_id=project.id, currency=project.currency,
        approved_budget=approved_total, planned_budget=planned_total,
        committed=committed, actual=actual, remaining=remaining,
        forecast=forecast, forecast_deviation=deviation,
        has_approved_budget=approved_budget is not None,
        committed_breakdown=[
            SummaryComponent("Заказы поставщикам", po_committed, "purchase_orders"),
            SummaryComponent("Договоры (расходные)", contract_committed, "contracts"),
            SummaryComponent("Ручные обязательства", manual_committed, "financial_commitments"),
        ],
        actual_breakdown=[
            SummaryComponent("Полученные заказы", po_actual, "purchase_orders"),
            SummaryComponent("ФОТ (утверждённый)", payroll_actual, "payroll_drafts"),
        ],
    )


# ------------------------- Экспорт в бухгалтерию ------------------------ #


def export_summary(summary: ProjectFinancialSummary, *, fmt: str = "csv") -> str:
    """Экспорт финансовой сводки проекта в CSV или JSON (без интеграции с 1С)."""
    rows = [
        ("approved_budget", str(summary.approved_budget)),
        ("planned_budget", str(summary.planned_budget)),
        ("committed", str(summary.committed)),
        ("actual", str(summary.actual)),
        ("remaining", str(summary.remaining)),
        ("forecast", str(summary.forecast)),
        ("forecast_deviation", str(summary.forecast_deviation)),
    ]
    if fmt == "json":
        payload = {
            "project_id": str(summary.project_id),
            "currency": summary.currency,
            **{k: v for k, v in rows},
            "committed_breakdown": [
                {"label": c.label, "amount": str(c.amount), "source": c.source}
                for c in summary.committed_breakdown
            ],
            "actual_breakdown": [
                {"label": c.label, "amount": str(c.amount), "source": c.source}
                for c in summary.actual_breakdown
            ],
        }
        return json.dumps(payload, ensure_ascii=False, indent=2)
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["metric", "amount", "currency"])
    for key, value in rows:
        writer.writerow([key, value, summary.currency])
    return buf.getvalue()


# ------------------------------- Доступ --------------------------------- #


def can_access_finance_project(session: Session, user: User, project_id: uuid.UUID) -> bool:
    return can_access_project(session, user, project_id)
