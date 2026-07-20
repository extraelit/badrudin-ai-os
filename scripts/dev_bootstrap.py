#!/usr/bin/env python3
"""Локальный бутстрап Badrudin AI OS: секреты → миграции → безопасное сидирование.

Кроссплатформенный (Windows / macOS / Linux). Один шаг вместо ручного запуска
`alembic` и загрузки фикстур. Запускать из корня репозитория:

    python scripts/dev_bootstrap.py

Что делает по порядку:
1. подхватывает переменные из `.env` (не переопределяя уже заданные в окружении);
2. проверяет обязательные секреты (`app.core.preflight`) — при небезопасной
   конфигурации в staging/production завершается с ошибкой;
3. применяет миграции БД (`alembic upgrade head`);
4. в development/test идемпотентно загружает обезличенные демо-данные.

Скрипт ничего не отправляет во внешние сервисы и не хранит секретов.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"


def load_dotenv(path: Path) -> None:
    """Минимальный загрузчик `.env` без внешних зависимостей.

    Значения уже заданные в окружении имеют приоритет (не перезаписываются).
    Поддерживаются строчные комментарии (`KEY=value  # comment`) и кавычки.
    """
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip()
        # строчный комментарий отделяется пробелом+'#' у не закавыченных значений
        if value[:1] not in {'"', "'"} and " #" in value:
            value = value.split(" #", 1)[0].rstrip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def main() -> int:
    load_dotenv(ROOT / ".env")
    sys.path.insert(0, str(BACKEND))

    from app.core.config import get_settings
    from app.core.preflight import SecretValidationError, check_required_secrets

    settings = get_settings()

    # 1) секреты
    try:
        check_required_secrets(settings)
    except SecretValidationError as exc:
        print(f"[bootstrap] ОШИБКА секретов: {exc}", file=sys.stderr)
        return 2

    # 2) миграции
    from alembic import command
    from alembic.config import Config

    print("[bootstrap] Применение миграций (alembic upgrade head)…")
    alembic_cfg = Config(str(ROOT / "alembic.ini"))
    command.upgrade(alembic_cfg, "head")

    # 3) безопасное сидирование (dev/test, идемпотентно)
    env = settings.app_env.strip().lower()
    if env in ("development", "test"):
        from app.db.seed import seed_if_empty
        from app.db.session import SessionLocal

        session = SessionLocal()
        try:
            result = seed_if_empty(session)
        finally:
            session.close()
        if result is None:
            print("[bootstrap] Демо-данные уже загружены — пропуск.")
        else:
            print(f"[bootstrap] Демо-данные загружены: {result}")
    else:
        print(
            f"[bootstrap] Окружение '{settings.app_env}': "
            "сидирование пропущено (только для development/test)."
        )

    print("[bootstrap] Готово.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
