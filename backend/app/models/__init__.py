"""Реестр моделей данных.

Импорт модулей моделей здесь обеспечивает регистрацию таблиц в
`Base.metadata` (используется Alembic для миграций). Модели добавляются
задачами блока 1.B по мере реализации.
"""

from app.db.base import Base
from app.models.organization import (
    Department,
    Employee,
    Organization,
    Position,
)
from app.models.user import User

__all__ = [
    "Base",
    "Organization",
    "Department",
    "Position",
    "Employee",
    "User",
]
