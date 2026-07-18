"""Тесты временного доступа project_access (T-1.C5)."""

import uuid
from datetime import UTC, datetime, timedelta

from app.core.security import hash_password
from app.models import Organization, Project, ProjectAccess, User
from app.services.access import can_access_project


def _setup(db_session):
    org = Organization(legal_name="ООО «Экстра-Элит»")
    db_session.add(org)
    db_session.flush()
    user = User(id=uuid.uuid4(), email="ext@ex.com", password_hash=hash_password("x"))
    project = Project(organization_id=org.id, name="Объект")
    db_session.add_all([user, project])
    db_session.flush()
    return user, project


def test_active_grant_gives_access(db_session) -> None:
    user, project = _setup(db_session)
    db_session.add(
        ProjectAccess(
            project_id=project.id,
            user_id=user.id,
            access_level="read",
            valid_until=datetime.now(UTC) + timedelta(days=1),
        )
    )
    db_session.commit()
    assert can_access_project(db_session, user, project.id) is True


def test_expired_grant_denies_access(db_session) -> None:
    user, project = _setup(db_session)
    db_session.add(
        ProjectAccess(
            project_id=project.id,
            user_id=user.id,
            access_level="read",
            valid_until=datetime.now(UTC) - timedelta(days=1),
        )
    )
    db_session.commit()
    # истёкший доступ не действует (ACCESS_CONTROL раздел 23)
    assert can_access_project(db_session, user, project.id) is False
