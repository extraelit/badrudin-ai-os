"""API-тесты «Мобильный ежедневный отчёт прораба»: сквозной цикл (составление →
работы/численность/техника/проблемы/фото → отправка → проверка руководителем),
доказательства через MinIO-метаданные, связь с задачами, RBAC/ABAC и аудит.

Переиспользует существующие сущности (daily_reports, sub-таблицы, files,
approvals) без дубликатов. Данные обезличены; загрузка файла — метаданные
(register_file не обращается к MinIO), тип валидируется по конфигурации.
"""

from __future__ import annotations

import base64
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
    Employee,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    Site,
    Task,
    User,
    UserRole,
)

VIEW = ["daily_report.view"]
FOREMAN = ["daily_report.view", "daily_report.manage"]
ALL = ["daily_report.view", "daily_report.manage", "daily_report.approve"]

PNG_1PX = base64.b64encode(
    base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
).decode()


def _make(db, *, perms=ALL, member=True):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект")
    db.add(project)
    db.flush()
    site = Site(organization_id=org.id, project_id=project.id, name="Участок 1")
    emp = Employee(organization_id=org.id, full_name="Прораб Тест")
    db.add_all([site, emp])
    db.flush()
    task = Task(organization_id=org.id, project_id=project.id, title="Кладка стен")
    db.add(task)
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
    return org, project, site, task, emp, user


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


def _create(client, project_id, site_id=None):
    body = {"report_date": "2026-07-19", "summary": "Смена отработана"}
    if site_id:
        body["site_id"] = str(site_id)
    return client.post(f"/field-reports/projects/{project_id}", json=body)


# ------------------------------- RBAC/ABAC ------------------------------- #


def test_create_requires_manage(db_engine, db_session) -> None:
    _, project, *_ , user = _make(db_session, perms=VIEW)
    client = _client(db_engine, user)
    assert _create(client, project.id).status_code == 403


def test_abac_denies_foreign_project(db_engine, db_session) -> None:
    _, project, *_ , user = _make(db_session, member=False)
    client = _client(db_engine, user)
    assert _create(client, project.id).status_code == 403


def test_review_requires_approve(db_engine, db_session) -> None:
    _, project, site, task, emp, user = _make(db_session, perms=FOREMAN)
    client = _client(db_engine, user)
    rid = _create(client, project.id).json()["id"]
    client.post(f"/field-reports/{rid}/headcount", json={"profession": "каменщик", "count": 4})
    client.post(f"/field-reports/{rid}/submit")
    # у прораба нет права проверки
    assert client.post(f"/field-reports/{rid}/review", json={"decision": "approved"}).status_code == 403


# --------------------------- Наполнение и фото --------------------------- #


def test_evidence_upload_and_validation(db_engine, db_session) -> None:
    _, project, site, task, emp, user = _make(db_session)
    client = _client(db_engine, user)
    rid = _create(client, project.id, site.id).json()["id"]
    ok = client.post(f"/field-reports/{rid}/evidence", json={
        "original_name": "obj.jpg", "mime_type": "image/jpeg",
        "content_base64": PNG_1PX, "kind": "photo", "caption": "кладка"})
    assert ok.status_code == 201
    # недопустимый тип файла → 422
    bad = client.post(f"/field-reports/{rid}/evidence", json={
        "original_name": "x.exe", "mime_type": "application/x-msdownload",
        "content_base64": PNG_1PX})
    assert bad.status_code == 422


def test_cannot_edit_after_submit(db_engine, db_session) -> None:
    _, project, site, task, emp, user = _make(db_session)
    client = _client(db_engine, user)
    rid = _create(client, project.id).json()["id"]
    client.post(f"/field-reports/{rid}/headcount", json={"profession": "монтажник", "count": 2})
    client.post(f"/field-reports/{rid}/submit")
    # после отправки наполнение запрещено
    r = client.post(f"/field-reports/{rid}/work-items", json={"work_type": "кладка", "actual_quantity": 10})
    assert r.status_code == 409


def test_submit_empty_report_409(db_engine, db_session) -> None:
    _, project, site, task, emp, user = _make(db_session)
    client = _client(db_engine, user)
    # создаём отчёт без summary/содержимого
    rid = client.post(f"/field-reports/projects/{project.id}", json={"report_date": "2026-07-19"}).json()["id"]
    assert client.post(f"/field-reports/{rid}/submit").status_code == 409


# --------------------------- Сквозной цикл ------------------------------- #


def test_full_lifecycle_with_correction(db_engine, db_session) -> None:
    _, project, site, task, emp, user = _make(db_session)
    client = _client(db_engine, user)
    rid = _create(client, project.id, site.id).json()["id"]

    # выполненная работа со связью с задачей
    w = client.post(f"/field-reports/{rid}/work-items", json={
        "work_type": "Кладка стен", "task_id": str(task.id),
        "planned_quantity": 50, "actual_quantity": 42})
    assert w.status_code == 201
    assert w.json()["task_id"] == str(task.id)
    # численность, техника, проблема
    client.post(f"/field-reports/{rid}/headcount", json={"profession": "каменщик", "count": 6})
    client.post(f"/field-reports/{rid}/equipment", json={"name": "Кран КБ-408", "hours": 7.5})
    client.post(f"/field-reports/{rid}/issues", json={"issue_type": "materials", "description": "не хватило раствора", "severity": "warning"})
    # фото-доказательство
    client.post(f"/field-reports/{rid}/evidence", json={
        "original_name": "wall.jpg", "mime_type": "image/jpeg", "content_base64": PNG_1PX})

    # детализация отражает все части
    d = client.get(f"/field-reports/{rid}").json()
    assert len(d["work_items"]) == 1 and len(d["headcount"]) == 1
    assert len(d["equipment"]) == 1 and len(d["issues"]) == 1 and len(d["evidence"]) == 1
    assert d["evidence"][0]["original_name"] == "wall.jpg"

    # отправка → проверка: возврат на доработку
    assert client.post(f"/field-reports/{rid}/submit").json()["status"] == "submitted"
    corr = client.post(f"/field-reports/{rid}/review", json={
        "decision": "correction_required", "comment": "уточните объём"})
    assert corr.json()["status"] == "correction_required"
    assert corr.json()["review_comment"] == "уточните объём"

    # доработка (снова можно добавлять) → повторная отправка → утверждение
    assert client.post(f"/field-reports/{rid}/work-items", json={"work_type": "Затирка швов", "actual_quantity": 12}).status_code == 201
    client.post(f"/field-reports/{rid}/submit")
    appr = client.post(f"/field-reports/{rid}/review", json={"decision": "approved"})
    assert appr.status_code == 200
    assert appr.json()["status"] == "approved"

    # сводка
    s = client.get("/field-reports/summary").json()
    assert s["approved"] == 1


def test_list_and_summary(db_engine, db_session) -> None:
    _, project, site, task, emp, user = _make(db_session)
    client = _client(db_engine, user)
    _create(client, project.id)
    reports = client.get(f"/field-reports/projects/{project.id}").json()
    assert len(reports) == 1 and reports[0]["status"] == "draft"
    assert client.get("/field-reports/summary").json()["draft"] == 1
