"""Тесты идемпотентности (T-1.F3)."""

import pytest

from app.core import idempotency


def test_duplicate_key_detected() -> None:
    idempotency.clear()
    assert idempotency.try_acquire("form-123") is True  # первый раз — выполнить
    assert idempotency.try_acquire("form-123") is False  # повтор — пропустить
    assert idempotency.try_acquire("form-456") is True


def test_empty_key_rejected() -> None:
    with pytest.raises(ValueError):
        idempotency.try_acquire("")
