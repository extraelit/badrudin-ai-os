"""HTTP-middleware: сквозной идентификатор запроса (T-1.G2).

Каждый запрос получает correlation_id (заголовок X-Request-ID). Идентификатор
доступен обработчикам (request.state), журналу (contextvar) и возвращается
клиенту в ответе (ARCHITECTURE.md раздел 13).
"""

from __future__ import annotations

import time
import uuid
from collections import defaultdict, deque

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

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


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Заголовки безопасности (PR-9). HSTS добавляется только вне development."""

    def __init__(self, app, *, hsts: bool = False) -> None:
        super().__init__(app)
        self._hsts = hsts

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        if self._hsts:
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Мягкий per-IP лимит запросов в минуту (PR-9), in-memory скользящее окно.

    По умолчанию высокий предел, не мешающий обычной работе и тестам. При
    `limit <= 0` middleware пропускает все запросы. Health-эндпоинты не лимитируются.
    """

    def __init__(self, app, *, limit_per_minute: int = 600) -> None:
        super().__init__(app)
        self._limit = limit_per_minute
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    async def dispatch(self, request: Request, call_next):
        if self._limit <= 0 or request.url.path.startswith("/health"):
            return await call_next(request)
        client = request.client.host if request.client else "unknown"
        now = time.monotonic()
        window = self._hits[client]
        while window and now - window[0] > 60.0:
            window.popleft()
        if len(window) >= self._limit:
            return JSONResponse(
                status_code=429,
                content={"error": {"message": "Слишком много запросов, попробуйте позже"}},
                headers={"Retry-After": "60"},
            )
        window.append(now)
        return await call_next(request)
