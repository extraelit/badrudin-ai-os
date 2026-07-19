"""API модуля «Складской учёт и остатки».

Backend — единственная точка доступа к данным. Чтение остатков, журнала движений,
складской карточки, резервов и мест хранения; управление ручными резервами,
точкой дозаказа и местами хранения. RBAC: `warehouse.view` (чтение),
`warehouse.manage` (изменение). ABAC: доступ к складу — через объект/проект.
Все значимые действия — в `audit_events`. Складские проводки (приход/расход)
выполняются модулем снабжения (общий идемпотентный контур), здесь не дублируются.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import Employee, StockReservation, User
from app.schemas.inventory import (
    LedgerRow,
    LocationIn,
    LocationOut,
    MinQuantityIn,
    ReservationIn,
    ReservationOut,
    StockCardOut,
    StockRow,
    StockSummaryOut,
)
from app.services import inventory as svc

router = APIRouter(prefix="/warehouse", tags=["warehouse"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _require_warehouse(db: Session, user: User, warehouse_id: uuid.UUID):
    try:
        wh = svc.warehouse_in_org(db, warehouse_id, _org(db, user))
    except svc.InventoryError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if not svc.can_access_warehouse(db, user, wh):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к складу")
    return wh


def _stock_row(b, names: dict) -> StockRow:
    return StockRow(
        warehouse_id=b.warehouse_id, material_id=b.material_id,
        material_name=names.get(b.material_id), location_id=b.location_id,
        quantity=str(b.quantity), reserved_quantity=str(b.reserved_quantity),
        available_quantity=str(svc.available_quantity(b)),
        minimum_quantity=str(b.minimum_quantity),
        average_unit_cost=str(b.average_unit_cost), currency=b.currency,
        low=svc._is_low(b),
    )


# ------------------------------- Сводка ---------------------------------- #


@router.get("/summary", response_model=StockSummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.view")),
) -> StockSummaryOut:
    return StockSummaryOut(**{
        k: (str(v) if k == "total_value" else v)
        for k, v in svc.stock_summary(db, _org(db, user)).items()
    })


# ------------------------------- Остатки --------------------------------- #


@router.get("/stock", response_model=list[StockRow])
def list_stock(
    warehouse_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    low_only: bool = False,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.view")),
) -> list[StockRow]:
    org = _org(db, user)
    if warehouse_id is not None:
        _require_warehouse(db, user, warehouse_id)
    rows = svc.list_stock(db, org, warehouse_id=warehouse_id, material_id=material_id, low_only=low_only)
    names = svc.material_names(db, {b.material_id for b in rows})
    return [_stock_row(b, names) for b in rows]


@router.get("/stock-card", response_model=StockCardOut)
def stock_card(
    warehouse_id: uuid.UUID,
    material_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.view")),
) -> StockCardOut:
    _require_warehouse(db, user, warehouse_id)
    org = _org(db, user)
    card = svc.stock_card(db, org, warehouse_id=warehouse_id, material_id=material_id)
    names = svc.material_names(db, {material_id})
    bal = card["balance"]
    return StockCardOut(
        warehouse_id=warehouse_id, material_id=material_id,
        balance=_stock_row(bal, names) if bal is not None else None,
        transactions=[_ledger_row(t, names) for t in card["transactions"]],
    )


@router.post("/stock/min-quantity", response_model=StockRow)
def set_min_quantity(
    payload: MinQuantityIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> StockRow:
    _require_warehouse(db, user, payload.warehouse_id)
    bal = svc.set_minimum_quantity(
        db, organization_id=_org(db, user), warehouse_id=payload.warehouse_id,
        material_id=payload.material_id,
        minimum_quantity=Decimal(str(payload.minimum_quantity)), user=user,
    )
    names = svc.material_names(db, {bal.material_id})
    return _stock_row(bal, names)


# ------------------------------ Журнал ----------------------------------- #


def _ledger_row(t, names: dict) -> LedgerRow:
    return LedgerRow(
        id=t.id, warehouse_id=t.warehouse_id, material_id=t.material_id,
        material_name=names.get(t.material_id), transaction_type=t.transaction_type,
        quantity=str(t.quantity), unit_cost=str(t.unit_cost),
        source_type=t.source_type, source_id=t.source_id, occurred_at=t.occurred_at,
    )


@router.get("/ledger", response_model=list[LedgerRow])
def ledger(
    warehouse_id: uuid.UUID | None = None,
    material_id: uuid.UUID | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.view")),
) -> list[LedgerRow]:
    org = _org(db, user)
    if warehouse_id is not None:
        _require_warehouse(db, user, warehouse_id)
    txs = svc.list_ledger(db, org, warehouse_id=warehouse_id, material_id=material_id, limit=limit)
    names = svc.material_names(db, {t.material_id for t in txs})
    return [_ledger_row(t, names) for t in txs]


# ------------------------------ Резервы ---------------------------------- #


def _res_out(r: StockReservation, names: dict) -> ReservationOut:
    return ReservationOut(
        id=r.id, warehouse_id=r.warehouse_id, material_id=r.material_id,
        material_name=names.get(r.material_id), quantity=str(r.quantity),
        status=r.status, reserved_until=r.reserved_until, reason=r.reason,
        purchase_order_id=r.purchase_order_id, material_request_id=r.material_request_id,
    )


@router.get("/reservations", response_model=list[ReservationOut])
def reservations(
    warehouse_id: uuid.UUID | None = None,
    status_filter: str | None = Query(None, alias="status"),
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.view")),
) -> list[ReservationOut]:
    org = _org(db, user)
    if warehouse_id is not None:
        _require_warehouse(db, user, warehouse_id)
    rows = svc.list_reservations(db, org, warehouse_id=warehouse_id, status=status_filter)
    names = svc.material_names(db, {r.material_id for r in rows})
    return [_res_out(r, names) for r in rows]


@router.post("/reservations", response_model=ReservationOut, status_code=status.HTTP_201_CREATED)
def create_reservation(
    payload: ReservationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> ReservationOut:
    _require_warehouse(db, user, payload.warehouse_id)
    try:
        res = svc.create_reservation(
            db, organization_id=_org(db, user), warehouse_id=payload.warehouse_id,
            material_id=payload.material_id, quantity=Decimal(str(payload.quantity)),
            user=user, reserved_until=payload.reserved_until, reason=payload.reason,
        )
    except svc.InventoryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    names = svc.material_names(db, {res.material_id})
    return _res_out(res, names)


@router.post("/reservations/{reservation_id}/release", response_model=ReservationOut)
def release_reservation(
    reservation_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> ReservationOut:
    res = db.get(StockReservation, reservation_id)
    if res is None or res.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Резерв не найден")
    if res.warehouse_id is not None:
        _require_warehouse(db, user, res.warehouse_id)
    try:
        svc.release_reservation(db, res, user=user)
    except svc.InventoryError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    names = svc.material_names(db, {res.material_id})
    return _res_out(res, names)


# --------------------------- Места хранения ------------------------------ #


@router.get("/{warehouse_id}/locations", response_model=list[LocationOut])
def list_locations(
    warehouse_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.view")),
) -> list[LocationOut]:
    _require_warehouse(db, user, warehouse_id)
    return [
        LocationOut(id=l.id, warehouse_id=l.warehouse_id, name=l.name, code=l.code,
                    parent_location_id=l.parent_location_id)
        for l in svc.list_locations(db, warehouse_id)
    ]


@router.post("/{warehouse_id}/locations", response_model=LocationOut, status_code=status.HTTP_201_CREATED)
def create_location(
    warehouse_id: uuid.UUID,
    payload: LocationIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("warehouse.manage")),
) -> LocationOut:
    _require_warehouse(db, user, warehouse_id)
    loc = svc.create_location(
        db, warehouse_id=warehouse_id, name=payload.name, code=payload.code,
        parent_location_id=payload.parent_location_id, user=user,
        organization_id=_org(db, user),
    )
    return LocationOut(id=loc.id, warehouse_id=loc.warehouse_id, name=loc.name,
                       code=loc.code, parent_location_id=loc.parent_location_id)
