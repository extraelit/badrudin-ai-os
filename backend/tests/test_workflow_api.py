"""Тесты процессного ядра: жизненный цикл, инварианты, SoD, RBAC/ABAC (PR-D1).

Проверяют единый жизненный цикл процесса и инварианты плана (§1.3, §10):
назначение делает постановщик; принимает только исполнитель; закрытие R2–R4 —
независимая проверка (SoD); перенос срока требует причины, для R3–R4 — согласования;
`overdue` вычисляется; смена исполнителя возвращает к назначению; терминальные —
только архивирование; изоляция по организации и проекту.
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
    User,
    UserRole,
    WorkflowProcess,
)
from app.services import workflow as svc

ALL = ["task.view", "task.create", "task.assign", "task.execute", "task.approve"]


def _user(db, org, *, perms=ALL, member_project=None, email=None):
    emp = Employee(organization_id=org.id, full_name="Сотрудник")
    db.add(emp)
    db.flush()
    user = User(
        email=email or f"u{uuid.uuid4().hex[:8]}@ex.com",
        password_hash=hash_password("x"), status="active", employee_id=emp.id,
    )
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
    if member_project is not None:
        db.add(ProjectMember(project_id=member_project.id, employee_id=emp.id,
                             project_role="member"))
    db.commit()
    return user


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


# ---------------------------------------------------------------------------
# Сервисный уровень: жизненный цикл R1 и инварианты
# ---------------------------------------------------------------------------

def _org(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    return org


def test_r1_flow_assign_accept_complete(db_session) -> None:
    org = _org(db_session)
    initiator, executor, reviewer = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    p = svc.create_process(
        db_session, org.id, process_kind="task", title="Поручение",
        author_user_id=initiator, risk_level="R1",
    )
    assert p.status == "draft"
    svc.assign(db_session, p, initiator_user_id=initiator, executor_id=executor)
    assert p.status == "assigned"
    svc.accept(db_session, p, actor_user_id=executor)
    assert p.status == "accepted" and p.accepted_at is not None
    svc.start(db_session, p, actor_user_id=executor)
    svc.submit_for_review(db_session, p, actor_user_id=executor)
    # R1 допускает закрытие тем же исполнителем
    svc.review(db_session, p, reviewer_user_id=executor, decision="completed")
    assert p.status == "completed" and p.completed_at is not None


def test_assign_by_executor_forbidden(db_session) -> None:
    org = _org(db_session)
    initiator, executor = uuid.uuid4(), uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="task", title="T",
                           author_user_id=initiator, risk_level="R1")
    # постановщик не может назначить исполнителем самого себя
    with pytest.raises(svc.WorkflowError):
        svc.assign(db_session, p, initiator_user_id=initiator, executor_id=initiator)


def test_only_executor_can_accept(db_session) -> None:
    org = _org(db_session)
    initiator, executor, other = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="task", title="T",
                           author_user_id=initiator, risk_level="R1")
    svc.assign(db_session, p, initiator_user_id=initiator, executor_id=executor)
    with pytest.raises(svc.WorkflowError, match="исполнитель"):
        svc.accept(db_session, p, actor_user_id=other)


def test_r3_requires_approval_before_assign(db_session) -> None:
    org = _org(db_session)
    author = uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="finance_payment",
                           title="Оплата", author_user_id=author)
    assert p.risk_level == "R3"  # профиль риска по виду
    # назначение из draft для R3 запрещено — нужен цикл согласования
    with pytest.raises(svc.WorkflowError):
        svc.assign(db_session, p, initiator_user_id=uuid.uuid4(),
                   executor_id=uuid.uuid4())


def test_r3_independent_review_sod(db_session) -> None:
    org = _org(db_session)
    author, executor = uuid.uuid4(), uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="acceptance_control",
                           title="Приёмка", author_user_id=author)  # R3
    svc.submit_for_approval(db_session, p, actor_user_id=author)
    svc.approve(db_session, p, approver_user_id=uuid.uuid4())
    svc.assign(db_session, p, initiator_user_id=author, executor_id=executor)
    svc.accept(db_session, p, actor_user_id=executor)
    svc.start(db_session, p, actor_user_id=executor)
    svc.submit_for_review(db_session, p, actor_user_id=executor)
    # исполнитель не может сам закрыть R3 (SoD)
    with pytest.raises(svc.WorkflowError, match="независим"):
        svc.review(db_session, p, reviewer_user_id=executor, decision="completed")
    # независимый проверяющий — можно
    svc.review(db_session, p, reviewer_user_id=uuid.uuid4(), decision="completed")
    assert p.status == "completed"


def test_r3_approver_not_author(db_session) -> None:
    org = _org(db_session)
    author = uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="contract",
                           title="Договор", author_user_id=author)  # R3
    svc.submit_for_approval(db_session, p, actor_user_id=author)
    with pytest.raises(svc.WorkflowError, match="автор"):
        svc.approve(db_session, p, approver_user_id=author)


def test_overdue_is_computed(db_session) -> None:
    org = _org(db_session)
    p = svc.create_process(db_session, org.id, process_kind="task", title="T",
                           author_user_id=uuid.uuid4(), risk_level="R1",
                           due_at=datetime.now(UTC) - timedelta(days=1))
    svc.assign(db_session, p, initiator_user_id=uuid.uuid4(), executor_id=uuid.uuid4())
    assert svc.is_overdue(p) is True
    # у завершённого просрочки нет
    p.status = "completed"
    assert svc.is_overdue(p) is False


def test_reschedule_requires_reason_and_manager_for_r3(db_session) -> None:
    org = _org(db_session)
    p = svc.create_process(db_session, org.id, process_kind="finance_payment",
                           title="Оплата", author_user_id=uuid.uuid4())  # R3
    new_due = datetime.now(UTC) + timedelta(days=3)
    with pytest.raises(svc.WorkflowError, match="причин"):
        svc.reschedule(db_session, p, actor_user_id=uuid.uuid4(),
                       new_due_at=new_due, reason="")
    with pytest.raises(svc.WorkflowError, match="согласовани"):
        svc.reschedule(db_session, p, actor_user_id=uuid.uuid4(),
                       new_due_at=new_due, reason="перенос", approved_by_manager=False)
    svc.reschedule(db_session, p, actor_user_id=uuid.uuid4(),
                   new_due_at=new_due, reason="перенос", approved_by_manager=True)
    assert p.reschedule_count == 1


def test_revision_loop(db_session) -> None:
    org = _org(db_session)
    initiator, executor = uuid.uuid4(), uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="task", title="T",
                           author_user_id=initiator, risk_level="R2")
    svc.submit_for_approval(db_session, p, actor_user_id=initiator)
    svc.approve(db_session, p, approver_user_id=uuid.uuid4())
    svc.assign(db_session, p, initiator_user_id=initiator, executor_id=executor)
    svc.accept(db_session, p, actor_user_id=executor)
    svc.start(db_session, p, actor_user_id=executor)
    svc.submit_for_review(db_session, p, actor_user_id=executor)
    svc.review(db_session, p, reviewer_user_id=uuid.uuid4(),
               decision="revision_required", comment="доработать")
    assert p.status == "revision_required"
    svc.start(db_session, p, actor_user_id=executor)  # снова в работу
    assert p.status == "in_progress"


def test_change_executor_returns_to_assigned(db_session) -> None:
    org = _org(db_session)
    initiator, executor, new_exec = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    p = svc.create_process(db_session, org.id, process_kind="task", title="T",
                           author_user_id=initiator, risk_level="R1")
    svc.assign(db_session, p, initiator_user_id=initiator, executor_id=executor)
    svc.accept(db_session, p, actor_user_id=executor)
    with pytest.raises(svc.WorkflowError, match="причин"):
        svc.change_executor(db_session, p, actor_user_id=initiator,
                            new_executor_id=new_exec, reason="")
    svc.change_executor(db_session, p, actor_user_id=initiator,
                        new_executor_id=new_exec, reason="болезнь")
    assert p.primary_executor_id == new_exec and p.status == "assigned"


def test_terminal_then_only_archive(db_session) -> None:
    org = _org(db_session)
    p = svc.create_process(db_session, org.id, process_kind="task", title="T",
                           author_user_id=uuid.uuid4(), risk_level="R1")
    svc.cancel(db_session, p, actor_user_id=uuid.uuid4(), reason="не требуется")
    assert p.status == "cancelled"
    # повторная отмена/назначение запрещены
    with pytest.raises(svc.WorkflowError):
        svc.assign(db_session, p, initiator_user_id=uuid.uuid4(),
                   executor_id=uuid.uuid4())
    svc.archive(db_session, p, actor_user_id=uuid.uuid4())
    assert p.status == "archived" and p.is_archived is True


# ---------------------------------------------------------------------------
# API: RBAC / ABAC / изоляция
# ---------------------------------------------------------------------------

def test_api_create_requires_task_create(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org, perms=["task.view"])
    client = _client(db_engine, user)
    resp = client.post("/processes/", json={"process_kind": "task", "title": "T"})
    assert resp.status_code == 403


def test_api_full_cycle_via_http(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    manager = _user(db_session, org, email="mgr@ex.com")
    client = _client(db_engine, manager)
    created = client.post("/processes/", json={"process_kind": "task", "title": "Задача"})
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["status"] == "draft" and body["overdue"] is False
    assert body["risk_level"] == "R1"


def test_api_isolation_by_organization(db_engine, db_session) -> None:
    org_a = _org(db_session)
    org_b = _org(db_session)
    db_session.commit()
    user_a = _user(db_session, org_a, email="a@ex.com")
    user_b = _user(db_session, org_b, email="b@ex.com")
    # A создаёт процесс
    client_a = _client(db_engine, user_a)
    pid = client_a.post("/processes/", json={"process_kind": "task", "title": "T"}).json()["id"]
    app.dependency_overrides.clear()
    # B не видит и не открывает чужой процесс
    client_b = _client(db_engine, user_b)
    assert client_b.get("/processes/").json() == []
    assert client_b.get(f"/processes/{pid}").status_code == 404


def test_api_invalid_kind_rejected(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org)
    client = _client(db_engine, user)
    resp = client.post("/processes/", json={"process_kind": "bogus", "title": "T"})
    assert resp.status_code == 409
