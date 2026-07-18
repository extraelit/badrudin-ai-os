"""Движок и сессии SQLAlchemy."""

from __future__ import annotations

from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

_settings = get_settings()

engine = create_engine(_settings.database_url, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)


def get_db() -> Iterator[Session]:
    """Зависимость FastAPI: сессия БД с гарантированным закрытием."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
