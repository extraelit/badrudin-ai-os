"""HTTP-middleware: сквозной идентификатор запроса (T-1.G2).

Каждый запрос получает correlation_id (заголовок X-Request-ID). Идентификатор
доступен обработчикам (request.state), журналу (contextvar) и возвращается
клиенту в ответе (ARCHITECTURE.md раздел 13).
"""

from __future__ import annotations

import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request

from app.core.context import request_id_ctx

HEADER = "X-Request-ID"


class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get(HEADER) or uuid.uuid4().hex
        request.state.request_id = request_id
        token = request_id_ctx.set(request_id)
        try:
            response = await call_next(request)
        finally:
            request_id_ctx.reset(token)
        response.headers[HEADER] = request_id
        return response
