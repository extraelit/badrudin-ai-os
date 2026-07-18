"""Общие фикстуры тестов: приложение с БД SQLite в памяти."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core import token_store
from app.core.security import hash_password
from app.db.session import get_db
from app.main import app
from app.models import Base, User


@pytest.fixture
def db_engine():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture
def db_session(db_engine) -> Iterator[Session]:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)
    session = factory()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client(db_engine) -> Iterator[TestClient]:
    factory = sessionmaker(bind=db_engine, autoflush=False, autocommit=False)

    def override_get_db() -> Iterator[Session]:
        db = factory()
        try:
            yield db
        finally:
            db.close()

    token_store.clear()
    app.dependency_overrides[get_db] = override_get_db
    with TestClient(app) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture
def seed_user(db_session) -> User:
    user = User(
        id=uuid.uuid4(),
        email="foreman@example.com",
        password_hash=hash_password("Secret123!"),
        status="active",
    )
    db_session.add(user)
    db_session.commit()
    return user
