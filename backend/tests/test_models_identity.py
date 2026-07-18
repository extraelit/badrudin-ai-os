"""Тесты моделей идентификации (T-1.B2)."""

import uuid

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.models import Base, Employee, Organization, User


def _engine():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    return engine


def test_create_organization_employee_user() -> None:
    engine = _engine()
    with Session(engine) as s:
        org = Organization(legal_name="ООО «Экстра-Элит»", short_name="Экстра-Элит")
        s.add(org)
        s.flush()
        emp = Employee(organization_id=org.id, full_name="Тестовый Прораб")
        s.add(emp)
        s.flush()
        user = User(
            employee_id=emp.id,
            email="user@example.com",
            password_hash="not-a-real-hash",
        )
        s.add(user)
        s.commit()

        loaded = s.scalar(select(User).where(User.email == "user@example.com"))
        assert loaded is not None
        assert isinstance(loaded.id, uuid.UUID)
        assert loaded.employee_id == emp.id
        assert loaded.mfa_enabled is False
        assert loaded.preferred_language == "ru"


def test_user_email_unique() -> None:
    engine = _engine()
    with Session(engine) as s:
        s.add(User(email="dup@example.com", password_hash="h1"))
        s.commit()
        s.add(User(email="dup@example.com", password_hash="h2"))
        try:
            s.commit()
            raised = False
        except Exception:
            raised = True
        assert raised, "email должен быть уникальным"
