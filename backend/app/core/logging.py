"""Настройка структурного логирования (T-1.G3).

Каждая запись журнала дополняется идентификатором запроса (correlation_id),
что обеспечивает трассировку (ARCHITECTURE.md разделы 13, 14). Секреты и
персональные данные в журнал не помещаются.
"""

from __future__ import annotations

import logging

from app.core.context import get_request_id
from app.core.secrets import SecretMaskingFilter


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id() or "-"
        return True


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.addFilter(RequestIDFilter())
    handler.addFilter(SecretMaskingFilter())
    handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)s [%(name)s] [req=%(request_id)s] %(message)s"
        )
    )
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level)
