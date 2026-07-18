"""Тесты планировщика Celery beat (T-1.F2)."""

from app.worker.celery_app import celery_app


def test_beat_schedule_configured() -> None:
    schedule = celery_app.conf.beat_schedule
    assert "heartbeat" in schedule
    assert schedule["heartbeat"]["task"] == "badrudin.ping"
