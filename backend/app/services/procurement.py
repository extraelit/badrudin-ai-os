"""Бизнес-логика модуля «Снабжение и закупки».

Правила (DATABASE.md раздел 33, D-001/D-002):
- все складские проводки идемпотентны (запрет двойного проведения) и меняют
  остатки транзакционно; количества — Decimal;
- приёмка не больше заказа; выдача/списание/перемещение не больше остатка;
- согласование через общий контур `approvals` (R0–R4): заявка — R2, заказ — R3
  (крупный — R4), списание — R3 (крупное/массовое — R4); пороги и требование MFA
  настраиваются для организации (`procurement_settings`);
- резервирование остатка при подтверждённом заказе;
- все значимые действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    GoodsReceipt,
    GoodsReceiptLine,
    InventoryBalance,
    InventoryCount,
    InventoryCountLine,
    InventoryTransaction,
    MaterialIssue,
    MaterialIssueLine,
    MaterialRequest,
    ProcurementSettings,
    PurchaseOrder,
    PurchaseOrderLine,
    StockReservation,
    StockTransfer,
    WriteOffDocument,
)
from app.services.access import can_access_project
from app.services.audit import record_event

DEFAULT_R4_AMOUNT = Decimal("1000000.00")
DEFAULT_MASS_LINES = 50
QTY = Decimal("0.001")
MONEY = Decimal("0.01")


class ProcurementError(RuntimeError):
    """Нарушение правил снабжения/склада (недостаточно остатка, превышение и т. п.)."""


class ProcurementAuthorizationError(RuntimeError):
    """Недостаточно условий для действия (например, нет MFA для R4)."""


def _q(v: Decimal | float | str) -> Decimal:
    return Decimal(str(v)).quantize(QTY, rounding=ROUND_HALF_UP)


def _m(v: Decimal | float | str) -> Decimal:
    return Decimal(str(v)).quantize(MONEY, rounding=ROUND_HALF_UP)


# ----------------------------- Настройки --------------------------------- #


def get_settings(
    session: Session, organization_id: uuid.UUID
) -> tuple[Decimal, int, bool]:
    """Возвращает (порог суммы R4, порог числа строк R4, требуется ли MFA)."""
    s = session.execute(
        select(ProcurementSettings).where(
            ProcurementSettings.organization_id == organization_id
        )
    ).scalars().first()
    if s is None:
        return DEFAULT_R4_AMOUNT, DEFAULT_MASS_LINES, True
    return (
        Decimal(s.order_r4_amount_threshold),
        int(s.mass_writeoff_lines_threshold),
        bool(s.require_mfa_r4),
    )


def order_risk_level(amount: Decimal, *, amount_threshold: Decimal) -> str:
    """Заказ: R4 для крупной суммы, иначе R3."""
    return "R4" if amount >= amount_threshold else "R3"


# --------------------------- Проводки склада ----------------------------- #


def _get_or_create_balance(
    session: Session,
    *,
    organization_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    material_id: uuid.UUID,
    location_id: uuid.UUID | None = None,
) -> InventoryBalance:
    bal = session.execute(
        select(InventoryBalance).where(
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.material_id == material_id,
            InventoryBalance.location_id.is_(location_id)
            if location_id is None
            else InventoryBalance.location_id == location_id,
        )
    ).scalars().first()
    if bal is None:
        bal = InventoryBalance(
            organization_id=organization_id,
            warehouse_id=warehouse_id,
            material_id=material_id,
            location_id=location_id,
            quantity=Decimal("0"),
            reserved_quantity=Decimal("0"),
            average_unit_cost=Decimal("0"),
        )
        session.add(bal)
        session.flush()
    return bal


def post_transaction(
    session: Session,
    *,
    organization_id: uuid.UUID,
    warehouse_id: uuid.UUID,
    material_id: uuid.UUID,
    quantity_signed: Decimal,
    transaction_type: str,
    unit_cost: Decimal = Decimal("0"),
    source_type: str | None = None,
    source_id: uuid.UUID | None = None,
    idempotency_key: str | None = None,
    location_id: uuid.UUID | None = None,
    allow_negative: bool = False,
) -> InventoryTransaction | None:
    """Проводит движение и обновляет остаток. Идемпотентно по ключу.

    Возвращает None, если проводка с этим ключом уже выполнена (двойное
    проведение предотвращено).
    """
    if idempotency_key is not None:
        existing = session.execute(
            select(InventoryTransaction).where(
                InventoryTransaction.idempotency_key == idempotency_key
            )
        ).scalars().first()
        if existing is not None:
            return None

    qty = _q(quantity_signed)
    bal = _get_or_create_balance(
        session, organization_id=organization_id, warehouse_id=warehouse_id,
        material_id=material_id, location_id=location_id,
    )
    new_qty = _q(Decimal(bal.quantity) + qty)
    if new_qty < 0 and not allow_negative:
        raise ProcurementError(
            f"недостаточно остатка: доступно {bal.quantity}, требуется {-qty}"
        )
    # средневзвешенная себестоимость при приходе
    if qty > 0 and unit_cost and Decimal(bal.quantity) + qty > 0:
        total_cost = Decimal(bal.quantity) * Decimal(bal.average_unit_cost) + qty * Decimal(unit_cost)
        bal.average_unit_cost = _m(total_cost / (Decimal(bal.quantity) + qty))
    bal.quantity = new_qty

    tx = InventoryTransaction(
        organization_id=organization_id, warehouse_id=warehouse_id,
        material_id=material_id, location_id=location_id,
        transaction_type=transaction_type, quantity=qty, unit_cost=_m(unit_cost),
        source_type=source_type, source_id=source_id,
        idempotency_key=idempotency_key, occurred_at=datetime.now(UTC),
    )
    session.add(tx)
    try:
        session.flush()
    except IntegrityError:
        # гонка по идемпотентному ключу — проводка уже выполнена
        session.rollback()
        return None
    return tx


# ----------------------------- Заявки (R2) ------------------------------- #


def approve_request(
    session: Session, request: MaterialRequest, *, user: User
) -> MaterialRequest:  # noqa: F821 (User импортируется ниже для типизации)
    if request.status not in ("draft", "submitted"):
        raise ProcurementError(f"нельзя утвердить заявку из '{request.status}'")
    approval = _approval(session, request.organization_id, "material_request", request.id, "material_request_approval", user, decided="approved")
    request.status = "approved"
    request.approval_id = approval.id
    _audit(session, user, "procurement.request.approved", request.organization_id,
           "material_request", request.id, {"number": request.number}, approval.id, "R2")
    session.commit()
    return request


# ------------------------------ Заказы ----------------------------------- #


def recalc_order_total(session: Session, order: PurchaseOrder) -> PurchaseOrder:
    lines = list(
        session.execute(
            select(PurchaseOrderLine).where(
                PurchaseOrderLine.purchase_order_id == order.id
            )
        ).scalars()
    )
    total = Decimal("0")
    for ln in lines:
        ln.amount = _m(Decimal(ln.quantity) * Decimal(ln.unit_price))
        total += ln.amount
    order.total_amount = _m(total)
    return order


def request_order_approval(
    session: Session, order: PurchaseOrder, *, user: User  # noqa: F821
) -> Approval:
    if order.status not in ("draft",):
        raise ProcurementError(f"нельзя согласовать заказ из '{order.status}'")
    recalc_order_total(session, order)
    if order.total_amount <= 0:
        raise ProcurementError("заказ пуст или сумма равна нулю")
    amount_thr, _lines, _mfa = get_settings(session, order.organization_id)
    order.risk_level = order_risk_level(order.total_amount, amount_threshold=amount_thr)
    approval = _approval(session, order.organization_id, "purchase_order", order.id,
                         "purchase_order_approval", user, decided=None)
    order.approval_id = approval.id
    order.status = "pending_approval"
    _audit(session, user, "procurement.order.approval_requested", order.organization_id,
           "purchase_order", order.id, {"total": str(order.total_amount), "risk": order.risk_level},
           approval.id, order.risk_level)
    session.commit()
    return approval


def decide_order(
    session: Session, order: PurchaseOrder, *, user: User, decision: str,  # noqa: F821
    comment: str | None = None, mfa_verified: bool = False,
) -> PurchaseOrder:
    if decision not in ("approved", "rejected"):
        raise ProcurementError(f"неизвестное решение '{decision}'")
    if order.approval_id is None or order.status != "pending_approval":
        raise ProcurementError("нет активного запроса на согласование заказа")
    if decision == "approved" and order.risk_level == "R4" and not mfa_verified:
        raise ProcurementAuthorizationError(
            "заказ уровня R4 требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, order.approval_id)
    _decide(session, approval, user, decision, comment)
    if decision == "approved":
        order.status = "approved"
        _reserve_order(session, order)
    else:
        order.status = "cancelled"
    _audit(session, user, f"procurement.order.{decision}", order.organization_id,
           "purchase_order", order.id, {"decision": decision}, approval.id, order.risk_level)
    session.commit()
    return order


def _reserve_order(session: Session, order: PurchaseOrder) -> None:
    """Резервирует остаток под подтверждённый заказ (минимальное резервирование)."""
    if order.warehouse_id is None:
        return
    for ln in session.execute(
        select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order.id)
    ).scalars():
        if ln.material_id is None:
            continue
        session.add(
            StockReservation(
                organization_id=order.organization_id, warehouse_id=order.warehouse_id,
                material_id=ln.material_id, purchase_order_id=order.id,
                quantity=ln.quantity, status="active",
            )
        )


# ----------------- Поступление и входной контроль ------------------------ #


def post_goods_receipt(
    session: Session, receipt: GoodsReceipt, *, user: User  # noqa: F821
) -> GoodsReceipt:
    """Проводит поступление: приёмка ≤ заказа, оприходование принятого количества."""
    if receipt.status == "posted":
        raise ProcurementError("поступление уже проведено")
    lines = list(
        session.execute(
            select(GoodsReceiptLine).where(
                GoodsReceiptLine.goods_receipt_id == receipt.id
            )
        ).scalars()
    )
    if not lines:
        raise ProcurementError("поступление без позиций")
    for ln in lines:
        accepted = _q(ln.quantity_accepted)
        if accepted <= 0:
            continue
        # проверка: приёмка не больше заказа
        if ln.purchase_order_line_id is not None:
            pol = session.get(PurchaseOrderLine, ln.purchase_order_line_id)
            if pol is not None:
                remaining = _q(Decimal(pol.quantity) - Decimal(pol.received_quantity))
                if accepted > remaining:
                    raise ProcurementError(
                        f"приёмка ({accepted}) превышает остаток заказа ({remaining})"
                    )
                pol.received_quantity = _q(Decimal(pol.received_quantity) + accepted)
        post_transaction(
            session, organization_id=receipt.organization_id,
            warehouse_id=receipt.warehouse_id, material_id=ln.material_id,
            quantity_signed=accepted, transaction_type="receipt",
            source_type="goods_receipt", source_id=receipt.id,
            idempotency_key=f"receipt:{receipt.id}:{ln.id}",
        )
    receipt.status = "posted"
    # обновление статуса заказа и снятие резерва
    if receipt.purchase_order_id is not None:
        _update_order_progress(session, receipt.purchase_order_id)
    _audit(session, user, "procurement.receipt.posted", receipt.organization_id,
           "goods_receipt", receipt.id, {"number": receipt.number}, None, "R1")
    session.commit()
    return receipt


def _update_order_progress(session: Session, order_id: uuid.UUID) -> None:
    order = session.get(PurchaseOrder, order_id)
    if order is None:
        return
    lines = list(
        session.execute(
            select(PurchaseOrderLine).where(PurchaseOrderLine.purchase_order_id == order_id)
        ).scalars()
    )
    fully = all(Decimal(l.received_quantity) >= Decimal(l.quantity) for l in lines)
    some = any(Decimal(l.received_quantity) > 0 for l in lines)
    order.status = "received" if fully else ("partially_received" if some else order.status)
    if fully:
        for res in session.execute(
            select(StockReservation).where(
                StockReservation.purchase_order_id == order_id,
                StockReservation.status == "active",
            )
        ).scalars():
            res.status = "consumed"


# ------------------------------ Выдача ----------------------------------- #


def post_material_issue(
    session: Session, issue: MaterialIssue, *, user: User  # noqa: F821
) -> MaterialIssue:
    if issue.status == "posted":
        raise ProcurementError("выдача уже проведена")
    lines = list(
        session.execute(
            select(MaterialIssueLine).where(
                MaterialIssueLine.material_issue_id == issue.id
            )
        ).scalars()
    )
    if not lines:
        raise ProcurementError("выдача без позиций")
    for ln in lines:
        post_transaction(
            session, organization_id=issue.organization_id,
            warehouse_id=issue.warehouse_id, material_id=ln.material_id,
            quantity_signed=-_q(ln.quantity), transaction_type="issue",
            source_type="material_issue", source_id=issue.id,
            idempotency_key=f"issue:{issue.id}:{ln.id}",
        )
    issue.status = "posted"
    _audit(session, user, "procurement.issue.posted", issue.organization_id,
           "material_issue", issue.id, {"number": issue.number}, None, "R1")
    session.commit()
    return issue


# ------------------- Перемещение, возврат, списание ---------------------- #


def post_transfer(
    session: Session, transfer: StockTransfer, *, user: User  # noqa: F821
) -> StockTransfer:
    if transfer.status == "posted":
        raise ProcurementError("перемещение уже проведено")
    qty = _q(transfer.quantity)
    post_transaction(
        session, organization_id=transfer.organization_id,
        warehouse_id=transfer.from_warehouse_id, material_id=transfer.material_id,
        quantity_signed=-qty, transaction_type="transfer_out",
        source_type="stock_transfer", source_id=transfer.id,
        idempotency_key=f"transfer_out:{transfer.id}",
    )
    post_transaction(
        session, organization_id=transfer.organization_id,
        warehouse_id=transfer.to_warehouse_id, material_id=transfer.material_id,
        quantity_signed=qty, transaction_type="transfer_in",
        source_type="stock_transfer", source_id=transfer.id,
        idempotency_key=f"transfer_in:{transfer.id}",
    )
    transfer.status = "posted"
    _audit(session, user, "procurement.transfer.posted", transfer.organization_id,
           "stock_transfer", transfer.id, {"number": transfer.number}, None, "R2")
    session.commit()
    return transfer


def post_return(
    session: Session, ret: MaterialReturn, *, user: User  # noqa: F821
) -> MaterialReturn:  # noqa: F821
    if ret.status == "posted":
        raise ProcurementError("возврат уже проведён")
    qty = _q(ret.quantity)
    signed = qty if ret.return_type == "from_site" else -qty
    post_transaction(
        session, organization_id=ret.organization_id, warehouse_id=ret.warehouse_id,
        material_id=ret.material_id, quantity_signed=signed, transaction_type="return",
        source_type="material_return", source_id=ret.id,
        idempotency_key=f"return:{ret.id}",
    )
    ret.status = "posted"
    _audit(session, user, "procurement.return.posted", ret.organization_id,
           "material_return", ret.id, {"number": ret.number}, None, "R2")
    session.commit()
    return ret


def request_writeoff_approval(
    session: Session, wo: WriteOffDocument, *, user: User  # noqa: F821
) -> Approval:
    if wo.status not in ("draft",):
        raise ProcurementError(f"нельзя согласовать списание из '{wo.status}'")
    amount_thr, mass_lines, _mfa = get_settings(session, wo.organization_id)
    # для одиночного списания риск по количеству*себестоимости не считаем — R3;
    # крупное/массовое (по политике) — R4
    bal = session.execute(
        select(InventoryBalance).where(
            InventoryBalance.warehouse_id == wo.warehouse_id,
            InventoryBalance.material_id == wo.material_id,
        )
    ).scalars().first()
    cost = Decimal(bal.average_unit_cost) if bal else Decimal("0")
    amount = _m(Decimal(wo.quantity) * cost)
    wo.risk_level = "R4" if amount >= amount_thr else "R3"
    approval = _approval(session, wo.organization_id, "write_off_document", wo.id,
                         "write_off_approval", user, decided=None)
    wo.approval_id = approval.id
    wo.status = "pending_approval"
    _audit(session, user, "procurement.writeoff.approval_requested", wo.organization_id,
           "write_off_document", wo.id, {"amount": str(amount), "risk": wo.risk_level},
           approval.id, wo.risk_level)
    session.commit()
    return approval


def decide_writeoff(
    session: Session, wo: WriteOffDocument, *, user: User, decision: str,  # noqa: F821
    comment: str | None = None, mfa_verified: bool = False,
) -> WriteOffDocument:
    if decision not in ("approved", "rejected"):
        raise ProcurementError(f"неизвестное решение '{decision}'")
    if wo.approval_id is None or wo.status != "pending_approval":
        raise ProcurementError("нет активного запроса на согласование списания")
    if decision == "approved" and wo.risk_level == "R4" and not mfa_verified:
        raise ProcurementAuthorizationError(
            "списание уровня R4 требует подтверждения усиленной аутентификацией"
        )
    approval = session.get(Approval, wo.approval_id)
    _decide(session, approval, user, decision, comment)
    if decision == "approved":
        post_transaction(
            session, organization_id=wo.organization_id, warehouse_id=wo.warehouse_id,
            material_id=wo.material_id, quantity_signed=-_q(wo.quantity),
            transaction_type="write_off", source_type="write_off_document",
            source_id=wo.id, idempotency_key=f"writeoff:{wo.id}",
        )
        wo.status = "posted"
    else:
        wo.status = "rejected"
    _audit(session, user, f"procurement.writeoff.{decision}", wo.organization_id,
           "write_off_document", wo.id, {"decision": decision}, approval.id, wo.risk_level)
    session.commit()
    return wo


# ---------------------------- Инвентаризация ----------------------------- #


def apply_inventory_count(
    session: Session, count: InventoryCount, *, user: User  # noqa: F821
) -> InventoryCount:
    """Проводит инвентаризацию: расхождения корректируют остаток (adjustment)."""
    if count.status == "posted":
        raise ProcurementError("инвентаризация уже проведена")
    for ln in session.execute(
        select(InventoryCountLine).where(
            InventoryCountLine.inventory_count_id == count.id
        )
    ).scalars():
        diff = _q(Decimal(ln.counted_quantity) - Decimal(ln.expected_quantity))
        ln.difference_quantity = diff
        if diff != 0:
            post_transaction(
                session, organization_id=count.organization_id,
                warehouse_id=count.warehouse_id, material_id=ln.material_id,
                quantity_signed=diff, transaction_type="adjustment",
                source_type="inventory_count", source_id=count.id,
                idempotency_key=f"count:{count.id}:{ln.id}", allow_negative=True,
            )
    count.status = "posted"
    _audit(session, user, "procurement.inventory.posted", count.organization_id,
           "inventory_count", count.id, {"number": count.number}, None, "R2")
    session.commit()
    return count


# ------------------------------ Помощники -------------------------------- #


def _approval(session, org_id, entity_type, entity_id, approval_type, user, *, decided):
    approval = Approval(
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        approval_type=approval_type, requested_by_user_id=user.id,
        status=decided or "pending", current_step=1,
        completed_at=datetime.now(UTC) if decided else None,
    )
    session.add(approval)
    session.flush()
    if decided:
        session.add(
            ApprovalStep(approval_id=approval.id, step_number=1,
                         approver_user_id=user.id, decision=decided,
                         decided_at=datetime.now(UTC))
        )
    return approval


def _decide(session, approval, user, decision, comment):
    session.add(
        ApprovalStep(approval_id=approval.id, step_number=approval.current_step,
                     approver_user_id=user.id, decision=decision, comment=comment,
                     decided_at=datetime.now(UTC))
    )
    approval.status = decision
    approval.completed_at = datetime.now(UTC)


def _audit(session, user, action, org_id, entity_type, entity_id, new_values, approval_id, risk):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        new_values=new_values, approval_id=approval_id, risk_level=risk, commit=False,
    )


def can_access(session, user, project_id: uuid.UUID | None) -> bool:
    if project_id is None:
        return True
    return can_access_project(session, user, project_id)


# импорт User в конце во избежание циклических ссылок при аннотациях
from app.models import User  # noqa: E402
