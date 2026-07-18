"""Пакет фоновых задач Celery (T-1.F)."""

from app.worker.celery_app import celery_app

__all__ = ["celery_app"]
