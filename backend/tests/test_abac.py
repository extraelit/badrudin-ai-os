"""Тесты ABAC — изоляция по проектам/объектам (T-1.C4)."""

import uuid

from app.core.security import hash_password
from app.models import (
    Employee,
    Organization,
    Project,
    ProjectMember,
    Role,
    User,
    UserRole,
)
from app.services.access import accessible_project_ids, can_access_project


def _org(session):
    o = Organization(legal_name="ООО «Экстра-Элит»")
    session.add(o)
    session.flush()
    return o


def test_member_sees_only_own_project(db_session) -> None:
    org = _org(db_session)
    emp = Employee(organization_id=org.id, full_name="Прораб")
    session_user = User(
        id=uuid.uuid4(), email="f@ex.com", password_hash=hash_password("x")
    )
    p_own = Project(organization_id=org.id, name="Свой")
    p_other = Project(organization_id=org.id, name="Чужой")
    db_session.add_all([emp, session_user, p_own, p_other])
    db_session.flush()
    session_user.employee_id = emp.id
    db_session.add(ProjectMember(project_id=p_own.id, employee_id=emp.id, project_role="foreman"))
    db_session.commit()

    allowed = accessible_project_ids(db_session, session_user)
    assert allowed == {p_own.id}
    assert can_access_project(db_session, session_user, p_own.id) is True
    assert can_access_project(db_session, session_user, p_other.id) is False


def test_system_owner_unrestricted(db_session) -> None:
    org = _org(db_session)
    owner = User(id=uuid.uuid4(), email="o@ex.com", password_hash=hash_password("x"))
    role = Role(code="system_owner", name="Владелец")
    db_session.add_all([owner, role])
    db_session.flush()
    db_session.add(UserRole(user_id=owner.id, role_id=role.id))
    p = Project(organization_id=org.id, name="Любой")
    db_session.add(p)
    db_session.commit()
    assert accessible_project_ids(db_session, owner) is None
    assert can_access_project(db_session, owner, p.id) is True
