"""Бизнес-логика модуля «Сметы и ценообразование».

Правила:
- все денежные расчёты — Decimal, с правилом округления сметы;
- раздельный учёт материалов, труда и машин; накладные, сметная прибыль, наценка,
  НДС, коэффициенты и индексация;
- утверждение пустой или некорректно рассчитанной сметы запрещено;
- прямое изменение утверждённой сметы запрещено — только новая версия или
  change order; причины изменения цены/объёма фиксируются в журнале;
- коммерческое предложение проходит согласование R3 (обычная сумма) или R4 + MFA
  (крупная/массовая), порог настраивается для организации (`pricing_settings`);
- план-факт формируется из утверждённой сметы (baseline) и фактических данных
  (`daily_report_work_items`);
- все значимые действия — в `audit_events`.

Импорт нормативных баз (ГЭСН/ФЕР/ТЕР) в MVP не выполняется, но заложен интерфейс
адаптеров `RateImportProvider` для будущего импортера.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    CommercialOffer,
    DailyReportWorkItem,
    Estimate,
    EstimateChange,
    EstimatePosition,
    PricingSettings,
    Project,
    User,
)
from app.services.access import can_access_project
from app.services.audit import record_event

# Значения по умолчанию, если у организации нет строки pricing_settings.
DEFAULT_OFFER_R4_AMOUNT = Decimal("1000000.00")
DEFAULT_OFFER_R4_POSITIONS = 100
APPROVAL_RISK = "R2"


class EstimateStateError(RuntimeError):
    """Недопустимый переход состояния или изменение утверждённой сметы."""


class EstimateValidationError(RuntimeError):
    """Смета пуста или рассчитана некорректно — утверждение запрещено."""


class OfferAuthorizationError(RuntimeError):
    """Недостаточно условий для подтверждения предложения (например, нет MFA)."""


def _round(value: Decimal, rounding: str) -> Decimal:
    q = Decimal(rounding or "0.01")
    return Decimal(value).quantize(q, rounding=ROUND_HALF_UP)


def _pct(base: Decimal, percent: Decimal) -> Decimal:
    return base * Decimal(percent) / Decimal(100)


# ----------------------- Интерфейс импортера расценок -------------------- #


@dataclass
class ImportedRate:
    code: str
    name: str
    unit: str | None
    material_cost: Decimal
    labor_cost: Decimal
    machine_cost: Decimal
    source: str


class RateImportProvider(Protocol):
    """Адаптер импорта расценок (ГЭСН/ФЕР/ТЕР и др.). В MVP не используется."""

    def load(self, reference: str) -> list[ImportedRate]: ...


# ----------------------------- Расчёт сметы ------------------------------ #


@dataclass
class PositionComputed:
    material: Decimal
    labor: Decimal
    machine: Decimal
    direct: Decimal
    overhead: Decimal
    profit: Decimal
    total: Decimal


def compute_position(pos: EstimatePosition, rounding: str) -> PositionComputed:
    """Рассчитывает составляющие и итог позиции сметы (Decimal)."""
    coeff = Decimal(pos.coefficient or 1)
    qty = Decimal(pos.quantity or 0)
    material = _round(Decimal(pos.material_unit_cost or 0) * coeff * qty, rounding)
    labor = _round(Decimal(pos.labor_unit_cost or 0) * coeff * qty, rounding)
    machine = _round(Decimal(pos.machine_unit_cost or 0) * coeff * qty, rounding)
    direct = _round(material + labor + machine, rounding)
    overhead = _round(_pct(direct, Decimal(pos.overhead_percent or 0)), rounding)
    profit = _round(_pct(direct + overhead, Decimal(pos.profit_percent or 0)), rounding)
    total = _round(direct + overhead + profit, rounding)
    return PositionComputed(material, labor, machine, direct, overhead, profit, total)


def recalc_estimate(session: Session, estimate: Estimate) -> Estimate:
    """Пересчитывает все позиции и итоги сметы с индексацией и НДС."""
    rounding = estimate.rounding or "0.01"
    positions = list(
        session.execute(
            select(EstimatePosition).where(
                EstimatePosition.estimate_id == estimate.id
            )
        ).scalars()
    )
    material = labor = machine = direct = overhead = profit = Decimal("0")
    for pos in positions:
        c = compute_position(pos, rounding)
        pos.position_direct = c.direct
        pos.position_overhead = c.overhead
        pos.position_profit = c.profit
        pos.position_total = c.total
        material += c.material
        labor += c.labor
        machine += c.machine
        direct += c.direct
        overhead += c.overhead
        profit += c.profit
    positions_sum = direct + overhead + profit
    subtotal = _round(positions_sum * Decimal(estimate.base_index or 1), rounding)
    vat_total = _round(_pct(subtotal, Decimal(estimate.vat_rate or 0)), rounding)
    estimate.material_total = _round(material, rounding)
    estimate.labor_total = _round(labor, rounding)
    estimate.machine_total = _round(machine, rounding)
    estimate.direct_total = _round(direct, rounding)
    estimate.overhead_total = _round(overhead, rounding)
    estimate.profit_total = _round(profit, rounding)
    estimate.subtotal = subtotal
    estimate.vat_total = vat_total
    estimate.grand_total = _round(subtotal + vat_total, rounding)
    return estimate


def validate_for_approval(
    session: Session, estimate: Estimate
) -> list[EstimatePosition]:
    """Проверяет смету перед утверждением. Бросает при пустой/некорректной."""
    positions = list(
        session.execute(
            select(EstimatePosition).where(
                EstimatePosition.estimate_id == estimate.id
            )
        ).scalars()
    )
    if not positions:
        raise EstimateValidationError("смета не содержит ни одной позиции")
    for p in positions:
        if Decimal(p.quantity or 0) <= 0:
            raise EstimateValidationError(f"позиция «{p.name}»: объём должен быть > 0")
        if p.unit_id is None:
            raise EstimateValidationError(
                f"позиция «{p.name}»: не указана единица измерения"
            )
    if Decimal(estimate.grand_total or 0) <= 0:
        raise EstimateValidationError("итоговая стоимость сметы должна быть > 0")
    return positions


def assert_editable(estimate: Estimate) -> None:
    """Запрещает прямое изменение утверждённой/устаревшей сметы."""
    if estimate.status in ("approved", "superseded"):
        raise EstimateStateError(
            "утверждённую смету нельзя менять напрямую — создайте новую версию "
            "или оформите change order"
        )


# ------------------------- Версии и изменения ---------------------------- #


def record_change(
    session: Session,
    estimate: Estimate,
    *,
    user: User,
    change_type: str,
    reason: str,
    amount_delta: Decimal = Decimal("0"),
    position_id: uuid.UUID | None = None,
    old_value: dict | None = None,
    new_value: dict | None = None,
    commit: bool = True,
) -> EstimateChange:
    """Фиксирует запись в журнале изменений сметы (причина обязательна)."""
    if not reason:
        raise EstimateStateError("не указана причина изменения")
    change = EstimateChange(
        estimate_id=estimate.id,
        position_id=position_id,
        change_type=change_type,
        reason=reason,
        amount_delta=amount_delta,
        old_value_json=old_value,
        new_value_json=new_value,
        changed_by=user.id,
    )
    session.add(change)
    record_event(
        session,
        actor_type="user",
        action="estimate.change.recorded",
        actor_user_id=user.id,
        organization_id=estimate.organization_id,
        entity_type="estimate",
        entity_id=estimate.id,
        new_values={"change_type": change_type, "reason": reason},
        commit=False,
    )
    if commit:
        session.commit()
    return change


def create_new_version(
    session: Session, estimate: Estimate, *, user: User, reason: str
) -> Estimate:
    """Создаёт новую версию сметы (копию) как черновик. Оригинал не меняется."""
    new = Estimate(
        organization_id=estimate.organization_id,
        project_id=estimate.project_id,
        site_id=estimate.site_id,
        contract_id=estimate.contract_id,
        discipline_id=estimate.discipline_id,
        design_brief_id=estimate.design_brief_id,
        estimate_type=estimate.estimate_type,
        parent_estimate_id=estimate.parent_estimate_id,
        number=estimate.number,
        name=estimate.name,
        version=estimate.version + 1,
        status="draft",
        currency=estimate.currency,
        base_index=estimate.base_index,
        vat_rate=estimate.vat_rate,
        overhead_percent=estimate.overhead_percent,
        profit_percent=estimate.profit_percent,
        rounding=estimate.rounding,
        created_by=user.id,
    )
    session.add(new)
    session.flush()
    for pos in session.execute(
        select(EstimatePosition).where(EstimatePosition.estimate_id == estimate.id)
    ).scalars():
        session.add(
            EstimatePosition(
                estimate_id=new.id,
                parent_position_id=None,
                rate_item_id=pos.rate_item_id,
                material_id=pos.material_id,
                design_specification_id=pos.design_specification_id,
                discipline_id=pos.discipline_id,
                location_id=pos.location_id,
                unit_id=pos.unit_id,
                code=pos.code,
                name=pos.name,
                work_type=pos.work_type,
                position_no=pos.position_no,
                quantity=pos.quantity,
                material_unit_cost=pos.material_unit_cost,
                labor_unit_cost=pos.labor_unit_cost,
                machine_unit_cost=pos.machine_unit_cost,
                coefficient=pos.coefficient,
                overhead_percent=pos.overhead_percent,
                profit_percent=pos.profit_percent,
            )
        )
    recalc_estimate(session, new)
    record_change(
        session, new, user=user, change_type="new_version",
        reason=reason, commit=False,
    )
    session.commit()
    return new


def approve_estimate(session: Session, estimate: Estimate, *, user: User) -> Estimate:
    """Утверждает смету (R2) после пересчёта и проверок; старую версию — superseded."""
    if estimate.status not in ("draft", "review"):
        raise EstimateStateError(
            f"нельзя утвердить смету из состояния '{estimate.status}'"
        )
    recalc_estimate(session, estimate)
    validate_for_approval(session, estimate)

    approval = Approval(
        organization_id=estimate.organization_id,
        entity_type="estimate",
        entity_id=estimate.id,
        approval_type="estimate_approval",
        requested_by_user_id=user.id,
        status="approved",
        current_step=1,
        completed_at=datetime.now(UTC),
    )
    session.add(approval)
    session.flush()
    session.add(
        ApprovalStep(
            approval_id=approval.id, step_number=1, approver_user_id=user.id,
            decision="approved", decided_at=datetime.now(UTC),
        )
    )
    # Пометить прежние утверждённые версии этой сметы как устаревшие.
    if estimate.number:
        for prev in session.execute(
            select(Estimate).where(
                Estimate.organization_id == estimate.organization_id,
                Estimate.project_id == estimate.project_id,
                Estimate.number == estimate.number,
                Estimate.status == "approved",
                Estimate.id != estimate.id,
            )
        ).scalars():
            prev.status = "superseded"
    estimate.status = "approved"
    estimate.approved_at = datetime.now(UTC)
    estimate.approved_by = user.id
    estimate.approval_id = approval.id
    record_event(
        session,
        actor_type="user",
        action="estimate.approved",
        actor_user_id=user.id,
        organization_id=estimate.organization_id,
        entity_type="estimate",
        entity_id=estimate.id,
        new_values={"grand_total": str(estimate.grand_total), "version": estimate.version},
        approval_id=approval.id,
        risk_level=APPROVAL_RISK,
        commit=False,
    )
    session.commit()
    return estimate


# --------------------- Коммерческое предложение (R3/R4) ------------------ #


def get_pricing_settings(
    session: Session, organization_id: uuid.UUID
) -> tuple[Decimal, int]:
    """Возвращает (порог суммы R4, порог числа позиций R4) для организации."""
    s = session.execute(
        select(PricingSettings).where(
            PricingSettings.organization_id == organization_id
        )
    ).scalars().first()
    if s is None:
        return DEFAULT_OFFER_R4_AMOUNT, DEFAULT_OFFER_R4_POSITIONS
    return Decimal(s.offer_r4_amount_threshold), int(s.offer_r4_positions_threshold)


def offer_risk_level(
    amount: Decimal, positions_count: int, *, amount_threshold: Decimal, positions_threshold: int
) -> str:
    """Уровень риска КП: R4 для крупной/массовой суммы, иначе R3."""
    if amount >= amount_threshold or positions_count >= positions_threshold:
        return "R4"
    return "R3"


def create_offer(
    session: Session,
    estimate: Estimate,
    *,
    user: User,
    markup_percent: Decimal,
) -> CommercialOffer:
    """Формирует коммерческое предложение из утверждённой сметы с наценкой."""
    if estimate.status != "approved":
        raise EstimateStateError("КП формируется только из утверждённой сметы")
    rounding = estimate.rounding or "0.01"
    base = Decimal(estimate.grand_total or 0)
    offer_amount = _round(base * (Decimal(1) + Decimal(markup_percent) / Decimal(100)), rounding)
    count = len(
        list(
            session.execute(
                select(EstimatePosition.id).where(
                    EstimatePosition.estimate_id == estimate.id
                )
            ).scalars()
        )
    )
    amount_thr, pos_thr = get_pricing_settings(session, estimate.organization_id)
    risk = offer_risk_level(
        offer_amount, count, amount_threshold=amount_thr, positions_threshold=pos_thr
    )
    offer = CommercialOffer(
        organization_id=estimate.organization_id,
        project_id=estimate.project_id,
        estimate_id=estimate.id,
        markup_percent=markup_percent,
        base_amount=base,
        offer_amount=offer_amount,
        currency=estimate.currency,
        status="draft",
        risk_level=risk,
        created_by=user.id,
    )
    session.add(offer)
    session.flush()
    record_event(
        session, actor_type="user", action="offer.created", actor_user_id=user.id,
        organization_id=estimate.organization_id, entity_type="commercial_offer",
        entity_id=offer.id, new_values={"offer_amount": str(offer_amount), "risk_level": risk},
        risk_level=risk, commit=False,
    )
    session.commit()
    return offer


def request_offer_approval(
    session: Session, offer: CommercialOffer, *, user: User
) -> Approval:
    """Запрашивает согласование КП (R3/R4)."""
    if offer.status not in ("draft",):
        raise EstimateStateError(f"нельзя запросить согласование из '{offer.status}'")
    approval = Approval(
        organization_id=offer.organization_id,
        entity_type="commercial_offer",
        entity_id=offer.id,
        approval_type="commercial_offer",
        requested_by_user_id=user.id,
        status="pending",
        current_step=1,
    )
    session.add(approval)
    session.flush()
    offer.approval_id = approval.id
    offer.status = "pending_approval"
    record_event(
        session, actor_type="user", action="offer.approval_requested",
        actor_user_id=user.id, organization_id=offer.organization_id,
        entity_type="commercial_offer", entity_id=offer.id,
        approval_id=approval.id, risk_level=offer.risk_level, commit=False,
    )
    session.commit()
    return approval


def decide_offer(
    session: Session,
    offer: CommercialOffer,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
    mfa_verified: bool = False,
) -> CommercialOffer:
    """Фиксирует решение по КП. Уровень R4 требует MFA (D-002)."""
    if decision not in ("approved", "rejected"):
        raise EstimateStateError(f"неизвестное решение '{decision}'")
    if offer.approval_id is None or offer.status != "pending_approval":
        raise EstimateStateError("нет активного запроса на согласование КП")
    if decision == "approved" and offer.risk_level == "R4" and not mfa_verified:
        raise OfferAuthorizationError(
            "предложение уровня R4 требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, offer.approval_id)
    session.add(
        ApprovalStep(
            approval_id=approval.id, step_number=approval.current_step,
            approver_user_id=user.id, decision=decision, comment=comment,
            decided_at=datetime.now(UTC),
        )
    )
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    offer.status = "approved" if decision == "approved" else "rejected"
    record_event(
        session, actor_type="user", action=f"offer.{decision}",
        actor_user_id=user.id, organization_id=offer.organization_id,
        entity_type="commercial_offer", entity_id=offer.id, approval_id=approval.id,
        reason=comment, risk_level=offer.risk_level, commit=False,
    )
    session.commit()
    return offer


# ------------------------------ План-факт -------------------------------- #


@dataclass
class PlanFactRow:
    position_id: uuid.UUID
    name: str
    planned_quantity: Decimal
    actual_quantity: Decimal
    planned_total: Decimal
    actual_total: Decimal
    deviation: Decimal


def plan_fact(session: Session, estimate: Estimate) -> list[PlanFactRow]:
    """План-факт по позициям: план из сметы, факт из daily_report_work_items."""
    rounding = estimate.rounding or "0.01"
    rows: list[PlanFactRow] = []
    for pos in session.execute(
        select(EstimatePosition).where(EstimatePosition.estimate_id == estimate.id)
    ).scalars():
        actual_qty = Decimal("0")
        for wi in session.execute(
            select(DailyReportWorkItem).where(
                DailyReportWorkItem.estimate_position_id == pos.id,
                DailyReportWorkItem.verification_status != "rejected",
            )
        ).scalars():
            actual_qty += Decimal(wi.actual_quantity or 0)
        planned_qty = Decimal(pos.quantity or 0)
        unit_total = (
            (Decimal(pos.position_total or 0) / planned_qty)
            if planned_qty > 0
            else Decimal("0")
        )
        actual_total = _round(unit_total * actual_qty, rounding)
        rows.append(
            PlanFactRow(
                position_id=pos.id,
                name=pos.name,
                planned_quantity=planned_qty,
                actual_quantity=actual_qty,
                planned_total=Decimal(pos.position_total or 0),
                actual_total=actual_total,
                deviation=_round(actual_total - Decimal(pos.position_total or 0), rounding),
            )
        )
    return rows


def can_access_estimate_project(
    session: Session, user: User, project_id: uuid.UUID
) -> bool:
    return can_access_project(session, user, project_id)
