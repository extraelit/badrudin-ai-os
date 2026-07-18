"""Тесты неизменяемости журнала аудита (T-1.D2)."""

import pytest

from app.models.audit import AuditImmutableError
from app.services.audit import record_event


def test_audit_event_cannot_be_updated(db_session) -> None:
    event = record_event(db_session, actor_type="system", action="x")
    event.action = "tampered"
    with pytest.raises(AuditImmutableError):
        db_session.commit()
    db_session.rollback()


def test_audit_event_cannot_be_deleted(db_session) -> None:
    event = record_event(db_session, actor_type="system", action="y")
    db_session.delete(event)
    with pytest.raises(AuditImmutableError):
        db_session.commit()
    db_session.rollback()
