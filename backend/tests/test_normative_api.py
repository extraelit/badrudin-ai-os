"""Тесты нормативного реестра и профиля проекта (этап 1).

Проверяют инварианты плана: новая запись реестра создаётся со статусом
`needs_review` (система не подтверждает актуальность сама); перевод статуса —
действие уполномоченного лица с фиксацией в аудите; при изменении нормы прежние
записи не переписываются; профиль проекта активирует человек. Плюс RBAC
(view/manage/confirm), ABAC (доступ к проекту) и изоляция по организации.
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
    AuditEvent,
    Employee,
    NormativeDocument,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import normative as svc

ALL = ["normative.view", "normative.manage", "normative.confirm"]


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    emp = Employee(organization_id=org.id, full_name="Инженер Тест")
    db.add(emp)
    db.flush()
    user = User(
        email=f"u{uuid.uuid4().hex[:8]}@ex.com",
        password_hash=hash_password("x"),
        status="active",
        employee_id=emp.id,
    )
    db.add(user)
    db.flush()
    role = Role(code=f"r{uuid.uuid4().hex[:6]}", name="r")
    db.add(role)
    db.flush()
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        # права глобально уникальны по коду — переиспользуем существующее
        p = db.query(Permission).filter(Permission.code == pc).first()
        if p is None:
            p = Permission(code=pc)
            db.add(p)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    if member:
        db.add(
            ProjectMember(project_id=project.id, employee_id=emp.id, project_role="pm")
        )
    db.commit()
    return org, project, emp, user


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


def _create_doc(client, **kw):
    body = {"full_title": "СП 48.13330.2019", "doc_kind": "sp", "number": "48.13330.2019"}
    body.update(kw)
    return client.post("/normative/documents", json=body)


# ---------------------------------------------------------------------------
# Инвариант: новая запись — needs_review; система не подтверждает сама
# ---------------------------------------------------------------------------

def test_service_forces_needs_review_status(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    doc = svc.create_document(
        db_session, org.id, full_title="СП 70.13330.2012", doc_kind="sp"
    )
    assert doc.status == "needs_review"


def test_create_via_api_is_needs_review(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    resp = _create_doc(client)
    assert resp.status_code == 201, resp.text
    assert resp.json()["status"] == "needs_review"


def test_invalid_doc_kind_rejected(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    resp = _create_doc(client, doc_kind="not_a_kind")
    assert resp.status_code == 409


# ---------------------------------------------------------------------------
# Подтверждение статуса — действие уполномоченного лица + аудит
# ---------------------------------------------------------------------------

def test_confirm_in_force_sets_reviewer_and_audit(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session)
    client = _client(db_engine, user)
    doc_id = _create_doc(client).json()["id"]

    resp = client.post(
        f"/normative/documents/{doc_id}/confirm",
        json={"status": "in_force", "comment": "проверено главным инженером"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "in_force"
    assert body["last_checked_at"] is not None
    assert body["reviewer_comment"] == "проверено главным инженером"

    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "normative.document.confirm_status")
        .first()
    )
    assert event is not None
    assert event.new_values_json == {"status": "in_force"}


def test_confirm_rejects_needs_review_target(db_session) -> None:
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    doc = svc.create_document(db_session, org.id, full_title="СП", doc_kind="sp")
    with pytest.raises(svc.NormativeError):
        svc.confirm_status(
            db_session, doc.id, "needs_review", reviewer_user_id=uuid.uuid4()
        )


def test_superseding_keeps_old_record(db_session) -> None:
    """Изменение нормы не переписывает прежнюю запись (историческая привязка)."""
    org = Organization(legal_name="ТЕСТ")
    db_session.add(org)
    db_session.flush()
    old = svc.create_document(
        db_session, org.id, full_title="СП ред.2019", doc_kind="sp", edition="2019"
    )
    svc.confirm_status(db_session, old.id, "in_force", reviewer_user_id=uuid.uuid4())
    # выходит новая редакция — отдельная запись; старую переводим в superseded
    new = svc.create_document(
        db_session, org.id, full_title="СП ред.2023", doc_kind="sp", edition="2023"
    )
    svc.confirm_status(db_session, old.id, "superseded", reviewer_user_id=uuid.uuid4())

    db_session.refresh(old)
    assert old.status == "superseded" and old.edition == "2019"  # запись сохранена
    assert db_session.get(NormativeDocument, new.id) is not None


# ---------------------------------------------------------------------------
# RBAC / ABAC / изоляция по организации
# ---------------------------------------------------------------------------

def test_create_requires_manage(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session, perms=["normative.view"])
    client = _client(db_engine, user)
    assert _create_doc(client).status_code == 403


def test_confirm_requires_confirm_permission(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session, perms=["normative.view", "normative.manage"])
    client = _client(db_engine, user)
    doc_id = _create_doc(client).json()["id"]
    resp = client.post(
        f"/normative/documents/{doc_id}/confirm", json={"status": "in_force"}
    )
    assert resp.status_code == 403


def test_list_requires_view(db_engine, db_session) -> None:
    _, _, _, user = _make(db_session, perms=[])
    client = _client(db_engine, user)
    assert client.get("/normative/documents").status_code == 403


def test_document_isolated_by_organization(db_engine, db_session) -> None:
    # документ создаёт пользователь одной организации
    _, _, _, user_a = _make(db_session)
    client_a = _client(db_engine, user_a)
    doc_id = _create_doc(client_a).json()["id"]
    app.dependency_overrides.clear()

    # пользователь другой организации не видит и не подтверждает чужой документ
    _, _, _, user_b = _make(db_session)
    client_b = _client(db_engine, user_b)
    assert client_b.get("/normative/documents").json() == []
    resp = client_b.post(
        f"/normative/documents/{doc_id}/confirm", json={"status": "in_force"}
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Профиль проекта: позиции + активация человеком + ABAC
# ---------------------------------------------------------------------------

def test_project_profile_add_item_and_activate(db_engine, db_session) -> None:
    _, project, _, user = _make(db_session)
    client = _client(db_engine, user)
    doc_id = _create_doc(client).json()["id"]

    # добавляем норматив в профиль проекта
    add = client.post(
        f"/normative/projects/{project.id}/profile/items",
        json={"normative_document_id": doc_id, "mandatory": True, "applicable_edition": "2019"},
    )
    assert add.status_code == 201, add.text

    # активируем профиль (нормативы применяет человек, не система)
    act = client.post(f"/normative/projects/{project.id}/profile/activate")
    assert act.status_code == 200, act.text
    body = act.json()
    assert body["status"] == "active"
    assert body["approved_by"] is not None
    assert len(body["items"]) == 1
    assert body["items"][0]["applicable_edition"] == "2019"


def test_profile_denied_without_project_access(db_engine, db_session) -> None:
    _, project, _, user = _make(db_session, member=False)
    client = _client(db_engine, user)
    assert client.get(f"/normative/projects/{project.id}/profile").status_code == 403
