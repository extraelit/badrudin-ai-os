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
