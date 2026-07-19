"""Бизнес-логика модуля «Техника, транспорт и инструмент» (§17, DATABASE.md §33.15–33.18).

Полный жизненный цикл: реестр → назначение на объект/ответственного →
эксплуатация (моточасы/пробег/простой) → топливо → техобслуживание/ремонт →
осмотры; инструмент — выдача/возврат с фиксацией состояния. Правила: единица не
назначается дважды одновременно; техника в ремонте/на осмотре или с открытым
заказом на обслуживание не выдаётся (§33.17); счётчики моточасов/пробега не
уменьшаются. Все значимые действия — в `audit_events`; изоляция по проекту (ABAC).
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Equipment,
    EquipmentAssignment,
    EquipmentInspection,
    EquipmentUsageLog,
    FuelTransaction,
    MaintenanceOrder,
    Tool,
    ToolAssignment,
    User,
)
from app.services.access import can_access_project
from app.services.audit import record_event


class EquipmentError(RuntimeError):
    """Нарушение правил учёта техники/инструмента."""


BLOCKED_STATUSES = ("under_repair", "under_inspection", "written_off")


# ------------------------------ Доступ (ABAC) ---------------------------- #


def can_access_equipment(session: Session, user: User, equipment: Equipment) -> bool:
    if equipment.current_project_id is None:
        return True
    return can_access_project(session, user, equipment.current_project_id)


def _has_open_maintenance(session: Session, asset_type: str, asset_id: uuid.UUID) -> bool:
    return session.execute(
        select(MaintenanceOrder).where(
            MaintenanceOrder.asset_type == asset_type,
            MaintenanceOrder.asset_id == asset_id,
            MaintenanceOrder.status.in_(("open", "in_progress")),
            MaintenanceOrder.deleted_at.is_(None),
        )
    ).scalars().first() is not None


# ------------------------------ Техника ---------------------------------- #


def register_equipment(session: Session, *, organization_id: uuid.UUID, user: User, **fields) -> Equipment:
    eq = Equipment(organization_id=organization_id, current_status="available",
                   created_by=user.id, **fields)
    session.add(eq)
    session.flush()
    _audit(session, user, "equipment.registered", organization_id, "equipment", eq.id,
           {"name": eq.name, "asset_type": eq.asset_type})
    session.commit()
    return eq


def assign_equipment(
    session: Session, equipment: Equipment, *, user: User,
    project_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    responsible_employee_id: uuid.UUID | None = None,
    operator_employee_id: uuid.UUID | None = None, task_id: uuid.UUID | None = None,
    assigned_until: datetime | None = None, notes: str | None = None,
) -> EquipmentAssignment:
    if equipment.current_status in BLOCKED_STATUSES:
        raise EquipmentError(f"техника в статусе '{equipment.current_status}' не может быть выдана")
    if equipment.current_status == "assigned":
        raise EquipmentError("техника уже назначена; сначала оформите возврат")
    if _has_open_maintenance(session, "equipment", equipment.id):
        raise EquipmentError("по технике есть открытый заказ на обслуживание — выдача запрещена")
    assignment = EquipmentAssignment(
        equipment_id=equipment.id, project_id=project_id, site_id=site_id,
        assigned_from=datetime.now(UTC), assigned_until=assigned_until,
        responsible_employee_id=responsible_employee_id,
        operator_employee_id=operator_employee_id, task_id=task_id,
        status="active", notes=notes, created_by=user.id,
    )
    session.add(assignment)
    equipment.current_status = "assigned"
    equipment.current_project_id = project_id
    equipment.current_site_id = site_id
    equipment.responsible_employee_id = responsible_employee_id
    equipment.operator_employee_id = operator_employee_id
    _audit(session, user, "equipment.assigned", equipment.organization_id, "equipment",
           equipment.id, {"project_id": str(project_id) if project_id else None})
    session.commit()
    return assignment


def return_equipment(session: Session, equipment: Equipment, *, user: User) -> Equipment:
    if equipment.current_status not in ("assigned", "in_use"):
        raise EquipmentError("возврат возможен только для выданной техники")
    for a in session.execute(
        select(EquipmentAssignment).where(
            EquipmentAssignment.equipment_id == equipment.id,
            EquipmentAssignment.status == "active",
        )
    ).scalars():
        a.status = "returned"
        a.returned_at = datetime.now(UTC)
    equipment.current_status = "available"
    equipment.current_project_id = None
    equipment.current_site_id = None
    _audit(session, user, "equipment.returned", equipment.organization_id, "equipment",
           equipment.id, {})
    session.commit()
    return equipment


def log_usage(
    session: Session, equipment: Equipment, *, user: User, usage_date: date,
    engine_hours_end: Decimal | None = None, odometer_end: Decimal | None = None,
    engine_hours_start: Decimal | None = None, odometer_start: Decimal | None = None,
    fuel_issued: Decimal = Decimal("0"), fuel_consumed: Decimal = Decimal("0"),
    downtime_hours: Decimal = Decimal("0"), downtime_reason: str | None = None,
    operator_employee_id: uuid.UUID | None = None, work_description: str | None = None,
) -> EquipmentUsageLog:
    if equipment.current_status in ("written_off",):
        raise EquipmentError("нельзя учитывать эксплуатацию списанной техники")
    # счётчики не уменьшаются
    if engine_hours_end is not None and Decimal(engine_hours_end) < Decimal(equipment.engine_hours):
        raise EquipmentError("моточасы не могут быть меньше текущего значения")
    if odometer_end is not None and Decimal(odometer_end) < Decimal(equipment.odometer_value):
        raise EquipmentError("пробег не может быть меньше текущего значения")
    log = EquipmentUsageLog(
        equipment_id=equipment.id, project_id=equipment.current_project_id,
        site_id=equipment.current_site_id, usage_date=usage_date,
        operator_employee_id=operator_employee_id or equipment.operator_employee_id,
        engine_hours_start=engine_hours_start if engine_hours_start is not None else equipment.engine_hours,
        engine_hours_end=engine_hours_end,
        odometer_start=odometer_start if odometer_start is not None else equipment.odometer_value,
        odometer_end=odometer_end, fuel_issued=fuel_issued, fuel_consumed=fuel_consumed,
        downtime_hours=downtime_hours, downtime_reason=downtime_reason,
        work_description=work_description,
    )
    session.add(log)
    if engine_hours_end is not None:
        equipment.engine_hours = Decimal(engine_hours_end)
    if odometer_end is not None:
        equipment.odometer_value = Decimal(odometer_end)
    if equipment.current_status == "assigned":
        equipment.current_status = "in_use"
    _audit(session, user, "equipment.usage_logged", equipment.organization_id, "equipment",
           equipment.id, {"date": str(usage_date), "downtime_hours": str(downtime_hours)})
    session.commit()
    return log


def record_inspection(
    session: Session, equipment: Equipment, *, user: User, inspection_type: str,
    result: str = "passed", operation_allowed: bool = True, defects: str | None = None,
    inspector_employee_id: uuid.UUID | None = None, next_inspection_at: date | None = None,
    file_id: uuid.UUID | None = None,
) -> EquipmentInspection:
    insp = EquipmentInspection(
        equipment_id=equipment.id, inspection_type=inspection_type,
        inspector_employee_id=inspector_employee_id, inspected_at=datetime.now(UTC),
        result=result, operation_allowed=operation_allowed, defects=defects,
        next_inspection_at=next_inspection_at, file_id=file_id,
    )
    session.add(insp)
    equipment.last_inspection_at = datetime.now(UTC).date()
    if next_inspection_at is not None:
        equipment.next_inspection_at = next_inspection_at
    # запрет эксплуатации до устранения — блокируем технику
    if not operation_allowed and equipment.current_status not in ("written_off",):
        equipment.current_status = "under_inspection"
    _audit(session, user, "equipment.inspected", equipment.organization_id, "equipment",
           equipment.id, {"result": result, "operation_allowed": operation_allowed})
    session.commit()
    return insp


# --------------------- Техобслуживание и ремонт -------------------------- #


def open_maintenance(
    session: Session, *, organization_id: uuid.UUID, user: User, asset_type: str,
    asset_id: uuid.UUID, maintenance_type: str = "planned", problem_description: str | None = None,
    priority: str = "normal", planned_start_at: datetime | None = None,
    estimated_cost: Decimal | None = None, responsible_employee_id: uuid.UUID | None = None,
    number: str | None = None,
) -> MaintenanceOrder:
    order = MaintenanceOrder(
        organization_id=organization_id, maintenance_order_number=number,
        asset_type=asset_type, asset_id=asset_id, maintenance_type=maintenance_type,
        problem_description=problem_description, reported_by=user.id,
        reported_at=datetime.now(UTC), priority=priority, planned_start_at=planned_start_at,
        estimated_cost=estimated_cost, responsible_employee_id=responsible_employee_id,
        status="open", created_by=user.id,
    )
    session.add(order)
    session.flush()
    _block_asset(session, asset_type, asset_id, "under_repair")
    _audit(session, user, "maintenance.opened", organization_id,
           "maintenance_order", order.id, {"asset_type": asset_type, "type": maintenance_type})
    session.commit()
    return order


def complete_maintenance(
    session: Session, order: MaintenanceOrder, *, user: User,
    actual_cost: Decimal | None = None, downtime_hours: Decimal = Decimal("0"),
) -> MaintenanceOrder:
    if order.status in ("completed", "cancelled"):
        raise EquipmentError("заказ уже закрыт")
    order.status = "completed"
    order.actual_end_at = datetime.now(UTC)
    order.actual_cost = actual_cost
    order.downtime_hours = downtime_hours
    session.flush()  # чтобы проверка открытых заказов увидела закрытие этого заказа
    # вернуть актив в доступное состояние, если нет других открытых заказов
    if not _has_open_maintenance(session, order.asset_type, order.asset_id):
        _block_asset(session, order.asset_type, order.asset_id, "available",
                     service_date=datetime.now(UTC).date())
    _audit(session, user, "maintenance.completed", order.organization_id,
           "maintenance_order", order.id, {"actual_cost": str(actual_cost) if actual_cost else None})
    session.commit()
    return order


def _block_asset(session, asset_type, asset_id, status, *, service_date=None):
    if asset_type == "equipment":
        eq = session.get(Equipment, asset_id)
        if eq is not None and eq.current_status not in ("written_off",):
            eq.current_status = status
            if service_date is not None:
                eq.last_service_at = service_date
    elif asset_type == "tool":
        tool = session.get(Tool, asset_id)
        if tool is not None and tool.current_status not in ("written_off",):
            tool.current_status = "under_repair" if status == "under_repair" else "available"


# ------------------------------ Топливо ---------------------------------- #


def record_fuel(
    session: Session, *, organization_id: uuid.UUID, user: User, transaction_type: str,
    fuel_type: str | None = None, quantity: Decimal = Decimal("0"),
    equipment_id: uuid.UUID | None = None, unit_price: Decimal | None = None,
    project_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    odometer_value: Decimal | None = None, engine_hours: Decimal | None = None,
    number: str | None = None, receipt_document_id: uuid.UUID | None = None,
) -> FuelTransaction:
    if quantity <= 0:
        raise EquipmentError("количество топлива должно быть больше нуля")
    total = None
    if unit_price is not None:
        total = (Decimal(quantity) * Decimal(unit_price)).quantize(Decimal("0.01"))
    tx = FuelTransaction(
        organization_id=organization_id, transaction_number=number,
        transaction_type=transaction_type, fuel_type=fuel_type, quantity=quantity,
        unit_price=unit_price, total_amount=total, equipment_id=equipment_id,
        project_id=project_id, site_id=site_id, odometer_value=odometer_value,
        engine_hours=engine_hours, receipt_document_id=receipt_document_id,
        occurred_at=datetime.now(UTC),
    )
    session.add(tx)
    _audit(session, user, "fuel.recorded", organization_id, "fuel_transaction", None,
           {"type": transaction_type, "quantity": str(quantity)})
    session.commit()
    return tx


# ------------------------------ Инструмент ------------------------------- #


def register_tool(session: Session, *, organization_id: uuid.UUID, user: User, **fields) -> Tool:
    tool = Tool(organization_id=organization_id, current_status="available",
                created_by=user.id, **fields)
    session.add(tool)
    session.flush()
    _audit(session, user, "tool.registered", organization_id, "tool", tool.id, {"name": tool.name})
    session.commit()
    return tool


def issue_tool(
    session: Session, tool: Tool, *, user: User, employee_id: uuid.UUID,
    project_id: uuid.UUID | None = None, site_id: uuid.UUID | None = None,
    expected_return_at: datetime | None = None, condition_at_issue: str | None = None,
) -> ToolAssignment:
    if tool.current_status not in ("available", "reserved"):
        raise EquipmentError(f"инструмент в статусе '{tool.current_status}' нельзя выдать")
    assignment = ToolAssignment(
        tool_id=tool.id, employee_id=employee_id, project_id=project_id, site_id=site_id,
        issued_at=datetime.now(UTC), expected_return_at=expected_return_at,
        condition_at_issue=condition_at_issue or tool.condition_status, status="issued",
        created_by=user.id,
    )
    session.add(assignment)
    tool.current_status = "issued"
    tool.current_employee_id = employee_id
    tool.current_project_id = project_id
    _audit(session, user, "tool.issued", tool.organization_id, "tool", tool.id,
           {"employee_id": str(employee_id)})
    session.commit()
    return assignment


def return_tool(
    session: Session, tool: Tool, *, user: User, condition_at_return: str | None = None,
) -> Tool:
    if tool.current_status not in ("issued", "in_use"):
        raise EquipmentError("возврат возможен только для выданного инструмента")
    for a in session.execute(
        select(ToolAssignment).where(
            ToolAssignment.tool_id == tool.id, ToolAssignment.status == "issued",
        )
    ).scalars():
        a.status = "returned"
        a.returned_at = datetime.now(UTC)
        a.condition_at_return = condition_at_return
    tool.current_status = "available"
    tool.current_employee_id = None
    tool.current_project_id = None
    if condition_at_return:
        tool.condition_status = condition_at_return
    _audit(session, user, "tool.returned", tool.organization_id, "tool", tool.id,
           {"condition": condition_at_return})
    session.commit()
    return tool


# ------------------------------ Помощники -------------------------------- #


def _audit(session, user, action, org_id, entity_type, entity_id, new_values):
    record_event(
        session, actor_type="user", action=action, actor_user_id=user.id,
        organization_id=org_id, entity_type=entity_type, entity_id=entity_id,
        new_values=new_values, risk_level="R1", commit=False,
    )
