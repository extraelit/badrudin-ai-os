"""Точка входа backend Badrudin AI OS (FastAPI).

Backend — единственная точка доступа к данным для интерфейса и ИИ-агентов
(ARCHITECTURE.md раздел 5.2). На этапе T-1.A4 реализован каркас с health-check;
работа с базой (блок 1.B), аутентификация (1.C) и фоновые задачи (1.F)
добавляются последующими задачами.
"""

from fastapi import FastAPI

from app import __version__
from app.api import auth, health
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр приложения FastAPI."""
    settings = get_settings()
    configure_logging()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        debug=settings.app_debug,
    )
    app.add_middleware(RequestIDMiddleware)
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    return app


app = create_app()
