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
    agents,
    auth,
    core,
    crm,
    design,
    digest,
    equipment,
    estimates,
    executive_doc,
    field_report,
    finance,
    health,
    inbox,
    integration,
    inventory,
    kpi,
    normative,
    notifications,
    personnel,
    procurement,
    risk,
    smm,
    task_control,
    webauthn,
    workflow,
)
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import RequestIDMiddleware
from app.core.preflight import check_required_secrets


def create_app() -> FastAPI:
    """Создаёт и настраивает экземпляр приложения FastAPI."""
    settings = get_settings()
    configure_logging()
    # Fail-fast по секретам: в staging/production запуск с заглушками запрещён,
    # в development выводится предупреждение (см. app.core.preflight).
    check_required_secrets(settings)
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
    app.include_router(inbox.router)
    app.include_router(agents.router)
    app.include_router(risk.router)
    app.include_router(integration.router)
    app.include_router(smm.router)
    app.include_router(kpi.router)
    app.include_router(notifications.router)
    app.include_router(personnel.router)
    app.include_router(design.router)
    app.include_router(estimates.router)
    app.include_router(executive_doc.router)
    app.include_router(procurement.router)
    app.include_router(inventory.router)
    app.include_router(equipment.router)
    app.include_router(field_report.router)
    app.include_router(crm.router)
    app.include_router(finance.router)
    app.include_router(accountable.router)
    app.include_router(normative.router)
    app.include_router(webauthn.router)
    app.include_router(workflow.router)
    return app


app = create_app()
