"""Тесты рассылок (PR-7).

Проверяют: жизненный цикл (черновик → цели → согласование → отправка sandbox),
SoD (внешний канал: согласующий ≠ автор), тестовую отправку, отчёт о доставке,
исключение по стоп-листу/согласию/отписке, анти-спам (без дублей), повтор только
неуспешным, RBAC (403 без прав) и tenant isolation.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    CommunicationMessage,
    Employee,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import broadcasts as bsvc
from app.services import communications as comm


def _org(db, name="ТЕСТ") -> Organization:
    org = Organization(legal_name=name)
    db.add(org)
    db.flush()
    return org


def _user(db, org, *, perms=(), email=None) -> User:
    emp = Employee(organization_id=org.id, full_name="Сотрудник")
    db.add(emp)
    db.flush()
    user = User(email=email or f"u{uuid.uuid4().hex[:8]}@ex.com",
                password_hash=hash_password("x"), status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    if perms:
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
    db.commit()
    return user


def _contact(db, org, **kw):
    return comm.create_contact(db, org.id, display_name=kw.pop("name", "Контакт"), **kw)


# --------------------------- Сервисный уровень --------------------------- #

def test_broadcast_lifecycle_sandbox(db_session) -> None:
    org = _org(db_session)
    author, approver = uuid.uuid4(), uuid.uuid4()
    c1 = _contact(db_session, org, email="a@ex.com", consent=True)
    c2 = _contact(db_session, org, email="b@ex.com", consent=True)
    b = bsvc.create_broadcast(db_session, org.id, channel="email", title="Новости",
                              subject="Тема", body_text="Текст", author_user_id=author)
    added = bsvc.add_targets(db_session, b, contact_ids=[c1.id, c2.id])
    assert added == 2 and b.total_count == 2
    bsvc.submit_for_approval(db_session, b, actor_user_id=author)
    with pytest.raises(bsvc.BroadcastError, match="автор"):
        bsvc.approve(db_session, b, approver_user_id=author)
    bsvc.approve(db_session, b, approver_user_id=approver)
    bsvc.dispatch_broadcast(db_session, b, actor_user_id=approver)
    assert b.status == "sent" and b.sent_count == 2
    report = bsvc.delivery_report(db_session, b)
    assert report["by_status"].get("sent") == 2


def test_targets_dedup_and_exclusions(db_session) -> None:
    org = _org(db_session)
    ok = _contact(db_session, org, email="ok@ex.com", consent=True)
    noconsent = _contact(db_session, org, email="n@ex.com", consent=False)
    stopped = _contact(db_session, org, email="s@ex.com", consent=True)
    comm.set_stop_list(db_session, stopped, stop_listed=True)
    unsub = _contact(db_session, org, email="u@ex.com", consent=True)
    comm.set_unsubscribed(db_session, unsub, unsubscribed=True)
    approver = uuid.uuid4()
    b = bsvc.create_broadcast(db_session, org.id, channel="email", title="T",
                              body_text="x", author_user_id=uuid.uuid4())
    # добавляем ok дважды (анти-спам) + исключаемых
    bsvc.add_targets(db_session, b, contact_ids=[ok.id, ok.id, noconsent.id, stopped.id, unsub.id])
    assert b.total_count == 4  # ok(1) + noconsent + stopped + unsub (без дубля ok)
    bsvc.submit_for_approval(db_session, b, actor_user_id=uuid.uuid4())
    bsvc.approve(db_session, b, approver_user_id=approver)
    bsvc.dispatch_broadcast(db_session, b, actor_user_id=approver)
    # доставлен только ok; остальные исключены
    assert b.sent_count == 1 and b.failed_count == 3


def test_test_send_sandbox(db_session) -> None:
    org = _org(db_session)
    b = bsvc.create_broadcast(db_session, org.id, channel="email", title="T",
                              subject="Привет", body_text="тело", author_user_id=uuid.uuid4())
    msg = bsvc.test_send(db_session, b, test_address="test@ex.com", actor_user_id=uuid.uuid4())
    assert msg.status == "sent" and msg.external_id.startswith("sandbox:")
    assert b.test_recipient == "test@ex.com"


def test_retry_only_failed(db_session) -> None:
    org = _org(db_session)
    approver = uuid.uuid4()
    ok = _contact(db_session, org, email="ok@ex.com", consent=True)
    stopped = _contact(db_session, org, email="s@ex.com", consent=True)
    b = bsvc.create_broadcast(db_session, org.id, channel="email", title="T",
                              body_text="x", author_user_id=uuid.uuid4())
    bsvc.add_targets(db_session, b, contact_ids=[ok.id, stopped.id])
    bsvc.submit_for_approval(db_session, b, actor_user_id=uuid.uuid4())
    bsvc.approve(db_session, b, approver_user_id=approver)
    comm.set_stop_list(db_session, stopped, stop_listed=True)
    bsvc.dispatch_broadcast(db_session, b, actor_user_id=approver)
    assert b.sent_count == 1 and b.failed_count == 1
    # снимаем стоп-лист и повторяем — теперь второй тоже уходит
    comm.set_stop_list(db_session, stopped, stop_listed=False)
    bsvc.retry_failed(db_session, b, actor_user_id=approver)
    report = bsvc.delivery_report(db_session, b)
    assert report["by_status"].get("sent") == 2


# ------------------------------- API/RBAC -------------------------------- #

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


def test_api_broadcast_flow(db_engine, db_session) -> None:
    org = _org(db_session)
    author = _user(db_session, org, perms=("communication.view", "communication.manage",
                                           "communication.send"))
    approver = _user(db_session, org, perms=("communication.approve",))
    c = _contact(db_session, org, email="x@ex.com", consent=True)
    db_session.commit()
    ca = _client(db_engine, author)
    r = ca.post("/communications/broadcasts", json={
        "channel": "email", "title": "Рассылка", "subject": "S", "body_text": "B",
        "contact_ids": [str(c.id)],
    })
    assert r.status_code == 201, r.text
    bid = r.json()["id"]
    assert r.json()["total_count"] == 1
    assert ca.post(f"/communications/broadcasts/{bid}/submit-approval").status_code == 200
    assert ca.post(f"/communications/broadcasts/{bid}/approve").status_code == 403  # автор
    cap = _client(db_engine, approver)
    assert cap.post(f"/communications/broadcasts/{bid}/approve").status_code == 200
    ca = _client(db_engine, author)
    sr = ca.post(f"/communications/broadcasts/{bid}/send")
    assert sr.status_code == 200 and sr.json()["sent_count"] == 1
    rep = ca.get(f"/communications/broadcasts/{bid}/report")
    assert rep.status_code == 200 and rep.json()["sent"] == 1


def test_api_requires_permission(db_engine, db_session) -> None:
    org = _org(db_session)
    viewer = _user(db_session, org, perms=("communication.view",))
    c = _client(db_engine, viewer)
    r = c.post("/communications/broadcasts", json={"channel": "email", "title": "T"})
    assert r.status_code == 403


def test_api_tenant_isolation(db_engine, db_session) -> None:
    org_a, org_b = _org(db_session, "A"), _org(db_session, "B")
    b = bsvc.create_broadcast(db_session, org_a.id, channel="email", title="T",
                              author_user_id=uuid.uuid4())
    db_session.commit()
    user_b = _user(db_session, org_b, perms=("communication.view",))
    c = _client(db_engine, user_b)
    assert c.get(f"/communications/broadcasts/{b.id}").status_code == 404
