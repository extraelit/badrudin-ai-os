"""Простой реестр отозванных токенов (T-1.C1).

Хранит идентификаторы (jti) отозванных при выходе токенов. На этапе фундамента —
внутрипроцессное хранилище; в T-1.F (Redis) заменяется на общее хранилище с TTL.
"""

from __future__ import annotations

_revoked: set[str] = set()


def revoke(jti: str) -> None:
    _revoked.add(jti)


def is_revoked(jti: str) -> bool:
    return jti in _revoked


def clear() -> None:
    """Очистка (используется в тестах)."""
    _revoked.clear()
