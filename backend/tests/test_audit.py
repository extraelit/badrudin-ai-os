"""Тесты записи журнала аудита (T-1.D1)."""

from app.models import AuditEvent
from app.services.audit import record_event


def test_record_event(db_session) -> None:
    event = record_event(
        db_session,
        actor_type="system",
        action="task.created",
        entity_type="task",
        risk_level="R1",
    )
    assert event.id is not None
    assert event.created_at is not None
    assert db_session.query(AuditEvent).count() == 1


def test_login_writes_audit(client, db_session, seed_user) -> None:
    client.post(
        "/auth/login",
        json={"email": "foreman@example.com", "password": "Secret123!"},
    )
    # событие входа зафиксировано в едином журнале (та же БД)
    events = db_session.query(AuditEvent).filter(AuditEvent.action == "auth.login").all()
    assert len(events) >= 1
    assert events[0].actor_type == "user"
