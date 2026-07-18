"""Тест загрузки тестовых данных (T-1.B8)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.seed import load_fixtures
from app.models import Base, Organization, Permission, Role


def test_load_fixtures() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        counts = load_fixtures(s)
        assert counts["organizations"] >= 1
        assert counts["roles"] >= 1
        assert counts["permissions"] >= 1
        assert s.query(Organization).count() == counts["organizations"]
        assert s.query(Role).count() == counts["roles"]
        assert s.query(Permission).count() == counts["permissions"]
