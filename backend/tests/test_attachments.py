"""Тесты универсальных вложений (PR-1).

Проверяют: реальное сохранение байтов через локальный адаптер + метаданные и
SHA-256; список/скачивание; версии; архивирование вместо удаления; запрет
архивирования утверждённого (заблокированного) файла; учёт вложений Evidence
Gate; RBAC (без права — 403) и tenant isolation; валидацию типа/размера.
"""

from __future__ import annotations

import base64
import uuid
from collections.abc import Iterator
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    Attachment,
    Employee,
    File,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import attachments as att
from app.services import evidence as ev
from app.services import workflow as wf
from app.services.storage import UploadValidationError
from app.services.storage_adapter import LocalStorageAdapter, get_storage_adapter

PNG = b"\x89PNG\r\n\x1a\n" + b"0" * 32


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

def test_local_adapter_roundtrip(tmp_path) -> None:
    a = LocalStorageAdapter(str(tmp_path))
    a.put("files/x.bin", b"hello", "application/octet-stream")
    assert a.exists("files/x.bin")
    assert a.open("files/x.bin") == b"hello"
    assert a.presigned_url("files/x.bin") is None


def test_attach_stores_bytes_and_metadata(db_session) -> None:
    org = _org(db_session)
    uid = uuid.uuid4()
    a = att.attach(
        db_session, organization_id=org.id, entity_type="workflow_process",
        entity_id=uuid.uuid4(), original_name="фото.png", content=PNG,
        mime_type="image/png", attachment_type="photo", uploaded_by=uid,
    )
    file = db_session.get(File, a.file_id)
    assert file.size_bytes == len(PNG)
    assert file.checksum_sha256 and len(file.checksum_sha256) == 64
    # байты реально в хранилище
    data, url, _ = att.download(db_session, a)
    assert data == PNG and url is None


def test_reject_bad_entity_and_mime(db_session) -> None:
    org = _org(db_session)
    with pytest.raises(att.AttachmentError):
        att.attach(db_session, organization_id=org.id, entity_type="unknown",
                   entity_id=uuid.uuid4(), original_name="a.png", content=PNG,
                   mime_type="image/png")
    with pytest.raises(UploadValidationError):
        att.attach(db_session, organization_id=org.id, entity_type="task",
                   entity_id=uuid.uuid4(), original_name="a.exe", content=b"x",
                   mime_type="application/x-msdownload")


def test_versioning_supersedes_previous(db_session) -> None:
    org = _org(db_session)
    eid = uuid.uuid4()
    v1 = att.attach(db_session, organization_id=org.id, entity_type="document",
                    entity_id=eid, original_name="d.pdf", content=b"%PDF-1",
                    mime_type="application/pdf")
    v2 = att.attach(db_session, organization_id=org.id, entity_type="document",
                    entity_id=eid, original_name="d2.pdf", content=b"%PDF-2",
                    mime_type="application/pdf", replaces_id=v1.id)
    db_session.refresh(v1)
    assert v2.version == 2 and v2.replaces_id == v1.id
    assert v1.is_current is False
    current = att.list_for(db_session, "document", eid)
    assert [x.id for x in current] == [v2.id]


def test_archive_instead_of_delete(db_session) -> None:
    org = _org(db_session)
    eid = uuid.uuid4()
    a = att.attach(db_session, organization_id=org.id, entity_type="task",
                   entity_id=eid, original_name="a.pdf", content=b"%PDF",
                   mime_type="application/pdf")
    att.archive(db_session, a, actor_user_id=uuid.uuid4(), reason="ошибочный файл")
    assert a.is_archived is True
    assert att.list_for(db_session, "task", eid) == []
    assert len(att.list_for(db_session, "task", eid, include_archived=True)) == 1


def test_cannot_archive_locked_file(db_session) -> None:
    org = _org(db_session)
    a = att.attach(db_session, organization_id=org.id, entity_type="document",
                   entity_id=uuid.uuid4(), original_name="a.pdf", content=b"%PDF",
                   mime_type="application/pdf")
    file = db_session.get(File, a.file_id)
    file.locked_at = datetime.now(timezone.utc)
    db_session.flush()
    with pytest.raises(att.AttachmentError, match="утверждённого"):
        att.archive(db_session, a, actor_user_id=uuid.uuid4(), reason="x")


def test_attachment_counts_toward_evidence_gate(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo")
    p = wf.create_process(db_session, org.id, process_kind="daily_report",
                          title="Отчёт", author_user_id=uuid.uuid4(), risk_level="R1")
    wf.assign(db_session, p, initiator_user_id=uuid.uuid4(), executor_id=executor)
    wf.accept(db_session, p, actor_user_id=executor)
    wf.start(db_session, p, actor_user_id=executor)
    # без вложения — гейт закрыт
    assert ev.missing_required(db_session, p) == ["photo"]
    att.attach(db_session, organization_id=org.id, entity_type="workflow_process",
               entity_id=p.id, original_name="ф.png", content=PNG,
               mime_type="image/png", attachment_type="photo")
    # реальное вложение открывает гейт
    assert ev.missing_required(db_session, p) == []
    wf.submit_for_review(db_session, p, actor_user_id=executor)
    assert p.status == "submitted_for_review"


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
    c = TestClient(app)
    return c


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _b64(data: bytes) -> str:
    return base64.b64encode(data).decode()


def test_api_attach_and_list_and_download(db_engine, db_session) -> None:
    org = _org(db_session)
    user = _user(db_session, org, perms=("attachment.manage", "attachment.view"))
    client = _client(db_engine, user)
    eid = str(uuid.uuid4())
    r = client.post("/attachments/", json={
        "entity_type": "task", "entity_id": eid, "original_name": "ф.png",
        "content_base64": _b64(PNG), "mime_type": "image/png",
        "attachment_type": "photo", "description": "на объекте",
    })
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    assert r.json()["checksum_sha256"]
    lst = client.get("/attachments/", params={"entity_type": "task", "entity_id": eid})
    assert lst.status_code == 200 and len(lst.json()) == 1
    dl = client.get(f"/attachments/{aid}/download")
    assert dl.status_code == 200 and dl.content == PNG


def test_api_requires_permission(db_engine, db_session) -> None:
    org = _org(db_session)
    user = _user(db_session, org, perms=("attachment.view",))  # нет manage
    client = _client(db_engine, user)
    r = client.post("/attachments/", json={
        "entity_type": "task", "entity_id": str(uuid.uuid4()),
        "original_name": "a.pdf", "content_base64": _b64(b"%PDF"),
        "mime_type": "application/pdf",
    })
    assert r.status_code == 403


def test_api_tenant_isolation(db_engine, db_session) -> None:
    org_a = _org(db_session, "A")
    org_b = _org(db_session, "B")
    # вложение принадлежит org_a
    a = att.attach(db_session, organization_id=org_a.id, entity_type="task",
                   entity_id=uuid.uuid4(), original_name="a.pdf", content=b"%PDF",
                   mime_type="application/pdf")
    db_session.commit()
    user_b = _user(db_session, org_b, perms=("attachment.view",))
    client = _client(db_engine, user_b)
    r = client.get(f"/attachments/{a.id}/download")
    assert r.status_code == 404
