"""Тесты ежедневного отчёта: ИИ-черновик и правила отправки (этап E, PR-E).

Проверяют: ИИ-черновик создаётся как предложение и НЕ утверждает отчёт (честный
контур); подтверждает человек; отчёт нельзя отправить без фото/видео, кроме
отметки «работы не велись» (с причиной) или согласованного исключения
уполномоченного руководителя; медиа без метаданных помечаются как фактор риска.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from app.api.deps import get_current_user
from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import (
    AgentProposal,
    DailyReport,
    DailyReportFile,
    Employee,
    File,
    Organization,
    Permission,
    Project,
    ProjectMember,
    Role,
    RolePermission,
    User,
)
from app.services import daily_report_ai as svc


def _org_project(db):
    org = Organization(legal_name="ТЕСТ")
    db.add(org)
    db.flush()
    project = Project(organization_id=org.id, name="Объект", status="active")
    db.add(project)
    db.flush()
    return org, project


def _report(db, project):
    r = DailyReport(project_id=project.id, report_date=date(2026, 7, 22), status="draft")
    db.add(r)
    db.flush()
    return r


def _file(db, org, *, metadata=None):
    f = File(organization_id=org.id, storage_key=f"k/{uuid.uuid4().hex}",
             original_name="ф.jpg", checksum_sha256="a" * 64, metadata_json=metadata)
    db.add(f)
    db.flush()
    return f


def _add_media(db, report, org, *, kind="photo", metadata=None):
    f = _file(db, org, metadata=metadata)
    m = DailyReportFile(daily_report_id=report.id, file_id=f.id, kind=kind)
    db.add(m)
    db.flush()
    return m


def _user(db, org, project, *, perms=(), roles=(), member=True, email=None):
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
    from app.models import UserRole
    db.add(UserRole(user_id=user.id, role_id=role.id))
    for pc in perms:
        p = db.query(Permission).filter(Permission.code == pc).first()
        if p is None:
            p = Permission(code=pc)
            db.add(p)
            db.flush()
        db.add(RolePermission(role_id=role.id, permission_id=p.id))
    for rc in roles:
        r = db.query(Role).filter(Role.code == rc).first()
        if r is None:
            r = Role(code=rc, name=rc)
            db.add(r)
            db.flush()
        db.add(UserRole(user_id=user.id, role_id=r.id))
    if member:
        db.add(ProjectMember(project_id=project.id, employee_id=emp.id,
                             project_role="member"))
    db.commit()
    return user


# ---------------------------------------------------------------------------
# ИИ-черновик — предложение, не утверждение (D-010)
# ---------------------------------------------------------------------------

def test_ai_draft_is_proposal_not_approval(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    _add_media(db_session, report, org)
    proposal = svc.generate_ai_draft(db_session, report, actor_user_id=uuid.uuid4())
    assert proposal.status == "pending"  # ИИ не утверждает
    assert proposal.proposal_type == "daily_report_draft"
    db_session.refresh(report)
    assert report.status == "draft"  # отчёт НЕ переведён в approved автоматически


def test_human_confirms_ai_draft_applies_summary(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    _add_media(db_session, report, org)
    proposal = svc.generate_ai_draft(db_session, report, actor_user_id=uuid.uuid4())
    actor = uuid.uuid4()
    svc.confirm_ai_draft(db_session, proposal, actor_user_id=actor)
    assert proposal.status == "approved" and proposal.decided_by_user_id == actor
    db_session.refresh(report)
    assert report.summary  # черновик применён к сводке человеком


def test_reject_ai_draft(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    proposal = svc.generate_ai_draft(db_session, report, actor_user_id=uuid.uuid4())
    svc.reject_ai_draft(db_session, proposal, actor_user_id=uuid.uuid4(),
                        comment="неполно")
    assert proposal.status == "rejected"


def test_double_decision_rejected(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    proposal = svc.generate_ai_draft(db_session, report, actor_user_id=uuid.uuid4())
    svc.confirm_ai_draft(db_session, proposal, actor_user_id=uuid.uuid4())
    with pytest.raises(svc.DailyReportError):
        svc.confirm_ai_draft(db_session, proposal, actor_user_id=uuid.uuid4())


# ---------------------------------------------------------------------------
# Медиа-предупреждения (метаданные не гарантированы)
# ---------------------------------------------------------------------------

def test_media_without_metadata_flagged(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    _add_media(db_session, report, org, metadata=None)  # без метаданных
    _add_media(db_session, report, org, metadata={"gps": "x"})  # с метаданными
    warnings = svc.media_metadata_warnings(db_session, report)
    assert len(warnings) == 1


# ---------------------------------------------------------------------------
# Правила отправки
# ---------------------------------------------------------------------------

def test_submit_blocked_without_media(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    with pytest.raises(svc.DailyReportError, match="фото/видео"):
        svc.submit_report(db_session, report, actor_user_id=uuid.uuid4())
    assert report.status == "draft"


def test_submit_allowed_with_media(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    _add_media(db_session, report, org)
    svc.submit_report(db_session, report, actor_user_id=uuid.uuid4())
    assert report.status == "submitted" and report.submitted_at is not None


def test_no_work_requires_reason_then_submittable(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    with pytest.raises(svc.DailyReportError, match="причин"):
        svc.mark_no_work(db_session, report, reason="", actor_user_id=uuid.uuid4())
    svc.mark_no_work(db_session, report, reason="выходной", actor_user_id=uuid.uuid4())
    assert report.no_work is True
    # без медиа, но «работы не велись» — отправка разрешена
    svc.submit_report(db_session, report, actor_user_id=uuid.uuid4())
    assert report.status == "submitted"


def test_submit_without_media_needs_director(db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    ordinary = _user(db_session, org, project, roles=("foreman",))
    with pytest.raises(svc.DailyReportError, match="руководител"):
        svc.submit_without_media_exception(
            db_session, report, actor_user_id=ordinary.id, reason="связь недоступна"
        )
    director = _user(db_session, org, project, roles=("general_director",),
                     email="gd@ex.com")
    with pytest.raises(svc.DailyReportError, match="причин"):
        svc.submit_without_media_exception(
            db_session, report, actor_user_id=director.id, reason=""
        )
    svc.submit_without_media_exception(
        db_session, report, actor_user_id=director.id, reason="объект недоступен"
    )
    assert report.status == "submitted"


# ---------------------------------------------------------------------------
# API: RBAC / ABAC
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


def test_api_generate_requires_manage(db_engine, db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    db_session.commit()
    user = _user(db_session, org, project, perms=["daily_report.view"])
    client = _client(db_engine, user)
    resp = client.post(f"/daily-reports/{report.id}/ai-draft")
    assert resp.status_code == 403


def test_api_no_project_access_denied(db_engine, db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    db_session.commit()
    outsider = _user(db_session, org, project,
                     perms=["daily_report.view", "daily_report.manage"],
                     member=False)
    client = _client(db_engine, outsider)
    resp = client.post(f"/daily-reports/{report.id}/ai-draft")
    assert resp.status_code == 403


def test_api_full_ai_draft_flow(db_engine, db_session) -> None:
    org, project = _org_project(db_session)
    report = _report(db_session, project)
    _add_media(db_session, report, org)
    db_session.commit()
    user = _user(db_session, org, project,
                 perms=["daily_report.view", "daily_report.manage",
                        "daily_report.approve"], email="mgr@ex.com")
    client = _client(db_engine, user)
    gen = client.post(f"/daily-reports/{report.id}/ai-draft")
    assert gen.status_code == 201, gen.text
    pid = gen.json()["proposal_id"]
    assert gen.json()["status"] == "pending"
    conf = client.post(f"/daily-reports/{report.id}/ai-draft/{pid}/confirm")
    assert conf.status_code == 200 and conf.json()["status"] == "approved"
