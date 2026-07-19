"""Точка входа backend Badrudin AI OS (FastAPI).

Backend — единственная точка доступа к данным для интерфейса и ИИ-агентов
(ARCHITECTURE.md раздел 5.2). На этапе T-1.A4 реализован каркас с health-check;
работа с базой (блок 1.B), аутентификация (1.C) и фоновые задачи (1.F)
добавляются последующими задачами.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api import (
    accountable,
    auth,
    core,
    crm,
    design,
    digest,
    equipment,
    estimates,
    field_report,
    finance,
    health,
    inventory,
    personnel,
    procurement,
    task_control,
)
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
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(core.router)
    app.include_router(task_control.router)
    app.include_router(digest.router)
    app.include_router(personnel.router)
    app.include_router(design.router)
    app.include_router(estimates.router)
    app.include_router(procurement.router)
    app.include_router(inventory.router)
    app.include_router(equipment.router)
    app.include_router(field_report.router)
    app.include_router(crm.router)
    app.include_router(finance.router)
    app.include_router(accountable.router)
    return app


app = create_app()
