"""Бизнес-логика модуля «Проектирование и дизайн».

Ключевые правила (WORKFLOWS §16, D-001/D-002):
- замечание заказчика/экспертизы превращается в задачу с ответственным и сроком;
- выпуск рабочей документации в производство — только через утверждённую версию
  документа и согласование уровня R3 (подтверждение уполномоченного человека);
- массовое изменение/удаление/аннулирование утверждённой документации — R4 с MFA;
- утверждение ТЗ/концепции — уровень R2 (человек в контуре);
- проверка реализуемости выполняется сервисом/агентом (рекомендация, R0/R1) через
  провайдер данных: сейчас — демонстрационные данные, интерфейс готов к подключению
  реальных каталогов, цен, остатков и сроков поставщиков;
- все значимые действия записываются в `audit_events`.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    Approval,
    ApprovalStep,
    DesignBrief,
    DesignConcept,
    DesignIssue,
    DesignSpecification,
    Document,
    MarketAvailabilityCheck,
    ProjectDiscipline,
    SupplierProduct,
    Task,
    TaskAssignment,
    User,
)
from app.services.access import can_access_project
from app.services.audit import record_event

RELEASE_RISK = "R3"
ANNUL_RISK = "R4"
APPROVAL_RISK = "R2"


class DesignStateError(RuntimeError):
    """Недопустимый переход состояния в модуле проектирования."""


class ReleaseAuthorizationError(RuntimeError):
    """Недостаточно условий для действия (например, нет MFA для R4)."""


# ------------------------ Замечание → задача ----------------------------- #


def create_issue_with_task(
    session: Session,
    *,
    organization_id: uuid.UUID,
    project_id: uuid.UUID,
    title: str,
    user: User,
    description: str | None = None,
    source: str = "internal",
    severity: str = "normal",
    due_date: date | None = None,
    discipline_id: uuid.UUID | None = None,
    document_id: uuid.UUID | None = None,
    responsible_employee_id: uuid.UUID | None = None,
    create_task: bool = True,
) -> DesignIssue:
    """Создаёт замечание и (по умолчанию) связанную задачу с ответственным."""
    issue = DesignIssue(
        organization_id=organization_id,
        project_id=project_id,
        discipline_id=discipline_id,
        document_id=document_id,
        source=source,
        title=title,
        description=description,
        severity=severity,
        due_date=due_date,
        responsible_employee_id=responsible_employee_id,
        created_by=user.id,
    )
    session.add(issue)
    session.flush()

    if create_task:
        task = Task(
            organization_id=organization_id,
            project_id=project_id,
            title=f"Замечание: {title}",
            description=description,
            status="approved",
            priority="high" if severity in ("high", "critical") else "normal",
            source_type="design_issue",
            source_id=issue.id,
            owner_employee_id=responsible_employee_id,
            due_at=datetime.combine(due_date, datetime.min.time(), UTC)
            if due_date
            else None,
            created_by_user_id=user.id,
        )
        session.add(task)
        session.flush()
        if responsible_employee_id is not None:
            session.add(
                TaskAssignment(
                    task_id=task.id,
                    employee_id=responsible_employee_id,
                    assignment_role="responsible",
                    assigned_by=user.id,
                )
            )
        issue.linked_task_id = task.id

    record_event(
        session,
        actor_type="user",
        action="design.issue.created",
        actor_user_id=user.id,
        organization_id=organization_id,
        entity_type="design_issue",
        entity_id=issue.id,
        new_values={"title": title, "linked_task_id": str(issue.linked_task_id) if issue.linked_task_id else None},
        commit=False,
    )
    session.commit()
    return issue


# ------------------- Проверка реализуемости (провайдер) ------------------ #


@dataclass
class RealizabilityResult:
    availability_status: str
    supplier_count: int
    minimum_price: Decimal | None
    maximum_price: Decimal | None
    lead_time_days: int | None
    regional_delivery_possible: bool
    recommended_option: str | None
    risk_notes: str | None
    source: str = "demo"


class RealizabilityProvider(Protocol):
    """Источник данных о реализуемости (наличие, цены, сроки поставщиков).

    Демонстрационная реализация опирается на `supplier_products`. Реальный
    провайдер (каталоги/маркетплейсы/остатки) подключается по этому же интерфейсу.
    """

    def check(
        self, *, material_id: uuid.UUID | None, region: str | None
    ) -> RealizabilityResult: ...


class DemoRealizabilityProvider:
    """Провайдер на безопасных демонстрационных данных из `supplier_products`."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def check(
        self, *, material_id: uuid.UUID | None, region: str | None
    ) -> RealizabilityResult:
        products: list[SupplierProduct] = []
        if material_id is not None:
            products = list(
                self._session.execute(
                    select(SupplierProduct).where(
                        SupplierProduct.material_id == material_id,
                        SupplierProduct.deleted_at.is_(None),
                    )
                ).scalars()
            )
        prices = [p.price for p in products if p.price is not None]
        leads = [p.lead_time_days for p in products if p.lead_time_days is not None]
        regional_ok = any(
            region is None or (p.region or "") == region or p.region is None
            for p in products
        )
        if not products:
            return RealizabilityResult(
                availability_status="unknown",
                supplier_count=0,
                minimum_price=None,
                maximum_price=None,
                lead_time_days=None,
                regional_delivery_possible=False,
                recommended_option=None,
                risk_notes="Нет данных о поставщиках — требуется проверка вручную",
            )
        status = "available" if len(products) >= 2 else "limited"
        return RealizabilityResult(
            availability_status=status,
            supplier_count=len(products),
            minimum_price=min(prices) if prices else None,
            maximum_price=max(prices) if prices else None,
            lead_time_days=min(leads) if leads else None,
            regional_delivery_possible=bool(regional_ok),
            recommended_option=(
                products[0].supplier_name or products[0].supplier_sku
            ),
            risk_notes=None if status == "available" else "Ограниченное предложение",
        )


