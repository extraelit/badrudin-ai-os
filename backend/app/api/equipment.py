"""API модуля «Техника, транспорт и инструмент».

Backend — единственная точка доступа. RBAC: `equipment.view` (реестр, история,
сводка), `equipment.manage` (реестр, выдача/возврат, эксплуатация, топливо,
инструмент, осмотры), `equipment.maintain` (техобслуживание и ремонт). ABAC:
доступ к единице — через её текущий проект; выдача на проект требует доступа к
проекту. Все значимые действия — в `audit_events`.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.db.session import get_db
from app.models import (
    Employee,
    Equipment,
    EquipmentUsageLog,
    MaintenanceOrder,
    Project,
    Tool,
    User,
)
from app.schemas.equipment import (
    AssignIn,
    AssignmentOut,
    EquipmentIn,
    EquipmentOut,
    EquipmentSummaryOut,
    FuelIn,
    FuelOut,
    InspectionIn,
    InspectionOut,
    MaintenanceCompleteIn,
    MaintenanceIn,
    MaintenanceOut,
    ToolAssignmentOut,
    ToolIn,
    ToolIssueIn,
    ToolOut,
    ToolReturnIn,
    UsageIn,
    UsageOut,
)
from app.services import equipment as svc

router = APIRouter(prefix="/equipment", tags=["equipment"])


def _org(db: Session, user: User) -> uuid.UUID:
    if user.employee_id is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Пользователь не связан с сотрудником")
    emp = db.get(Employee, user.employee_id)
    return emp.organization_id


def _dec(v) -> Decimal | None:
    return Decimal(str(v)) if v is not None else None


def _get_equipment(db: Session, user: User, equipment_id: uuid.UUID) -> Equipment:
    eq = db.get(Equipment, equipment_id)
    if eq is None or eq.deleted_at is not None or eq.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Техника не найдена")
    if not svc.can_access_equipment(db, user, eq):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к технике")
    return eq


def _project_access(db: Session, user: User, project_id: uuid.UUID | None) -> None:
    if project_id is None:
        return
    project = db.get(Project, project_id)
    if project is None or project.deleted_at is not None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Проект не найден")
    from app.services.access import can_access_project

    if not can_access_project(db, user, project_id):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Нет доступа к проекту")


def _get_tool(db: Session, user: User, tool_id: uuid.UUID) -> Tool:
    tool = db.get(Tool, tool_id)
    if tool is None or tool.deleted_at is not None or tool.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Инструмент не найден")
    return tool


def _eq_out(e: Equipment) -> EquipmentOut:
    return EquipmentOut(
        id=e.id, asset_number=e.asset_number, name=e.name, asset_type=e.asset_type,
        ownership_type=e.ownership_type, current_status=e.current_status,
        current_project_id=e.current_project_id,
        responsible_employee_id=e.responsible_employee_id,
        odometer_value=str(e.odometer_value), engine_hours=str(e.engine_hours),
        fuel_type=e.fuel_type, next_service_at=e.next_service_at,
        next_inspection_at=e.next_inspection_at,
    )


def _guard(exc: svc.EquipmentError) -> HTTPException:
    return HTTPException(status.HTTP_409_CONFLICT, str(exc))


# ------------------------------- Сводка ---------------------------------- #


@router.get("/summary", response_model=EquipmentSummaryOut)
def summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.view")),
) -> EquipmentSummaryOut:
    org = _org(db, user)

    def _eq(*w):
        return int(db.scalar(select(func.count()).select_from(Equipment).where(
            Equipment.organization_id == org, Equipment.deleted_at.is_(None), *w)) or 0)

    def _tool(*w):
        return int(db.scalar(select(func.count()).select_from(Tool).where(
            Tool.organization_id == org, Tool.deleted_at.is_(None), *w)) or 0)

    service_due = _eq(Equipment.next_service_at.is_not(None), Equipment.next_service_at <= date.today())
    return EquipmentSummaryOut(
        equipment_total=_eq(), equipment_available=_eq(Equipment.current_status == "available"),
        equipment_assigned=_eq(Equipment.current_status.in_(("assigned", "in_use"))),
        equipment_under_repair=_eq(Equipment.current_status.in_(("under_repair", "under_inspection"))),
        maintenance_open=int(db.scalar(select(func.count()).select_from(MaintenanceOrder).where(
            MaintenanceOrder.organization_id == org, MaintenanceOrder.status.in_(("open", "in_progress")),
            MaintenanceOrder.deleted_at.is_(None))) or 0),
        service_due=service_due, tools_total=_tool(),
        tools_issued=_tool(Tool.current_status.in_(("issued", "in_use"))),
    )


# ------------------------------ Техника ---------------------------------- #


@router.get("", response_model=list[EquipmentOut])
def list_equipment(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.view")),
) -> list[EquipmentOut]:
    org = _org(db, user)
    rows = db.execute(
        select(Equipment).where(Equipment.organization_id == org, Equipment.deleted_at.is_(None))
        .order_by(Equipment.created_at.desc())
    ).scalars()
    return [_eq_out(e) for e in rows]


@router.post("", response_model=EquipmentOut, status_code=status.HTTP_201_CREATED)
def register_equipment(
    payload: EquipmentIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> EquipmentOut:
    eq = svc.register_equipment(db, organization_id=_org(db, user), user=user,
                                **payload.model_dump(exclude_none=True))
    return _eq_out(eq)


@router.get("/{equipment_id}", response_model=EquipmentOut)
def get_equipment(
    equipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.view")),
) -> EquipmentOut:
    return _eq_out(_get_equipment(db, user, equipment_id))


@router.post("/{equipment_id}/assign", response_model=AssignmentOut, status_code=status.HTTP_201_CREATED)
def assign_equipment(
    equipment_id: uuid.UUID, payload: AssignIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> AssignmentOut:
    eq = _get_equipment(db, user, equipment_id)
    _project_access(db, user, payload.project_id)
    try:
        a = svc.assign_equipment(db, eq, user=user, **payload.model_dump())
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return AssignmentOut(id=a.id, equipment_id=a.equipment_id, project_id=a.project_id,
                         status=a.status, responsible_employee_id=a.responsible_employee_id)


@router.post("/{equipment_id}/return", response_model=EquipmentOut)
def return_equipment(
    equipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> EquipmentOut:
    eq = _get_equipment(db, user, equipment_id)
    try:
        svc.return_equipment(db, eq, user=user)
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return _eq_out(eq)


@router.post("/{equipment_id}/usage", response_model=UsageOut, status_code=status.HTTP_201_CREATED)
def log_usage(
    equipment_id: uuid.UUID, payload: UsageIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> UsageOut:
    eq = _get_equipment(db, user, equipment_id)
    try:
        log = svc.log_usage(
            db, eq, user=user, usage_date=payload.usage_date,
            engine_hours_end=_dec(payload.engine_hours_end), odometer_end=_dec(payload.odometer_end),
            engine_hours_start=_dec(payload.engine_hours_start), odometer_start=_dec(payload.odometer_start),
            fuel_issued=_dec(payload.fuel_issued), fuel_consumed=_dec(payload.fuel_consumed),
            downtime_hours=_dec(payload.downtime_hours), downtime_reason=payload.downtime_reason,
            operator_employee_id=payload.operator_employee_id, work_description=payload.work_description,
        )
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return UsageOut(id=log.id, equipment_id=log.equipment_id, usage_date=log.usage_date,
                    engine_hours_end=str(log.engine_hours_end) if log.engine_hours_end is not None else None,
                    odometer_end=str(log.odometer_end) if log.odometer_end is not None else None,
                    downtime_hours=str(log.downtime_hours))


@router.get("/{equipment_id}/usage", response_model=list[UsageOut])
def list_usage(
    equipment_id: uuid.UUID,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.view")),
) -> list[UsageOut]:
    eq = _get_equipment(db, user, equipment_id)
    rows = db.execute(
        select(EquipmentUsageLog).where(EquipmentUsageLog.equipment_id == eq.id)
        .order_by(EquipmentUsageLog.usage_date.desc())
    ).scalars()
    return [
        UsageOut(id=u.id, equipment_id=u.equipment_id, usage_date=u.usage_date,
                 engine_hours_end=str(u.engine_hours_end) if u.engine_hours_end is not None else None,
                 odometer_end=str(u.odometer_end) if u.odometer_end is not None else None,
                 downtime_hours=str(u.downtime_hours))
        for u in rows
    ]


@router.post("/{equipment_id}/inspection", response_model=InspectionOut, status_code=status.HTTP_201_CREATED)
def record_inspection(
    equipment_id: uuid.UUID, payload: InspectionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> InspectionOut:
    eq = _get_equipment(db, user, equipment_id)
    insp = svc.record_inspection(
        db, eq, user=user, inspection_type=payload.inspection_type, result=payload.result,
        operation_allowed=payload.operation_allowed, defects=payload.defects,
        inspector_employee_id=payload.inspector_employee_id, next_inspection_at=payload.next_inspection_at,
    )
    return InspectionOut(id=insp.id, inspection_type=insp.inspection_type, result=insp.result,
                         operation_allowed=insp.operation_allowed)


# --------------------- Техобслуживание и ремонт -------------------------- #


def _mo_out(o: MaintenanceOrder) -> MaintenanceOut:
    return MaintenanceOut(id=o.id, asset_type=o.asset_type, asset_id=o.asset_id,
                          maintenance_type=o.maintenance_type, status=o.status, priority=o.priority,
                          actual_cost=str(o.actual_cost) if o.actual_cost is not None else None)


@router.get("/maintenance/orders", response_model=list[MaintenanceOut])
def list_maintenance(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.view")),
) -> list[MaintenanceOut]:
    org = _org(db, user)
    rows = db.execute(
        select(MaintenanceOrder).where(MaintenanceOrder.organization_id == org,
                                       MaintenanceOrder.deleted_at.is_(None))
        .order_by(MaintenanceOrder.created_at.desc())
    ).scalars()
    return [_mo_out(o) for o in rows]


@router.post("/maintenance", response_model=MaintenanceOut, status_code=status.HTTP_201_CREATED)
def open_maintenance(
    payload: MaintenanceIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.maintain")),
) -> MaintenanceOut:
    org = _org(db, user)
    # проверка принадлежности актива организации
    if payload.asset_type == "equipment":
        _get_equipment(db, user, payload.asset_id)
    else:
        _get_tool(db, user, payload.asset_id)
    order = svc.open_maintenance(
        db, organization_id=org, user=user, asset_type=payload.asset_type,
        asset_id=payload.asset_id, maintenance_type=payload.maintenance_type,
        problem_description=payload.problem_description, priority=payload.priority,
        planned_start_at=payload.planned_start_at, estimated_cost=_dec(payload.estimated_cost),
        responsible_employee_id=payload.responsible_employee_id, number=payload.number,
    )
    return _mo_out(order)


@router.post("/maintenance/{order_id}/complete", response_model=MaintenanceOut)
def complete_maintenance(
    order_id: uuid.UUID, payload: MaintenanceCompleteIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.maintain")),
) -> MaintenanceOut:
    order = db.get(MaintenanceOrder, order_id)
    if order is None or order.deleted_at is not None or order.organization_id != _org(db, user):
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Заказ не найден")
    try:
        svc.complete_maintenance(db, order, user=user, actual_cost=_dec(payload.actual_cost),
                                 downtime_hours=_dec(payload.downtime_hours))
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return _mo_out(order)


# ------------------------------ Топливо ---------------------------------- #


@router.post("/fuel", response_model=FuelOut, status_code=status.HTTP_201_CREATED)
def record_fuel(
    payload: FuelIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> FuelOut:
    if payload.equipment_id is not None:
        _get_equipment(db, user, payload.equipment_id)
    _project_access(db, user, payload.project_id)
    try:
        tx = svc.record_fuel(
            db, organization_id=_org(db, user), user=user,
            transaction_type=payload.transaction_type, fuel_type=payload.fuel_type,
            quantity=_dec(payload.quantity), equipment_id=payload.equipment_id,
            unit_price=_dec(payload.unit_price), project_id=payload.project_id,
            odometer_value=_dec(payload.odometer_value), engine_hours=_dec(payload.engine_hours),
            number=payload.number,
        )
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return FuelOut(id=tx.id, transaction_type=tx.transaction_type, fuel_type=tx.fuel_type,
                   quantity=str(tx.quantity),
                   total_amount=str(tx.total_amount) if tx.total_amount is not None else None,
                   equipment_id=tx.equipment_id)


# ------------------------------ Инструмент ------------------------------- #


def _tool_out(t: Tool) -> ToolOut:
    return ToolOut(id=t.id, inventory_number=t.inventory_number, name=t.name,
                   tool_type=t.tool_type, current_status=t.current_status,
                   condition_status=t.condition_status, current_employee_id=t.current_employee_id)


@router.get("/tools/list", response_model=list[ToolOut])
def list_tools(
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.view")),
) -> list[ToolOut]:
    org = _org(db, user)
    rows = db.execute(
        select(Tool).where(Tool.organization_id == org, Tool.deleted_at.is_(None))
        .order_by(Tool.created_at.desc())
    ).scalars()
    return [_tool_out(t) for t in rows]


@router.post("/tools", response_model=ToolOut, status_code=status.HTTP_201_CREATED)
def register_tool(
    payload: ToolIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> ToolOut:
    tool = svc.register_tool(db, organization_id=_org(db, user), user=user,
                             **payload.model_dump(exclude_none=True))
    return _tool_out(tool)


@router.post("/tools/{tool_id}/issue", response_model=ToolAssignmentOut, status_code=status.HTTP_201_CREATED)
def issue_tool(
    tool_id: uuid.UUID, payload: ToolIssueIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> ToolAssignmentOut:
    tool = _get_tool(db, user, tool_id)
    _project_access(db, user, payload.project_id)
    try:
        a = svc.issue_tool(db, tool, user=user, employee_id=payload.employee_id,
                           project_id=payload.project_id, site_id=payload.site_id,
                           expected_return_at=payload.expected_return_at,
                           condition_at_issue=payload.condition_at_issue)
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return ToolAssignmentOut(id=a.id, tool_id=a.tool_id, employee_id=a.employee_id, status=a.status)


@router.post("/tools/{tool_id}/return", response_model=ToolOut)
def return_tool(
    tool_id: uuid.UUID, payload: ToolReturnIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_permission("equipment.manage")),
) -> ToolOut:
    tool = _get_tool(db, user, tool_id)
    try:
        svc.return_tool(db, tool, user=user, condition_at_return=payload.condition_at_return)
    except svc.EquipmentError as exc:
        raise _guard(exc) from exc
    return _tool_out(tool)
