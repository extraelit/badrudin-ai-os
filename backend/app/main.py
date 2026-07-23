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
    ai_provider,
    attachments,
    auth,
    communications,
    core,
    crm,
    daily_report_ai,
    dashboards,
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
    quality,
    personnel,
    procurement,
    risk,
    risk_threshold,
    smm,
    evidence,
    task_control,
    webauthn,
    workflow,
)
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging
from app.core.middleware import (
    RateLimitMiddleware,
    RequestIDMiddleware,
    SecurityHeadersMiddleware,
)
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
    # Мягкий per-IP лимит запросов (PR-9); health-эндпоинты не лимитируются.
    # Активен только в staging/production, чтобы не мешать локальной работе и CI.
    rate_limit = settings.rate_limit_per_minute if settings.is_strict_env else 0
    app.add_middleware(RateLimitMiddleware, limit_per_minute=rate_limit)
    # Заголовки безопасности; HSTS — только вне development (за HTTPS-прокси).
    if settings.security_headers_enabled:
        app.add_middleware(SecurityHeadersMiddleware, hsts=settings.is_production)
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
    app.include_router(evidence.router)
    app.include_router(daily_report_ai.router)
    app.include_router(quality.router)
    app.include_router(risk_threshold.router)
    app.include_router(dashboards.router)
    app.include_router(attachments.router)
    app.include_router(communications.router)
    app.include_router(ai_provider.router)
    return app


app = create_app()
