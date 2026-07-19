"""Бизнес-логика модуля «Персонал объектов».

Ключевые правила:
- предварительный расчёт начислений (ФОТ) — точные вычисления Decimal;
- выплата и критические изменения проходят согласование R3/R4 (D-001, D-002):
  ИИ/сервис только готовит расчёт, окончательную выплату подтверждает человек;
- работник не может быть отмечен допущенным/отработавшим без обязательных
  документов охраны труда (инструктажи, медосмотр, действующие допуски);
- все значимые действия записываются в `audit_events` (append-only).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    PayrollDraft,
    PayrollLine,
    SafetyClearance,
    Site,
    User,
    WorkPermit,
)
from app.services.access import can_access_project
from app.services.audit import record_event

CENTS = Decimal("0.01")

# Порог отнесения выплаты к критическому уровню R4 (крупная сумма).
PAYOUT_R4_AMOUNT = Decimal("1000000.00")
# Массовая выплата (много строк) также относится к R4 (принцип ACCESS_CONTROL 9.5).
PAYOUT_R4_LINES = 50


def _money(value: Decimal | int | float | str) -> Decimal:
    return Decimal(str(value)).quantize(CENTS, rounding=ROUND_HALF_UP)


# --------------------------- Расчёт начислений --------------------------- #


def compute_line(
    *,
    rate: Decimal | float | str,
    quantity: Decimal | float | str,
    advance: Decimal | float | str = 0,
    deduction: Decimal | float | str = 0,
) -> tuple[Decimal, Decimal]:
    """Возвращает (начислено, к выплате).

    Единая формула для всех схем (почасовая/посменная/окладная/сдельная):
    начислено = ставка × количество; к выплате = начислено − аванс − удержания.
    """
    accrued = _money(Decimal(str(rate)) * Decimal(str(quantity)))
    to_pay = _money(accrued - _money(advance) - _money(deduction))
    return accrued, to_pay


def payout_risk_level(total_to_pay: Decimal, line_count: int) -> str:
    """Уровень риска выплаты: R4 для крупной/массовой, иначе R3 (D-001)."""
    if total_to_pay >= PAYOUT_R4_AMOUNT or line_count >= PAYOUT_R4_LINES:
        return "R4"
    return "R3"


def recalc_draft(session: Session, draft: PayrollDraft) -> PayrollDraft:
    """Пересчитывает строки и итоги расчёта, проставляет уровень риска выплаты."""
    lines = list(
        session.execute(
            select(PayrollLine).where(PayrollLine.payroll_draft_id == draft.id)
        ).scalars()
    )
    total_accrued = Decimal("0.00")
    total_advance = Decimal("0.00")
    total_deduction = Decimal("0.00")
    total_to_pay = Decimal("0.00")
    for line in lines:
        accrued, to_pay = compute_line(
            rate=line.rate,
            quantity=line.quantity,
            advance=line.advance,
            deduction=line.deduction,
        )
        line.accrued = accrued
        line.to_pay = to_pay
        total_accrued += accrued
        total_advance += _money(line.advance)
        total_deduction += _money(line.deduction)
        total_to_pay += to_pay
    draft.total_accrued = _money(total_accrued)
    draft.total_advance = _money(total_advance)
    draft.total_deduction = _money(total_deduction)
    draft.total_to_pay = _money(total_to_pay)
    draft.risk_level = payout_risk_level(draft.total_to_pay, len(lines))
    return draft


# ---------------------- Охрана труда: допуск к работе -------------------- #


@dataclass
class ClearanceResult:
    cleared: bool
    reasons: list[str]


def evaluate_clearance(
    clearance: SafetyClearance | None,
    permits: list[WorkPermit],
    *,
    on_date: date,
    required_permits: tuple[str, ...] = (),
) -> ClearanceResult:
    """Проверяет допуск работника к работе на дату.

    Требуется: вводный и первичный инструктажи, подпись работника, действующий
    медосмотр и все необходимые специальные допуски без просрочки. Работника
    нельзя отметить допущенным без обязательных документов.
    """
    reasons: list[str] = []
    if clearance is None:
        return ClearanceResult(False, ["отсутствует карточка охраны труда"])
    if clearance.intro_briefing_at is None:
        reasons.append("нет вводного инструктажа")
    if clearance.primary_briefing_at is None:
        reasons.append("нет первичного инструктажа")
    if not clearance.signed_by_worker:
        reasons.append("инструктаж не подписан работником")
    if clearance.medical_valid_until is None or clearance.medical_valid_until < on_date:
        reasons.append("медосмотр отсутствует или просрочен")

    by_type = {p.permit_type: p for p in permits}
    for req in required_permits:
        permit = by_type.get(req)
        if permit is None:
            reasons.append(f"нет допуска: {req}")
        elif permit.valid_until is not None and permit.valid_until < on_date:
            reasons.append(f"просрочен допуск: {req}")
        elif permit.status != "active":
            reasons.append(f"допуск неактивен: {req}")

    return ClearanceResult(len(reasons) == 0, reasons)


def refresh_clearance_status(
    session: Session,
    clearance: SafetyClearance,
    *,
    on_date: date | None = None,
    required_permits: tuple[str, ...] = (),
) -> SafetyClearance:
    """Пересчитывает и сохраняет итоговый статус допуска работника."""
    on = on_date or datetime.now(UTC).date()
    permits = list(
        session.execute(
            select(WorkPermit).where(WorkPermit.clearance_id == clearance.id)
        ).scalars()
    )
    result = evaluate_clearance(
        clearance, permits, on_date=on, required_permits=required_permits
    )
    clearance.status = "cleared" if result.cleared else "not_cleared"
    return clearance


class ClearanceRequiredError(RuntimeError):
    """Работник не допущен: попытка отметить отработанное время без документов."""


def assert_can_mark_worked(
    session: Session,
    *,
    employee_id: uuid.UUID,
    on_date: date,
    required_permits: tuple[str, ...] = (),
) -> None:
    """Гейт охраны труда: запрещает засчитывать часы работнику без допуска."""
    clearance = session.execute(
        select(SafetyClearance).where(SafetyClearance.employee_id == employee_id)
    ).scalars().first()
    permits: list[WorkPermit] = []
    if clearance is not None:
        permits = list(
            session.execute(
                select(WorkPermit).where(WorkPermit.clearance_id == clearance.id)
            ).scalars()
        )
    result = evaluate_clearance(
        clearance, permits, on_date=on_date, required_permits=required_permits
    )
    if not result.cleared:
        raise ClearanceRequiredError("; ".join(result.reasons))


# ------------------- Согласование выплаты (R3/R4) ------------------------ #


class PayrollStateError(RuntimeError):
    """Недопустимый переход состояния расчёта начислений."""


def request_payout(
    session: Session,
    draft: PayrollDraft,
    *,
    user: User,
    request_id: str | None = None,
) -> Approval:
    """Создаёт согласование выплаты (R3/R4). Выплата не проводится автоматически."""
    if draft.status not in ("draft", "foreman_checked"):
        raise PayrollStateError(
            f"нельзя запросить выплату из состояния '{draft.status}'"
        )
    recalc_draft(session, draft)
    approval = Approval(
        organization_id=draft.organization_id,
        entity_type="payroll_draft",
        entity_id=draft.id,
        approval_type="payroll_payout",
        requested_by_user_id=user.id,
        status="pending",
        current_step=1,
    )
    session.add(approval)
    session.flush()
    draft.approval_id = approval.id
    draft.status = "pending_approval"
    record_event(
        session,
        actor_type="user",
        action="payroll.payout.requested",
        actor_user_id=user.id,
        organization_id=draft.organization_id,
        entity_type="payroll_draft",
        entity_id=draft.id,
        new_values={
            "total_to_pay": str(draft.total_to_pay),
            "risk_level": draft.risk_level,
        },
        approval_id=approval.id,
        risk_level=draft.risk_level,
        commit=False,
    )
    session.commit()
    return approval


class PayoutAuthorizationError(RuntimeError):
    """Недостаточно условий для подтверждения выплаты (например, нет MFA для R4)."""


def record_payout_decision(
    session: Session,
    draft: PayrollDraft,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
    mfa_verified: bool = False,
    request_id: str | None = None,
) -> Approval:
    """Фиксирует решение человека по выплате (approved|rejected).

    Действие уровня R4 требует усиленной аутентификации (D-002): подтверждение
    выполняется только при `mfa_verified=True`.
    """
    if decision not in ("approved", "rejected"):
        raise PayrollStateError(f"неизвестное решение '{decision}'")
    if draft.approval_id is None or draft.status != "pending_approval":
        raise PayrollStateError("нет активного запроса на согласование выплаты")
    if decision == "approved" and draft.risk_level == "R4" and not mfa_verified:
        raise PayoutAuthorizationError(
            "выплата уровня R4 требует подтверждения усиленной аутентификацией"
        )

    approval = session.get(Approval, draft.approval_id)
    if approval is None:
        raise PayrollStateError("согласование не найдено")
    step = ApprovalStep(
        approval_id=approval.id,
        step_number=approval.current_step,
        approver_user_id=user.id,
        decision=decision,
        comment=comment,
        decided_at=datetime.now(UTC),
    )
    session.add(step)
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    draft.status = "approved" if decision == "approved" else "rejected"
    if decision == "approved":
        for line in session.execute(
            select(PayrollLine).where(PayrollLine.payroll_draft_id == draft.id)
        ).scalars():
            line.status = "approved"
    record_event(
        session,
        actor_type="user",
        action=f"payroll.payout.{decision}",
        actor_user_id=user.id,
        organization_id=draft.organization_id,
        entity_type="payroll_draft",
        entity_id=draft.id,
        new_values={"decision": decision, "risk_level": draft.risk_level},
        approval_id=approval.id,
        reason=comment,
        risk_level=draft.risk_level,
        commit=False,
    )
    session.commit()
    return approval


# ------------------------- Доступ по объекту (ABAC) ---------------------- #


def can_access_site(session: Session, user: User, site: Site) -> bool:
    """Изоляция по объектам: доступ к объекту — через доступ к его проекту."""
    return can_access_project(session, user, site.project_id)
