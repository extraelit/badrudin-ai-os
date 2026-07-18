"""Загрузка обезличенных тестовых данных для среды разработки (T-1.B8).

Данные читаются из database/fixtures/dev_seed.json. Реальные персональные данные
и секреты не используются (D-011). Загрузка предназначена только для сред
development/test.
"""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy.orm import Session

from app.models import Organization, Permission, Role

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[3] / "database" / "fixtures" / "dev_seed.json"
)


def load_fixtures(session: Session, path: Path | None = None) -> dict[str, int]:
    """Загружает справочные тестовые данные. Возвращает число вставленных строк."""
    data = json.loads((path or DEFAULT_FIXTURE).read_text(encoding="utf-8"))
    counts = {"organizations": 0, "roles": 0, "permissions": 0}

    for row in data.get("organizations", []):
        session.add(Organization(**row))
        counts["organizations"] += 1
    for row in data.get("roles", []):
        session.add(Role(**row))
        counts["roles"] += 1
    for row in data.get("permissions", []):
        session.add(Permission(**row))
        counts["permissions"] += 1

    session.commit()
    return counts
