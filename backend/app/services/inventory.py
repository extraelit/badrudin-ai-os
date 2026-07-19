"""Бизнес-логика модуля «Складской учёт и остатки».

Складской учёт (DATABASE.md раздел 33.4): достоверные остатки по складам,
журнал движений (проводок), резервы, места хранения, точка дозаказа и сигналы о
низком/отрицательном остатке. Модуль ЧИТАЕТ и агрегирует уже существующие
сущности (`inventory_balances`, `inventory_transactions`, `stock_reservations`,
`warehouses`, `warehouse_locations`, `materials`) без дублирования и управляет
ручными резервами и неснижаемым остатком.

Проводки склада (приход/расход) выполняются общей идемпотентной функцией
`app.services.procurement.post_transaction` — сквозной цикл (поступление →
остаток → резерв → выдача → возврат → списание → инвентаризация) остаётся единым.
Все значимые действия — в `audit_events`; изоляция по проекту (ABAC) — через склад.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    InventoryBalance,
    InventoryTransaction,
    Material,
    StockReservation,
    User,
    Warehouse,
    WarehouseLocation,
)
from app.services.access import can_access_project
from app.services.audit import record_event

QTY = Decimal("0.001")


class InventoryError(RuntimeError):
    """Нарушение правил складского учёта (например, резерв больше свободного остатка)."""


def _q(v: Decimal | float | str) -> Decimal:
    return Decimal(str(v)).quantize(QTY, rounding=ROUND_HALF_UP)


# ------------------------------ Доступ (ABAC) ---------------------------- #


def warehouse_in_org(session: Session, warehouse_id: uuid.UUID, organization_id: uuid.UUID) -> Warehouse:
    wh = session.get(Warehouse, warehouse_id)
    if wh is None or wh.deleted_at is not None or wh.organization_id != organization_id:
        raise InventoryError("склад не найден")
    return wh


def can_access_warehouse(session: Session, user: User, warehouse: Warehouse) -> bool:
    """ABAC: склад привязан к объекту → проверяем доступ к проекту объекта.

    Склад без объекта считается общеорганизационным (доступ в пределах организации).
    """
    if warehouse.site_id is None:
        return True
    from app.models import Site

    site = session.get(Site, warehouse.site_id)
    if site is None:
        return True
    return can_access_project(session, user, site.project_id)


# ------------------------------- Остатки --------------------------------- #


def list_stock(
    session: Session, organization_id: uuid.UUID, *,
    warehouse_id: uuid.UUID | None = None, material_id: uuid.UUID | None = None,
    low_only: bool = False,
) -> list[InventoryBalance]:
    stmt = select(InventoryBalance).where(InventoryBalance.organization_id == organization_id)
    if warehouse_id is not None:
        stmt = stmt.where(InventoryBalance.warehouse_id == warehouse_id)
    if material_id is not None:
        stmt = stmt.where(InventoryBalance.material_id == material_id)
    rows = list(session.execute(stmt).scalars())
    if low_only:
        rows = [b for b in rows if _is_low(b)]
    return rows


def _is_low(b: InventoryBalance) -> bool:
    avail = Decimal(b.quantity) - Decimal(b.reserved_quantity)
    return Decimal(b.minimum_quantity) > 0 and avail <= Decimal(b.minimum_quantity)


def available_quantity(b: InventoryBalance) -> Decimal:
    return _q(Decimal(b.quantity) - Decimal(b.reserved_quantity))


def stock_summary(session: Session, organization_id: uuid.UUID) -> dict:
    rows = list(
        session.execute(
            select(InventoryBalance).where(InventoryBalance.organization_id == organization_id)
        ).scalars()
    )
    total_value = Decimal("0")
    reserved_positions = 0
    low = 0
    negative = 0
    for b in rows:
        total_value += Decimal(b.quantity) * Decimal(b.average_unit_cost)
        if Decimal(b.reserved_quantity) > 0:
            reserved_positions += 1
        if _is_low(b):
            low += 1
        if Decimal(b.quantity) < 0:
            negative += 1
    return {
        "positions": len(rows),
        "warehouses_with_stock": len({b.warehouse_id for b in rows}),
        "total_value": total_value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        "reserved_positions": reserved_positions,
        "low_stock": low,
        "negative_stock": negative,
    }


def set_minimum_quantity(
    session: Session, *, organization_id: uuid.UUID, warehouse_id: uuid.UUID,
    material_id: uuid.UUID, minimum_quantity: Decimal, user: User,
) -> InventoryBalance:
    bal = session.execute(
        select(InventoryBalance).where(
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.material_id == material_id,
            InventoryBalance.location_id.is_(None),
        )
    ).scalars().first()
    if bal is None:
        bal = InventoryBalance(
            organization_id=organization_id, warehouse_id=warehouse_id,
            material_id=material_id, quantity=Decimal("0"),
            reserved_quantity=Decimal("0"), average_unit_cost=Decimal("0"),
        )
        session.add(bal)
    bal.minimum_quantity = _q(minimum_quantity)
    _audit(session, user, "inventory.min_quantity.set", organization_id,
           "inventory_balance", bal.id, {"minimum_quantity": str(bal.minimum_quantity)})
    session.commit()
    return bal


# ------------------------------ Журнал (ledger) -------------------------- #


def list_ledger(
    session: Session, organization_id: uuid.UUID, *,
    warehouse_id: uuid.UUID | None = None, material_id: uuid.UUID | None = None,
    limit: int = 100,
) -> list[InventoryTransaction]:
    stmt = select(InventoryTransaction).where(
        InventoryTransaction.organization_id == organization_id
    )
    if warehouse_id is not None:
        stmt = stmt.where(InventoryTransaction.warehouse_id == warehouse_id)
    if material_id is not None:
        stmt = stmt.where(InventoryTransaction.material_id == material_id)
    stmt = stmt.order_by(InventoryTransaction.created_at.desc()).limit(min(limit, 500))
    return list(session.execute(stmt).scalars())


def stock_card(
    session: Session, organization_id: uuid.UUID, *,
    warehouse_id: uuid.UUID, material_id: uuid.UUID,
) -> dict:
    bal = session.execute(
        select(InventoryBalance).where(
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.material_id == material_id,
        )
    ).scalars().first()
    txs = list_ledger(session, organization_id, warehouse_id=warehouse_id,
                      material_id=material_id, limit=200)
    return {"balance": bal, "transactions": txs}


# ------------------------------ Резервы ---------------------------------- #


def _get_or_create_balance(
    session: Session, *, organization_id: uuid.UUID, warehouse_id: uuid.UUID,
    material_id: uuid.UUID,
) -> InventoryBalance:
    bal = session.execute(
        select(InventoryBalance).where(
            InventoryBalance.warehouse_id == warehouse_id,
            InventoryBalance.material_id == material_id,
            InventoryBalance.location_id.is_(None),
        )
    ).scalars().first()
    if bal is None:
        bal = InventoryBalance(
            organization_id=organization_id, warehouse_id=warehouse_id,
            material_id=material_id, quantity=Decimal("0"),
            reserved_quantity=Decimal("0"), average_unit_cost=Decimal("0"),
        )
        session.add(bal)
        session.flush()
    return bal


def list_reservations(
    session: Session, organization_id: uuid.UUID, *,
    warehouse_id: uuid.UUID | None = None, status: str | None = None,
) -> list[StockReservation]:
    stmt = select(StockReservation).where(
        StockReservation.organization_id == organization_id
    )
    if warehouse_id is not None:
        stmt = stmt.where(StockReservation.warehouse_id == warehouse_id)
    if status is not None:
        stmt = stmt.where(StockReservation.status == status)
    return list(session.execute(stmt.order_by(StockReservation.created_at.desc())).scalars())


def create_reservation(
    session: Session, *, organization_id: uuid.UUID, warehouse_id: uuid.UUID,
    material_id: uuid.UUID, quantity: Decimal, user: User,
    reserved_until: date | None = None, reason: str | None = None,
) -> StockReservation:
    """Ручное резервирование свободного остатка (не под заказ/заявку)."""
    qty = _q(quantity)
    if qty <= 0:
        raise InventoryError("количество резерва должно быть больше нуля")
    bal = _get_or_create_balance(
        session, organization_id=organization_id, warehouse_id=warehouse_id,
        material_id=material_id,
    )
    available = available_quantity(bal)
    if qty > available:
        raise InventoryError(
            f"недостаточно свободного остатка: доступно {available}, требуется {qty}"
        )
    bal.reserved_quantity = _q(Decimal(bal.reserved_quantity) + qty)
    res = StockReservation(
        organization_id=organization_id, warehouse_id=warehouse_id,
        material_id=material_id, quantity=qty, status="active",
        reserved_by_user_id=user.id, reserved_until=reserved_until, reason=reason,
    )
    session.add(res)
    _audit(session, user, "inventory.reservation.created", organization_id,
           "stock_reservation", None, {"material_id": str(material_id), "quantity": str(qty)})
    session.commit()
    return res


def release_reservation(
    session: Session, reservation: StockReservation, *, user: User,
) -> StockReservation:
    """Снятие активного резерва: возвращает свободный остаток."""
    if reservation.status != "active":
        raise InventoryError("снять можно только активный резерв")
    bal = session.execute(
        select(InventoryBalance).where(
            InventoryBalance.warehouse_id == reservation.warehouse_id,
            InventoryBalance.material_id == reservation.material_id,
            InventoryBalance.location_id.is_(None),
        )
    ).scalars().first()
    if bal is not None:
        bal.reserved_quantity = _q(
            max(Decimal("0"), Decimal(bal.reserved_quantity) - Decimal(reservation.quantity))
        )
    reservation.status = "released"
    reservation.released_at = datetime.now(UTC)
    _audit(session, user, "inventory.reservation.released", reservation.organization_id,
           "stock_reservation", reservation.id, {"quantity": str(reservation.quantity)})
    session.commit()
    return reservation


# --------------------------- Места хранения ------------------------------ #


def list_locations(session: Session, warehouse_id: uuid.UUID) -> list[WarehouseLocation]:
    return list(
        session.execute(
            select(WarehouseLocation).where(WarehouseLocation.warehouse_id == warehouse_id)
        ).scalars()
    )


def create_location(
    session: Session, *, warehouse_id: uuid.UUID, name: str,
    code: str | None, parent_location_id: uuid.UUID | None, user: User,
    organization_id: uuid.UUID,
) -> WarehouseLocation:
    loc = WarehouseLocation(
        warehouse_id=warehouse_id, name=name, code=code,
        parent_location_id=parent_location_id, created_by=user.id,
    )
    session.add(loc)
    session.flush()
    _audit(session, user, "inventory.location.created", organization_id,
           "warehouse_location", loc.id, {"name": name})
    session.commit()
    return loc


# ------------------------------ Помощники -------------------------------- #


def material_names(session: Session, ids: set[uuid.UUID]) -> dict[uuid.UUID, str]:
    if not ids:
        return {}
    rows = session.execute(select(Material.id, Material.name).where(Material.id.in_(ids))).all()
    return {r[0]: r[1] for r in rows}


def _audit(session, user, action, org_id, entity_type, entity_id, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        new_values=new_values, risk_level="R1", commit=False,
    )
