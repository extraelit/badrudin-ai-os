"""Временное хранилище WebAuthn-челленджей между begin и complete.

Челлендж выдаётся на шаге `begin` и проверяется на шаге `complete`. Хранится
кратковременно (TTL) в памяти процесса и удаляется при использовании (одноразовый).

Ограничение: хранилище процессное; при нескольких воркерах требуется общий кэш
(Redis) — вынести при горизонтальном масштабировании. Для контура этапа 1
достаточно процессного хранилища с TTL.
"""

from __future__ import annotations

import time

# ключ (str) -> (challenge_bytes, expires_at_epoch)
_STORE: dict[str, tuple[bytes, float]] = {}
DEFAULT_TTL_SECONDS = 300


def _purge(now: float) -> None:
    for key in [k for k, (_, exp) in _STORE.items() if exp < now]:
        _STORE.pop(key, None)


def put(key: str, challenge: bytes, ttl: int = DEFAULT_TTL_SECONDS) -> None:
    now = time.time()
    _purge(now)
    _STORE[key] = (challenge, now + ttl)


def take(key: str) -> bytes | None:
    """Возвращает и удаляет челлендж (одноразовый). None — если нет или истёк."""
    now = time.time()
    item = _STORE.pop(key, None)
    if item is None:
        return None
    challenge, exp = item
    if exp < now:
        return None
    return challenge


def clear() -> None:
    _STORE.clear()
