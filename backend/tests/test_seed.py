"""Тест загрузки тестовых данных (T-1.B8)."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.seed import is_seeded, load_fixtures, seed_if_empty
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


def test_seed_if_empty_is_idempotent() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        assert is_seeded(s) is False
        first = seed_if_empty(s)
        assert first is not None
        assert first["organizations"] >= 1
        assert is_seeded(s) is True

    # Повторный запуск на уже засеянной БД не создаёт дубликатов.
    with Session(engine) as s2:
        assert is_seeded(s2) is True
        assert seed_if_empty(s2) is None
        assert s2.query(Organization).count() == first["organizations"]
        assert s2.query(Role).count() == first["roles"]
