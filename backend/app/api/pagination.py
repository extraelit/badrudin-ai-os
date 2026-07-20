"""Общая пагинация списков (§13 «пагинация больших списков», §25 «ограничивать
размер ответов»).

Пагинация аддитивна и безопасна: по умолчанию (`limit=None`, `offset=0`) поведение
не меняется — возвращается весь список, поэтому существующие клиенты не ломаются и
данные не обрезаются молча. Клиент может явно запросить страницу через `limit`
(1..200) и `offset` (>=0); недопустимые значения отклоняются с 422 на границе API.

Срез выполняется в памяти уже после применения ABAC-фильтрации по доступным
объектам, чтобы страница считалась от данных, которые пользователь реально может
видеть, а не от «сырого» результата запроса.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeVar

from fastapi import Query

T = TypeVar("T")

MAX_LIMIT = 200


@dataclass(frozen=True)
class PageParams:
    limit: int | None
    offset: int


def page_params(
    limit: int | None = Query(
        None, ge=1, le=MAX_LIMIT,
        description="Максимум элементов на странице (1..200). По умолчанию — без ограничения.",
    ),
    offset: int = Query(0, ge=0, description="Смещение от начала списка."),
) -> PageParams:
    return PageParams(limit=limit, offset=offset)


def paginate(items: list[T], params: PageParams) -> list[T]:
    """Возвращает срез списка согласно параметрам страницы (аддитивно и безопасно)."""
    if params.offset:
        items = items[params.offset:]
    if params.limit is not None:
        items = items[: params.limit]
    return items
