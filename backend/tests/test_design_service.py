"""Тесты бизнес-логики модуля «Проектирование и дизайн»."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import pytest

from app.core.security import hash_password
from app.models import (
    Counterparty,
    DesignBrief,
    DesignSpecification,
    Document,
    Employee,
    Material,
    Organization,
    Project,
    ProjectDiscipline,
    Supplier,
    SupplierProduct,
    Task,
    TaskAssignment,
    User,
)
from app.services import design as svc


def _base(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Проект")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Проектировщик Т.")
    db.add(emp)
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:6]}@ex.com", password_hash=hash_password("x"))
    db.add(user)
    db.flush()
    return org, project, emp, user


def test_issue_creates_linked_task(db_session) -> None:
    org, project, emp, user = _base(db_session)
    issue = svc.create_issue_with_task(
        db_session,
        organization_id=org.id,
        project_id=project.id,
        title="Замечание экспертизы по разделу ВК",
        user=user,
        severity="high",
        due_date=date(2026, 8, 1),
        responsible_employee_id=emp.id,
    )
    assert issue.linked_task_id is not None
    task = db_session.get(Task, issue.linked_task_id)
    assert task is not None
    assert task.source_type == "design_issue"
    assert task.source_id == issue.id
    assert task.priority == "high"
    assigns = db_session.query(TaskAssignment).filter_by(task_id=task.id).all()
    assert len(assigns) == 1
    assert assigns[0].employee_id == emp.id


def test_issue_without_task(db_session) -> None:
    org, project, _, user = _base(db_session)
    issue = svc.create_issue_with_task(
        db_session, organization_id=org.id, project_id=project.id,
        title="Внутреннее замечание", user=user, create_task=False,
    )
    assert issue.linked_task_id is None


def test_realizability_demo_provider(db_session) -> None:
    org, project, _, user = _base(db_session)
    material = Material(organization_id=org.id, name="Труба ПНД Ø315")
    cp = Counterparty(organization_id=org.id, name="Поставщик 1")
    db_session.add_all([material, cp])
    db_session.flush()
    supplier = Supplier(counterparty_id=cp.id)
    db_session.add(supplier)
    db_session.flush()
    db_session.add_all([
        SupplierProduct(supplier_id=supplier.id, material_id=material.id,
                        supplier_name="ПолимерСнаб", price=Decimal("3200"),
                        lead_time_days=10, region="Юг"),
        SupplierProduct(supplier_id=supplier.id, material_id=material.id,
                        supplier_name="ТрубаТорг", price=Decimal("3500"),
                        lead_time_days=7, region="Юг"),
    ])
    spec = DesignSpecification(project_id=project.id, material_id=material.id,
                               category="equipment", quantity=Decimal("100"))
    db_session.add(spec)
    db_session.commit()

    check = svc.run_realizability_check(db_session, spec, user=user)
    assert check.availability_status == "available"
    assert check.supplier_count == 2
    assert check.minimum_price == Decimal("3200.00")
    assert check.lead_time_days == 7


def test_realizability_no_data(db_session) -> None:
    org, project, _, user = _base(db_session)
    spec = DesignSpecification(project_id=project.id, category="other",
                               quantity=Decimal("1"))
    db_session.add(spec)
    db_session.commit()
    check = svc.run_realizability_check(db_session, spec, user=user)
    assert check.availability_status == "unknown"
    assert check.supplier_count == 0


def test_approve_brief_r2(db_session) -> None:
    org, project, _, user = _base(db_session)
    brief = DesignBrief(organization_id=org.id, project_id=project.id)
    db_session.add(brief)
    db_session.commit()
    svc.approve_brief(db_session, brief, user=user)
    assert brief.status == "approved"
    assert brief.approval_id is not None


def test_release_gate_requires_approved_document(db_session) -> None:
    org, project, _, user = _base(db_session)
    disc = ProjectDiscipline(project_id=project.id, name="Раздел ВК")
    doc = Document(organization_id=org.id, project_id=project.id,
                   title="Рабочая документация ВК", status="draft")
    db_session.add_all([disc, doc])
    db_session.commit()
    # черновик документа — выпуск запрещён
    with pytest.raises(svc.DesignStateError):
        svc.request_documentation_release(db_session, disc, document_id=doc.id, user=user)
    # утверждаем документ — выпуск разрешён
    doc.status = "approved"
    db_session.commit()
    approval = svc.request_documentation_release(
        db_session, disc, document_id=doc.id, user=user
    )
    assert approval.status == "pending"
    svc.record_release_decision(db_session, approval, user=user, decision="approved")
    assert disc.status == "issued"
    assert disc.gip_status == "checked"


def test_annul_requires_mfa(db_session) -> None:
    org, project, _, user = _base(db_session)
    disc = ProjectDiscipline(project_id=project.id, name="Раздел", status="issued")
    db_session.add(disc)
    db_session.commit()
    with pytest.raises(svc.ReleaseAuthorizationError):
        svc.annul_documentation(db_session, disc, user=user, reason="ошибка", mfa_verified=False)
    svc.annul_documentation(db_session, disc, user=user, reason="ошибка", mfa_verified=True)
    assert disc.status == "cancelled"
