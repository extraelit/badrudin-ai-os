"""Health-check эндпоинты (T-1.A4; readiness — PR-9)."""

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app import __version__
from app.core.config import get_settings
from app.db.session import get_db

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


@router.get("/health/ready")
def readiness(response: Response, db: Session = Depends(get_db)) -> dict[str, object]:
    """Readiness-проба (PR-9): проверяет доступность БД (SELECT 1).

    Возвращает 200 при доступной БД и 503 при ошибке подключения — пригодно для
    оркестратора (Kubernetes/Compose healthcheck).
    """
    try:
        db.execute(text("SELECT 1"))
        return {"status": "ready", "database": True}
    except Exception:  # noqa: BLE001 — не раскрываем детали ошибки БД наружу
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready", "database": False}


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