def run_realizability_check(
    session: Session,
    specification: DesignSpecification,
    *,
    user: User,
    provider: RealizabilityProvider | None = None,
    region: str | None = None,
) -> MarketAvailabilityCheck:
    """Выполняет проверку реализуемости спецификации и сохраняет результат."""
    prov = provider or DemoRealizabilityProvider(session)
    result = prov.check(material_id=specification.material_id, region=region)
    check = MarketAvailabilityCheck(
        design_specification_id=specification.id,
        checked_at=datetime.now(UTC),
        source=result.source,
        availability_status=result.availability_status,
        supplier_count=result.supplier_count,
        minimum_price=result.minimum_price,
        maximum_price=result.maximum_price,
        lead_time_days=result.lead_time_days,
        regional_delivery_possible=result.regional_delivery_possible,
        recommended_option=result.recommended_option,
        risk_notes=result.risk_notes,
    )
    session.add(check)
    record_event(
        session,
        actor_type="user",
        action="design.realizability.checked",
        actor_user_id=user.id,
        entity_type="design_specification",
        entity_id=specification.id,
        new_values={"availability_status": result.availability_status},
        risk_level="R1",
        commit=False,
    )
    session.commit()
    return check


# ---------------------- Утверждение ТЗ (R2) ------------------------------ #


def approve_brief(session: Session, brief: DesignBrief, *, user: User) -> DesignBrief:
    """Утверждает техническое задание (R2, человек в контуре)."""
    if brief.status == "approved":
        raise DesignStateError("ТЗ уже утверждено")
    approval = Approval(
        organization_id=brief.organization_id,
        entity_type="design_brief",
        entity_id=brief.id,
        approval_type="design_brief_approval",
        requested_by_user_id=user.id,
        status="approved",
        current_step=1,
        completed_at=datetime.now(UTC),
    )
    session.add(approval)
    session.flush()
    session.add(
        ApprovalStep(
            approval_id=approval.id,
            step_number=1,
            approver_user_id=user.id,
            decision="approved",
            decided_at=datetime.now(UTC),
        )
    )
    brief.status = "approved"
    brief.approved_at = datetime.now(UTC)
    brief.approved_by = user.id
    brief.approval_id = approval.id
    record_event(
        session,
        actor_type="user",
        action="design.brief.approved",
        actor_user_id=user.id,
        organization_id=brief.organization_id,
        entity_type="design_brief",
        entity_id=brief.id,
        approval_id=approval.id,
        risk_level=APPROVAL_RISK,
        commit=False,
    )
    session.commit()
    return brief


