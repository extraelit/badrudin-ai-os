"""Тесты Evidence Gate: обязательные доказательства и исключения (PR-D2).

Проверяют: без обязательного доказательства процесс нельзя отправить на проверку;
приложенное доказательство (с файлом) открывает гейт; матрица пуста по умолчанию
(гейт не мешает); запрос исключения требует причины; исключение согласует только
уполномоченный руководитель (ген./исп. директор), решение помечает результат как
«принят без стандартного доказательства» и пишется в аудит; RBAC/ABAC и изоляция.
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
    File,
    Organization,
    Permission,
    Role,
    RolePermission,
    User,
    UserRole,
)
from app.services import evidence as ev
from app.services import workflow as wf


def _org(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    return org


def _file(db, org):
    f = File(organization_id=org.id, storage_key=f"k/{uuid.uuid4().hex}",
             original_name="фото.jpg", checksum_sha256="a" * 64)
    db.add(f)
    db.flush()
    return f


def _user(db, org, *, roles=(), perms=(), email=None):
    emp = Employee(organization_id=org.id, full_name="Сотрудник")
    db.add(emp)
    db.flush()
    user = User(email=email or f"u{uuid.uuid4().hex[:8]}@ex.com",
                password_hash=hash_password("x"), status="active", employee_id=emp.id)
    db.add(user)
    db.flush()
    for rc in roles:
        r = db.query(Role).filter(Role.code == rc).first()
        if r is None:
            r = Role(code=rc, name=rc)
            db.add(r)
            db.flush()
        db.add(UserRole(user_id=user.id, role_id=r.id))
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


# ---------------------------------------------------------------------------
# Сервисный уровень: гейт и исключения
# ---------------------------------------------------------------------------

def _process_in_progress(db, org, executor):
    p = wf.create_process(db, org.id, process_kind="daily_report", title="Отчёт",
                          author_user_id=uuid.uuid4(), risk_level="R1")
    wf.assign(db, p, initiator_user_id=uuid.uuid4(), executor_id=executor)
    wf.accept(db, p, actor_user_id=executor)
    wf.start(db, p, actor_user_id=executor)
    return p


def test_gate_empty_matrix_does_not_block(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    p = _process_in_progress(db_session, org, executor)
    # требований нет — гейт пропускает
    wf.submit_for_review(db_session, p, actor_user_id=executor)
    assert p.status == "submitted_for_review"


def test_gate_blocks_submit_without_required_evidence(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo")
    p = _process_in_progress(db_session, org, executor)
    with pytest.raises(ev.EvidenceGateError, match="photo"):
        wf.submit_for_review(db_session, p, actor_user_id=executor)
    assert p.status == "in_progress"  # осталось в работе


def test_attached_evidence_opens_gate(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo")
    p = _process_in_progress(db_session, org, executor)
    f = _file(db_session, org)
    ev.add_evidence(db_session, p, evidence_type="photo", file_id=f.id,
                    actor_user_id=executor)
    wf.submit_for_review(db_session, p, actor_user_id=executor)
    assert p.status == "submitted_for_review"


def test_min_count_enforced(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo", min_count=2)
    p = _process_in_progress(db_session, org, executor)
    ev.add_evidence(db_session, p, evidence_type="photo",
                    file_id=_file(db_session, org).id)
    assert ev.missing_required(db_session, p) == ["photo"]  # одного мало
    ev.add_evidence(db_session, p, evidence_type="photo",
                    file_id=_file(db_session, org).id)
    assert ev.missing_required(db_session, p) == []


def test_evidence_requires_existing_file(db_session) -> None:
    org = _org(db_session)
    p = wf.create_process(db_session, org.id, process_kind="task", title="T",
                          author_user_id=uuid.uuid4(), risk_level="R1")
    with pytest.raises(ev.EvidenceError, match="Файл"):
        ev.add_evidence(db_session, p, evidence_type="photo", file_id=uuid.uuid4())


def test_evidence_file_cross_org_rejected(db_session) -> None:
    org = _org(db_session)
    other = _org(db_session)
    p = wf.create_process(db_session, org.id, process_kind="task", title="T",
                          author_user_id=uuid.uuid4(), risk_level="R1")
    foreign_file = _file(db_session, other)
    with pytest.raises(ev.EvidenceError, match="организац"):
        ev.add_evidence(db_session, p, evidence_type="photo", file_id=foreign_file.id)


# ---------------------------------------------------------------------------
# Исключения: причина + согласование уполномоченного руководителя
# ---------------------------------------------------------------------------

def test_exception_requires_reason(db_session) -> None:
    org = _org(db_session)
    p = wf.create_process(db_session, org.id, process_kind="daily_report",
                          title="Отчёт", author_user_id=uuid.uuid4(), risk_level="R1")
    with pytest.raises(ev.EvidenceError, match="причин"):
        ev.request_exception(db_session, p, evidence_type="photo", reason="")


def test_only_director_approves_exception(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo")
    p = _process_in_progress(db_session, org, executor)
    req = ev.request_exception(db_session, p, evidence_type="photo",
                               reason="съёмка невозможна", requested_by=executor)
    # обычный сотрудник (без роли директора) не согласует
    ordinary = _user(db_session, org, roles=("foreman",))
    with pytest.raises(ev.EvidenceError, match="руководител"):
        ev.decide_exception(db_session, req, approver_user_id=ordinary.id, approve=True)


def test_approved_exception_opens_gate_and_marks_audit(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo")
    p = _process_in_progress(db_session, org, executor)
    req = ev.request_exception(db_session, p, evidence_type="photo",
                               reason="объект под водой", requested_by=executor)
    director = _user(db_session, org, roles=("general_director",))
    ev.decide_exception(db_session, req, approver_user_id=director.id, approve=True,
                        comment="принято")
    # гейт открыт исключением — можно отправить на проверку
    assert ev.missing_required(db_session, p) == []
    wf.submit_for_review(db_session, p, actor_user_id=executor)
    assert p.status == "submitted_for_review"
    # аудит помечает «принят без стандартного доказательства»
    event = (
        db_session.query(AuditEvent)
        .filter(AuditEvent.action == "evidence.exception.decide")
        .first()
    )
    assert event is not None
    assert event.new_values_json["accepted_without_standard_evidence"] is True


def test_rejected_exception_keeps_gate_closed(db_session) -> None:
    org = _org(db_session)
    executor = uuid.uuid4()
    ev.set_requirement(db_session, org.id, process_kind="daily_report",
                       evidence_type="photo")
    p = _process_in_progress(db_session, org, executor)
    req = ev.request_exception(db_session, p, evidence_type="photo",
                               reason="нет времени", requested_by=executor)
    director = _user(db_session, org, roles=("executive_director",))
    ev.decide_exception(db_session, req, approver_user_id=director.id, approve=False,
                        comment="недостаточное основание")
    assert ev.missing_required(db_session, p) == ["photo"]
    with pytest.raises(ev.EvidenceGateError):
        wf.submit_for_review(db_session, p, actor_user_id=executor)


def test_double_decision_rejected(db_session) -> None:
    org = _org(db_session)
    p = wf.create_process(db_session, org.id, process_kind="daily_report",
                          title="Отчёт", author_user_id=uuid.uuid4(), risk_level="R1")
    req = ev.request_exception(db_session, p, evidence_type="photo",
                               reason="причина", requested_by=uuid.uuid4())
    director = _user(db_session, org, roles=("general_director",))
    ev.decide_exception(db_session, req, approver_user_id=director.id, approve=True)
    with pytest.raises(ev.EvidenceError, match="рассмотрен"):
        ev.decide_exception(db_session, req, approver_user_id=director.id, approve=True)


# ---------------------------------------------------------------------------
# API: RBAC / ABAC / изоляция
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


def test_api_set_requirement_requires_assign(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    user = _user(db_session, org, perms=["task.view"])
    client = _client(db_engine, user)
    resp = client.post("/evidence/requirements",
                       json={"process_kind": "daily_report", "evidence_type": "photo"})
    assert resp.status_code == 403


def test_api_gate_and_submit_block(db_engine, db_session) -> None:
    org = _org(db_session)
    db_session.commit()
    manager = _user(db_session, org,
                    perms=["task.view", "task.create", "task.assign",
                           "task.execute", "task.approve"], email="mgr@ex.com")
    client = _client(db_engine, manager)
    # задаём требование фото для daily_report
    client.post("/evidence/requirements",
                json={"process_kind": "daily_report", "evidence_type": "photo"})
    pid = client.post("/processes/",
                      json={"process_kind": "daily_report", "title": "Отчёт"}).json()["id"]
    # проведём процесс до in_progress: назначим другого исполнителя
    exec_user = _user(db_session, org,
                      perms=["task.view", "task.execute"], email="ex@ex.com")
    client.post(f"/processes/{pid}/assign", json={"executor_id": str(exec_user.id)})
    # гейт: не хватает photo
    gate = client.get(f"/processes/{pid}/evidence/gate").json()
    assert gate["satisfied"] is False and "photo" in gate["missing"]
