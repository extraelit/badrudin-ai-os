"""Тест соглашений моделей и миксинов (T-1.B1)."""

import uuid
from datetime import datetime

from sqlalchemy import String, create_engine
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db.base import Base, SoftDeleteMixin, TimestampMixin, UUIDPrimaryKeyMixin


class _Sample(UUIDPrimaryKeyMixin, TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "sample_conventions"
    name: Mapped[str] = mapped_column(String(50))


def test_naming_convention_present() -> None:
    for key in ("ix", "uq", "ck", "fk", "pk"):
        assert key in Base.metadata.naming_convention


def test_mixins_apply_conventions() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine, tables=[_Sample.__table__])
    with Session(engine) as session:
        obj = _Sample(name="проверка")
        session.add(obj)
        session.commit()
        session.refresh(obj)
        assert isinstance(obj.id, uuid.UUID)
        assert isinstance(obj.created_at, datetime)
        assert isinstance(obj.updated_at, datetime)
        assert obj.is_archived is False
        assert obj.deleted_at is None
