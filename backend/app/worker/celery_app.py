"""Экземпляр Celery для фоновых задач и планировщика (T-1.F1, T-1.F2).

Брокер и хранилище результатов — Redis (D-008). Критическая бизнес-логика не
хранится только в оркестраторе (ARCHITECTURE.md раздел 5.4).
"""

from __future__ import annotations

from datetime import timedelta

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "badrudin",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
)

celery_app.conf.update(
    task_track_started=True,
    task_acks_late=True,
    worker_max_tasks_per_child=1000,
    task_default_retry_delay=30,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

# Расписание периодических задач (T-1.F2). Каркас для напоминаний и эскалаций
# (реализация правил — на последующих этапах); здесь — heartbeat для проверки
# работоспособности планировщика.
celery_app.conf.beat_schedule = {
    "heartbeat": {
        "task": "badrudin.ping",
        "schedule": timedelta(hours=1),
    },
}


@celery_app.task(name="badrudin.ping")
def ping() -> str:
    """Базовая проверочная задача (liveness worker)."""
    return "pong"
