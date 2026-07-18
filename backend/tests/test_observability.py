"""Тесты наблюдаемости: логирование и статус интеграций (T-1.G3)."""

import logging

from app.core.logging import RequestIDFilter, configure_logging


def test_configure_logging_sets_handler() -> None:
    configure_logging()
    assert logging.getLogger().handlers


def test_request_id_filter_adds_attribute() -> None:
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "msg", None, None)
    assert RequestIDFilter().filter(record) is True
    assert hasattr(record, "request_id")


def test_status_endpoint(client) -> None:
    resp = client.get("/health/status")
    assert resp.status_code == 200
    components = resp.json()["components"]
    assert components["database"] is True
    assert components["object_storage"] is True
