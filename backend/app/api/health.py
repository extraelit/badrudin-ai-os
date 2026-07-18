"""Health-check эндпоинт (T-1.A4)."""

from fastapi import APIRouter

from app import __version__
from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, str | bool]:
    """Проверка работоспособности backend.

    Возвращает статус, имя приложения, среду и версию. Значения берутся из
    конфигурации, читаемой из окружения.
    """
    settings = get_settings()
    return {
        "status": "ok",
        "app": settings.app_name,
        "environment": settings.app_env,
        "version": __version__,
    }


@router.get("/health/status")
def integrations_status() -> dict[str, object]:
    """Сводка о настроенных интеграциях (T-1.G3).

    Показывает, какие компоненты сконфигурированы (не выполняет живую проверку —
    активный мониторинг доступности реализуется в T-1.J3).
    """
    settings = get_settings()
    return {
        "status": "ok",
        "components": {
            "database": bool(settings.database_url),
            "redis": bool(settings.redis_url),
            "object_storage": bool(settings.minio_endpoint),
            "broker": bool(settings.celery_broker_url),
        },
    }
