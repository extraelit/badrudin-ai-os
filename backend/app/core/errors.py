"""Единый формат ошибок API (T-1.G1).

Пользователю возвращается понятное сообщение; технические детали и секреты в
ответ не попадают (ARCHITECTURE.md раздел 13; CLAUDE.md раздел 24). Детали
внутренних ошибок пишутся в журнал, а не отдаются клиенту.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger("app.errors")


def _payload(code: str, message: str, request: Request) -> dict:
    request_id = getattr(request.state, "request_id", None)
    return {"error": {"code": code, "message": message, "request_id": request_id}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(request: Request, exc: StarletteHTTPException):
        code = {401: "unauthorized", 403: "forbidden", 404: "not_found"}.get(
            exc.status_code, "http_error"
        )
        return JSONResponse(
            status_code=exc.status_code,
            content=_payload(code, str(exc.detail), request),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=_payload(
                "validation_error", "Ошибка проверки входных данных", request
            ),
        )

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # детали — только в журнал, клиенту — общее сообщение без утечки
        logger.exception("Необработанная ошибка запроса", exc_info=exc)
        return JSONResponse(
            status_code=500,
            content=_payload("internal_error", "Внутренняя ошибка сервера", request),
        )