# ----------------- Выпуск рабочей документации (R3/R4) ------------------- #


def request_documentation_release(
    session: Session,
    discipline: ProjectDiscipline,
    *,
    document_id: uuid.UUID,
    user: User,
) -> Approval:
    """Запрашивает выпуск раздела в производство (R3).

    Разрешено только через утверждённую версию документа (WORKFLOWS §16.7).
    """
    document = session.get(Document, document_id)
    if document is None or document.deleted_at is not None:
        raise DesignStateError("документ не найден")
    if document.status != "approved":
        raise DesignStateError(
            "выпуск возможен только через утверждённую версию документа"
        )
    if discipline.status == "issued":
        raise DesignStateError("раздел уже выпущен")
    approval = Approval(
        organization_id=None,
        entity_type="project_discipline",
        entity_id=discipline.id,
        approval_type="documentation_release",
        requested_by_user_id=user.id,
        status="pending",
        current_step=1,
    )
    session.add(approval)
    session.flush()
    record_event(
        session,
        actor_type="user",
        action="design.documentation.release_requested",
        actor_user_id=user.id,
        entity_type="project_discipline",
        entity_id=discipline.id,
        new_values={"document_id": str(document_id)},
        approval_id=approval.id,
        risk_level=RELEASE_RISK,
        commit=False,
    )
    session.commit()
    return approval


def record_release_decision(
    session: Session,
    approval: Approval,
    *,
    user: User,
    decision: str,
    comment: str | None = None,
) -> ProjectDiscipline:
    """Фиксирует решение по выпуску раздела (R3, подтверждение человека)."""
    if decision not in ("approved", "rejected"):
        raise DesignStateError(f"неизвестное решение '{decision}'")
    if approval.status != "pending":
        raise DesignStateError("согласование уже завершено")
    discipline = session.get(ProjectDiscipline, approval.entity_id)
    if discipline is None:
        raise DesignStateError("раздел не найден")
    session.add(
        ApprovalStep(
            approval_id=approval.id,
            step_number=approval.current_step,
            approver_user_id=user.id,
            decision=decision,
            comment=comment,
            decided_at=datetime.now(UTC),
        )
    )
    approval.status = decision
    approval.completed_at = datetime.now(UTC)
    if decision == "approved":
        discipline.status = "issued"
        discipline.gip_status = "checked"
    record_event(
        session,
        actor_type="user",
        action=f"design.documentation.release_{decision}",
        actor_user_id=user.id,
        entity_type="project_discipline",
        entity_id=discipline.id,
        approval_id=approval.id,
        reason=comment,
        risk_level=RELEASE_RISK,
        commit=False,
    )
    session.commit()
    return discipline


def annul_documentation(
    session: Session,
    discipline: ProjectDiscipline,
    *,
    user: User,
    reason: str,
    mfa_verified: bool = False,
) -> ProjectDiscipline:
    """Аннулирует выпущенную документацию (R4, требует усиленной аутентификации)."""
    if not mfa_verified:
        raise ReleaseAuthorizationError(
            "аннулирование утверждённой документации (R4) требует подтверждения MFA"
        )
    discipline.status = "cancelled"
    discipline.gip_status = "rejected"
    record_event(
        session,
        actor_type="user",
        action="design.documentation.annulled",
        actor_user_id=user.id,
        entity_type="project_discipline",
        entity_id=discipline.id,
        reason=reason,
        risk_level=ANNUL_RISK,
        commit=False,
    )
    session.commit()
    return discipline


# ----------------------- Доступ по проекту (ABAC) ------------------------ #


def can_access_project_id(
    session: Session, user: User, project_id: uuid.UUID
) -> bool:
    return can_access_project(session, user, project_id)
