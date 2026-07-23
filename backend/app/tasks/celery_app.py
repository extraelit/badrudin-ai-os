"""Celery-приложение для фоновых задач (PR-9).

В development/test выполняется синхронно (`task_always_eager`), реальный брокер
не требуется. В production брокер/бэкенд берутся из окружения (Redis).
"""

from __future__ import annotations

from celery import Celery

from app.core.config import get_settings

_settings = get_settings()

celery_app = Celery(
    "badrudin",
    broker=_settings.celery_broker_url,
    backend=_settings.celery_result_backend,
    include=["app.tasks.communications_tasks"],
)
celery_app.conf.update(
    task_always_eager=_settings.celery_task_always_eager,
    task_eager_propagates=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    timezone="UTC",
)
