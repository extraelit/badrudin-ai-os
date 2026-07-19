"""API-тесты «Контроль исполнения поручений»: препятствия, вопросы/ответы,
эскалация, возврат на доработку, лента активности, уведомления, доска и
просрочка, RBAC/ABAC.

Переиспользует существующие сущности (tasks, task_updates, task_assignments,
notifications) без дубликатов. Данные обезличены.
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
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    Task,
    TaskAssignment,
    User,
    UserRole,
)

ALL = ["task.view", "task.execute", "task.assign", "task.approve"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Исполнитель Тест")
    db.add(emp)
    db.flush()
    user = User(email=f"u{uuid.uuid4().hex[:8]}@ex.com", password_hash=hash_password("x"),
                status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = Permission(code=pc)
        db.add(p)
        db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    if member:
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id, project_role="foreman"))
    db.commit()
    return org, project, emp, user


def _task(db, org, project, emp, *, status="in_progress", due_at=None, assign=True):
    t = Task(organization_id=org.id, project_id=project.id, title="Смонтировать узел",
             status=status, owner_employee_id=emp.id, due_at=due_at)
    db.add(t)
    db.flush()
    if assign:
        db.add(TaskAssignment(task_id=t.id, employee_id=emp.id, assignment_role="executor"))
    db.commit()
    return t


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


# ------------------------------- RBAC/ABAC ------------------------------- #


def test_board_requires_task_view(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session, perms=["project.view"])
    client = _client(db_engine, user)
    assert client.get("/task-control/board").status_code == 403


def test_blocker_requires_execute(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, perms=["task.view"])
    t = _task(db_session, org, project, emp)
    client = _client(db_engine, user)
    r = client.post(f"/task-control/tasks/{t.id}/blocker", json={"category": "materials", "message": "нет"})
    assert r.status_code == 403


def test_abac_denies_foreign_task(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session, member=False)
    t = _task(db_session, org, project, emp)
    client = _client(db_engine, user)
    assert client.get(f"/task-control/tasks/{t.id}/activity").status_code == 403


# --------------------------- Препятствия/вопросы ------------------------- #


def test_blocker_and_resolve(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    t = _task(db_session, org, project, emp)
    client = _client(db_engine, user)
    b = client.post(f"/task-control/tasks/{t.id}/blocker", json={"category": "equipment", "message": "сломан кран"})
    assert b.status_code == 200
    assert b.json()["status"] == "blocked"
    assert b.json()["blocked_reason"] == "сломан кран"
    # уведомление владельцу создано
    notes = client.get("/task-control/notifications").json()
    assert any(n["entity_id"] == str(t.id) for n in notes)
    r = client.post(f"/task-control/tasks/{t.id}/resolve-blocker", json={"message": "заменили"})
    assert r.json()["status"] == "in_progress"
    assert r.json()["blocked_reason"] is None


def test_question_and_answer(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    t = _task(db_session, org, project, emp)
    client = _client(db_engine, user)
    q = client.post(f"/task-control/tasks/{t.id}/question", json={"message": "какой профиль?"})
    assert q.json()["status"] == "waiting_for_information"
    a = client.post(f"/task-control/tasks/{t.id}/answer", json={"message": "40x40"})
    assert a.json()["status"] == "in_progress"


def test_invalid_transition_409(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    t = _task(db_session, org, project, emp, status="completed")
    client = _client(db_engine, user)
    # заявить препятствие у завершённой задачи нельзя
    r = client.post(f"/task-control/tasks/{t.id}/blocker", json={"category": "x", "message": "y"})
    assert r.status_code == 409


# --------------------------- Эскалация/возврат --------------------------- #


def test_escalate_overdue(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    t = _task(db_session, org, project, emp, due_at=datetime.now(UTC) - timedelta(days=2))
    client = _client(db_engine, user)
    board = client.get("/task-control/board").json()
    assert any(c["id"] == str(t.id) for c in board["overdue"])
    e = client.post(f"/task-control/tasks/{t.id}/escalate", json={"message": "срыв срока"})
    assert e.json()["escalation_level"] == 1
    assert e.json()["status"] == "overdue"
    # повторная эскалация повышает уровень
    e2 = client.post(f"/task-control/tasks/{t.id}/escalate", json={})
    assert e2.json()["escalation_level"] == 2


def test_return_for_revision(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    t = _task(db_session, org, project, emp, status="pending_review")
    client = _client(db_engine, user)
    r = client.post(f"/task-control/tasks/{t.id}/return", json={"message": "переделать шов"})
    assert r.json()["status"] == "returned_for_revision"


# --------------------------- Лента и уведомления ------------------------- #


def test_activity_feed_and_notifications(db_engine, db_session) -> None:
    org, project, emp, user = _make(db_session)
    t = _task(db_session, org, project, emp)
    client = _client(db_engine, user)
    client.post(f"/task-control/tasks/{t.id}/comment", json={"message": "начал"})
    client.post(f"/task-control/tasks/{t.id}/blocker", json={"category": "materials", "message": "ждём"})
    feed = client.get(f"/task-control/tasks/{t.id}/activity").json()
    types = [u["update_type"] for u in feed]
    assert "comment" in types and "blocker" in types
    # уведомления и отметка о прочтении
    notes = client.get("/task-control/notifications?unread_only=true").json()
    assert len(notes) >= 1
    nid = notes[0]["id"]
    read = client.post(f"/task-control/notifications/{nid}/read")
    assert read.json()["status"] == "read" and read.json()["read_at"] is not None
    assert len(client.get("/task-control/notifications?unread_only=true").json()) == len(notes) - 1
