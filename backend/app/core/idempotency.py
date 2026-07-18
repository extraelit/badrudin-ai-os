"""Идемпотентность изменяющих операций (T-1.F3).

Защищает от двойной отправки мобильной формы и повторной обработки
(ARCHITECTURE.md раздел 13; DATABASE.md раздел 24). На этапе фундамента —
внутрипроцессное хранилище ключей; в проде заменяется на Redis с TTL (D-008).
"""

from __future__ import annotations

_seen: set[str] = set()


def try_acquire(key: str) -> bool:
    """Возвращает True, если ключ встречается впервые (операцию нужно выполнить).

    При повторном ключе возвращает False — операция уже обработана.
    """
    if not key:
        raise ValueError("Пустой ключ идемпотентности")
    if key in _seen:
        return False
    _seen.add(key)
    return True


def clear() -> None:
    """Очистка (используется в тестах)."""
    _seen.clear()
