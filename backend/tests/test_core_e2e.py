"""Сквозной тест рабочего ядра Badrudin AI OS.

Проверяет полный минимальный управленческий цикл через API (CLAUDE.md §31):
вход → создание проекта → объект → задача → согласование → назначение →
исполнение → завершение → ежедневный отчёт → отражение в сводке директора.
Также проверяет реальный вход через /auth/login и enriched /auth/me.
"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.core import token_store
from app.db.seed import DEFAULT_DEMO_PASSWORD, load_fixtures
from app.db.session import get_db
from app.main import app
from app.models import Employee, User


@pytest.fixture
def seeded(db_engine, db_session) -> None:
    load_fixtures(db_session)


def _client(db_engine) -> TestClient:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    token_store.clear()
    app.dependency_overrides[get_db] = override_db
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()


def _login(client: TestClient, email: str) -> str:
    r = client.post("/auth/login", json={"email": email, "password": DEFAULT_DEMO_PASSWORD})
    assert r.status_code == 200, r.text
    return r.json()["access_token"]


def test_login_and_me_returns_roles_permissions(db_engine, db_session, seeded) -> None:
    client = _client(db_engine)
    token = _login(client, "director@extra-elit.demo")
    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    body = me.json()
    assert "production_director" in body["roles"]
    assert "task.create" in body["permissions"]
    assert "project.view" in body["permissions"]


def test_full_management_cycle(db_engine, db_session, seeded) -> None:
    client = _client(db_engine)
    token = _login(client, "director@extra-elit.demo")
    h = {"Authorization": f"Bearer {token}"}

    # исполнитель — сотрудник прораба
    foreman_emp = db_session.execute(
        __import__("sqlalchemy").select(Employee).where(Employee.full_name.like("Прораб%"))
    ).scalars().first()

    # 1. создание проекта
    proj = client.post("/core/projects", json={"name": "Северный коллектор"}, headers=h)
    assert proj.status_code == 201, proj.text
    pid = proj.json()["id"]

    # 2. объект
    site = client.post(f"/core/projects/{pid}/sites", json={"name": "Участок А", "address": "ул. Демо, 1"}, headers=h)
    assert site.status_code == 201
    sid = site.json()["id"]

    # 3. задача
    task = client.post(f"/core/projects/{pid}/tasks", json={
        "title": "Уложить трубу ПНД", "site_id": sid, "owner_employee_id": str(foreman_emp.id),
    }, headers=h)
    assert task.status_code == 201
    tid = task.json()["id"]
    assert task.json()["status"] == "draft"

    # 4. отправка на согласование
    sub = client.post(f"/core/tasks/{tid}/submit", headers=h)
    assert sub.status_code == 200 and sub.json()["status"] == "pending_approval"

    # 5. согласование руководителем
    approvals = client.get("/core/approvals", headers=h).json()
    task_appr = [a for a in approvals if a["entity_id"] == tid][0]
    dec = client.post(f"/core/approvals/{task_appr['id']}/decision", json={"decision": "approved"}, headers=h)
    assert dec.status_code == 200 and dec.json()["status"] == "approved"
    assert client.get(f"/core/tasks/{tid}", headers=h).json()["status"] == "approved"

    # 6. назначение → приёмка → исполнение → завершение
    assert client.post(f"/core/tasks/{tid}/assign", json={"employee_id": str(foreman_emp.id)}, headers=h).json()["status"] == "assigned"
    assert client.post(f"/core/tasks/{tid}/accept", headers=h).json()["status"] == "accepted"
    assert client.post(f"/core/tasks/{tid}/progress", json={"progress_percent": 60}, headers=h).json()["status"] == "in_progress"
    assert client.post(f"/core/tasks/{tid}/complete", json={"note": "Готово"}, headers=h).json()["status"] == "completed"

    # 7. ежедневный отчёт → отправка → согласование
    rep = client.post(f"/core/projects/{pid}/daily-reports", json={
        "report_date": date.today().isoformat(), "site_id": sid, "workers_count": 8,
        "summary": "Уложено 200 м трубы",
    }, headers=h)
    assert rep.status_code == 201
    rid = rep.json()["id"]
    assert client.post(f"/core/daily-reports/{rid}/submit", headers=h).json()["status"] == "submitted"
    reps_appr = [a for a in client.get("/core/approvals", headers=h).json() if a["entity_id"] == rid][0]
    client.post(f"/core/approvals/{reps_appr['id']}/decision", json={"decision": "approved"}, headers=h)

    # 8. отражение на дашборде
    dash = client.get("/core/dashboard", headers=h).json()
    assert dash["projects"] == 1
    assert dash["sites"] == 1
    assert dash["tasks_completed"] == 1
    assert dash["reports_today"] == 1


def test_rbac_viewer_cannot_create_project(db_engine, db_session, seeded) -> None:
    # у наблюдателя нет прав, но и пользователя-наблюдателя в сиде нет — проверяем
    # отказ через отсутствие права: создадим пользователя без нужных прав нельзя,
    # поэтому проверяем, что foreman (нет project.create) получает 403
    client = _client(db_engine)
    token = _login(client, "foreman@extra-elit.demo")
    h = {"Authorization": f"Bearer {token}"}
    r = client.post("/core/projects", json={"name": "X"}, headers=h)
    assert r.status_code == 403


def test_abac_isolation_between_projects(db_engine, db_session, seeded) -> None:
    from sqlalchemy import select

    from app.models import Organization, Project

    client = _client(db_engine)
    token = _login(client, "director@extra-elit.demo")
    h = {"Authorization": f"Bearer {token}"}
    pid = client.post("/core/projects", json={"name": "Свой"}, headers=h).json()["id"]
    # проект в той же организации, но без членства director → нет доступа (ABAC)
    org = db_session.execute(select(Organization)).scalars().first()
    other = Project(organization_id=org.id, name="Чужой")
    db_session.add(other)
    db_session.commit()
    assert client.get(f"/core/projects/{other.id}", headers=h).status_code == 403
    assert client.get(f"/core/projects/{pid}", headers=h).status_code == 200
