"""Тесты каркаса Celery (T-1.F1)."""

from app.worker.celery_app import celery_app, ping


def test_celery_configured() -> None:
    assert celery_app.main == "badrudin"
    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.timezone == "UTC"


def test_ping_task_runs_eagerly() -> None:
    celery_app.conf.task_always_eager = True
    try:
        result = ping.apply()
        assert result.get() == "pong"
    finally:
        celery_app.conf.task_always_eager = False
