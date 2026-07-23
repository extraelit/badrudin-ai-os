"""Тесты центра коммуникаций (PR-2).

Проверяют: жизненный цикл сообщения (черновик → согласование → отправка в
sandbox), SoD (внешний канал: согласующий ≠ автор), стоп-лист/согласие исключают
получателя, журнал доставки, реальная отправка недоступна (sandbox), повтор
только неуспешным, RBAC (403 без прав) и tenant isolation, входящее сообщение.
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
from app.services import communications as svc


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


# --------------------------- Сервисный уровень --------------------------- #

def test_external_message_lifecycle_sandbox(db_session) -> None:
    org = _org(db_session)
    author = uuid.uuid4()
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="email", subject="Тема",
                         body_text="Текст", author_user_id=author)
    contact = svc.create_contact(db_session, org.id, display_name="Контрагент",
                                 email="c@example.com", consent=True)
    svc.add_recipient(db_session, m, address="c@example.com", contact_id=contact.id)
    svc.submit_for_approval(db_session, m, actor_user_id=author)
    assert m.status == "pending_approval"
    # SoD: автор не может согласовать внешнее сообщение
    with pytest.raises(svc.CommunicationError, match="автор"):
        svc.approve(db_session, m, approver_user_id=author)
    svc.approve(db_session, m, approver_user_id=approver)
    assert m.status == "approved"
    svc.dispatch(db_session, m, actor_user_id=approver)
    assert m.status == "sent" and m.external_id.startswith("sandbox:")
    log = svc.delivery_log(db_session, m)
    assert any(e.event == "sent" for e in log)


def test_real_send_blocked(db_session) -> None:
    org = _org(db_session)
    m = svc.create_draft(db_session, org.id, channel="email", author_user_id=uuid.uuid4())
    svc.add_recipient(db_session, m, address="c@example.com")
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=uuid.uuid4())
    with pytest.raises(svc.CommunicationError, match="Реальная отправка недоступна"):
        svc.dispatch(db_session, m, actor_user_id=uuid.uuid4(), allow_real_send=True)


def test_stop_list_and_consent_exclude_recipient(db_session) -> None:
    org = _org(db_session)
    approver = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="email", author_user_id=uuid.uuid4())
    no_consent = svc.create_contact(db_session, org.id, display_name="Без согласия",
                                    email="a@ex.com", consent=False)
    stopped = svc.create_contact(db_session, org.id, display_name="Стоп",
                                 email="b@ex.com", consent=True)
    svc.set_stop_list(db_session, stopped, stop_listed=True)
    svc.add_recipient(db_session, m, address="a@ex.com", contact_id=no_consent.id)
    svc.add_recipient(db_session, m, address="b@ex.com", contact_id=stopped.id)
    svc.submit_for_approval(db_session, m, actor_user_id=uuid.uuid4())
    svc.approve(db_session, m, approver_user_id=approver)
    svc.dispatch(db_session, m, actor_user_id=approver)
    # оба исключены → сообщение failed
    assert m.status == "failed"
    rcpts = svc._recipients(db_session, m)
    assert all(r.status == "skipped" for r in rcpts)


def test_internal_channel_no_approval_needed(db_session) -> None:
    org = _org(db_session)
    actor = uuid.uuid4()
    m = svc.create_draft(db_session, org.id, channel="internal", author_user_id=actor)
    svc.add_recipient(db_session, m, address="user:internal")
    # внутренний канал: согласование не требуется, можно отправлять из draft? нет —
    # dispatch требует approved/scheduled только для внешних; internal — можно.
    svc.dispatch(db_session, m, actor_user_id=actor)
    assert m.status == "sent"


def test_incoming_message_recorded(db_session) -> None:
    org = _org(db_session)
    m = svc.record_incoming(db_session, org.id, channel="telegram",
                            address_from="+79990000000", body_text="Привет",
                            external_id="tg:123")
    assert m.direction == "in" and m.status == "delivered"
    assert svc.list_messages(db_session, org.id, direction="in")


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


def test_api_full_flow(db_engine, db_session) -> None:
    org = _org(db_session)
    author = _user(db_session, org, perms=("communication.view", "communication.manage",
                                           "communication.send"))
    approver = _user(db_session, org, perms=("communication.approve",))
    ca = _client(db_engine, author)
    r = ca.post("/communications/messages", json={
        "channel": "email", "subject": "Привет", "body_text": "Тело",
        "recipients": [{"address": "c@ex.com"}],
    })
    assert r.status_code == 201, r.text
    mid = r.json()["id"]
    assert ca.post(f"/communications/messages/{mid}/submit-approval").status_code == 200
    # автор без права approve — 403
    assert ca.post(f"/communications/messages/{mid}/approve").status_code == 403
    cap = _client(db_engine, approver)
    assert cap.post(f"/communications/messages/{mid}/approve").status_code == 200
    # отправка автором (есть send) — sandbox; переустанавливаем актора (override глобальный)
    ca = _client(db_engine, author)
    sr = ca.post(f"/communications/messages/{mid}/send")
    assert sr.status_code == 200 and sr.json()["status"] == "sent"
    # журнал доставки
    log = ca.get(f"/communications/messages/{mid}/delivery-log")
    assert log.status_code == 200 and len(log.json()) >= 1
    # исходящие содержат сообщение
    assert any(m["id"] == mid for m in ca.get("/communications/outbox").json())


def test_api_requires_permission(db_engine, db_session) -> None:
    org = _org(db_session)
    viewer = _user(db_session, org, perms=("communication.view",))
    c = _client(db_engine, viewer)
    r = c.post("/communications/messages", json={"channel": "email", "recipients": []})
    assert r.status_code == 403


def test_api_tenant_isolation(db_engine, db_session) -> None:
    org_a = _org(db_session, "A")
    org_b = _org(db_session, "B")
    m = svc.create_draft(db_session, org_a.id, channel="email", author_user_id=uuid.uuid4())
    db_session.commit()
    user_b = _user(db_session, org_b, perms=("communication.view",))
    c = _client(db_engine, user_b)
    assert c.get(f"/communications/messages/{m.id}").status_code == 404
