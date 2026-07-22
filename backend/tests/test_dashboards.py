"""Тесты руководительских панелей и эскалаций (этап H, PR-H).

Проверяют: сводка агрегирует процессы/просрочки/ожидающие согласования/исключения;
эскалация создаёт внутренние (in_app) уведомления руководителю и идемпотентна;
всё ограничено доступными проектами (ABAC) и организацией; RBAC на эндпоинтах.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    Employee,
    Notification,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import dashboards as svc
from app.services import workflow as wf


def _org(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    return org


def _user(db, org, *, perms=(), project=None, member=True, email=None):
    emp = Employee(organization_id=org.id, full_name="Сотрудник")
    db.add(emp)
    db.flush()
    user = User(email=email or f"u{uuid.uuid4().hex[:8]}@ex.com",
                password_hash=hash_password("x"), status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = db.query(Permission).filter(Permission.code == pc).first()
        if p is None:
            p = Permission(code=pc)
            db.add(p)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    if project is not None and member:
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id,
                             project_role="member"))
    db.commit()
    return user


def _overdue_process(db, org, *, manager):
    p = wf.create_process(db, org.id, process_kind="task", title="Просроченная",
                          author_user_id=uuid.uuid4(), risk_level="R1",
                          due_at=datetime.now(UTC) - timedelta(days=2))
    executor = uuid.uuid4()
    wf.assign(db, p, initiator_user_id=uuid.uuid4(), executor_id=executor,
              responsible_manager_id=manager)
    db.commit()
    return p


# ---------------------------------------------------------------------------
# Сводка
# ---------------------------------------------------------------------------

def test_overview_counts(db_session) -> None:
    org = _org(db_session)
    mgr = _user(db_session, org, perms=["management.view", "task.view"])
    _overdue_process(db_session, org, manager=mgr.id)
    ov = svc.manager_overview(db_session, mgr, org.id)
    assert ov["processes_total"] >= 1
    assert ov["overdue"] >= 1


def test_overdue_list(db_session) -> None:
    org = _org(db_session)
    mgr = _user(db_session, org, perms=["task.view"])
    _overdue_process(db_session, org, manager=mgr.id)
    rows = svc.overdue_processes(db_session, mgr, org.id)
    assert len(rows) >= 1 and wf.is_overdue(rows[0])


# ---------------------------------------------------------------------------
# Эскалация — внутренние уведомления, идемпотентно
# ---------------------------------------------------------------------------

def test_escalate_creates_notification_once(db_session) -> None:
    org = _org(db_session)
    mgr = _user(db_session, org, perms=["management.view"])
    p = _overdue_process(db_session, org, manager=mgr.id)
    created = svc.escalate_overdue(db_session, mgr, org.id)
    assert created == 1
    n = db_session.query(Notification).filter(
        Notification.entity_type == "workflow_process",
        Notification.entity_id == p.id,
    ).first()
    assert n is not None and n.channel == "in_app" and n.recipient_user_id == mgr.id
    # повторный запуск не плодит дубликаты (есть непрочитанное)
    again = svc.escalate_overdue(db_session, mgr, org.id)
    assert again == 0


# ---------------------------------------------------------------------------
# ABAC: чужой проект не попадает в сводку
# ---------------------------------------------------------------------------

def test_overview_scoped_by_project_access(db_session) -> None:
    org = _org(db_session)
    project = Project(organization_id=org.id, name="Объект", status="active")
    db_session.add(project)
    db_session.flush()
    # процесс на проекте
    p = wf.create_process(db_session, org.id, process_kind="task", title="П",
                          author_user_id=uuid.uuid4(), risk_level="R1",
                          project_id=project.id)
    db_session.commit()
    # пользователь без членства в проекте не видит процесс проекта
    outsider = _user(db_session, org, perms=["management.view"], project=project,
                     member=False)
    ov = svc.manager_overview(db_session, outsider, org.id)
    assert ov["processes_total"] == 0


# ---------------------------------------------------------------------------
# API RBAC
# ---------------------------------------------------------------------------

def _client(db_engine, user) -> TestClient:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    token_store.clear()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def test_api_overview_requires_management_view(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org, perms=["task.view"])
    client = _client(db_engine, user)
    assert client.get("/manager/overview").status_code == 403


def test_api_overview_ok_and_escalate(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    mgr = _user(db_session, org, perms=["management.view", "task.view"], email="m@ex.com")
    _overdue_process(db_session, org, manager=mgr.id)
    client = _client(db_engine, mgr)
    ov = client.get("/manager/overview")
    assert ov.status_code == 200 and ov.json()["overdue"] >= 1
    esc = client.post("/manager/escalate-overdue")
    assert esc.status_code == 200 and esc.json()["notifications_created"] >= 1
