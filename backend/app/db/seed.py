"""Загрузка обезличенных тестовых данных для среды разработки (T-1.B8).

Данные читаются из database/fixtures/dev_seed.json. Реальные персональные данные
и секреты не используются (D-011). Загрузка предназначена только для сред
development/test.

Помимо справочников (организации, роли, права) загрузчик создаёт рабочий
бутстрап доступа: связки роль→право (`role_permissions`), демо-сотрудников,
демо-пользователей и связки пользователь→роль (`user_roles`). Пароль демо-
пользователей берётся из переменной окружения `SEED_DEMO_PASSWORD` (по умолчанию —
демо-значение только для development; в production обязателен свой). Пользователь
`system_owner` создаётся с включённой MFA (демо-секрет для локальной разработки).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Department,
    Employee,
    Organization,
    Permission,
    Position,
    Role,
    RolePermission,
    User,
    UserRole,
)

DEFAULT_FIXTURE = (
    Path(__file__).resolve().parents[3] / "database" / "fixtures" / "dev_seed.json"
)

# Демо-пароль по умолчанию (только для development; переопределяется окружением).
DEFAULT_DEMO_PASSWORD = "BadrudinDemo!2026"
# Демо-секрет TOTP для владельца системы (RFC 4648 тест-вектор; только для dev).
DEMO_OWNER_TOTP_SECRET = "JBSWY3DPEHPK3PXP"


def load_fixtures(session: Session, path: Path | None = None) -> dict[str, int]:
    """Загружает справочные тестовые данные и бутстрап доступа.

    Идемпотентность обеспечивается на уровне вызова (пустая БД). Возвращает число
    вставленных строк по каждой сущности.
    """
    data = json.loads((path or DEFAULT_FIXTURE).read_text(encoding="utf-8"))
    counts = {
        "organizations": 0, "roles": 0, "permissions": 0,
        "departments": 0, "positions": 0,
        "role_permissions": 0, "employees": 0, "users": 0, "user_roles": 0,
    }

    for row in data.get("organizations", []):
        session.add(Organization(**row))
        counts["organizations"] += 1
    for row in data.get("roles", []):
        session.add(Role(**row))
        counts["roles"] += 1
    for row in data.get("permissions", []):
        session.add(Permission(**row))
        counts["permissions"] += 1
    session.flush()

    # Организация по умолчанию — первая (демо-контур одной организации).
    org = session.execute(select(Organization)).scalars().first()
    roles = {r.code: r for r in session.execute(select(Role)).scalars()}
    perms = {p.code: p for p in session.execute(select(Permission)).scalars()}

    # Подразделения (по ссылке ref) — организационная структура.
    dept_by_ref: dict[str, Department] = {}
    for row in data.get("departments", []):
        ref = row.pop("ref", None)
        dept = Department(organization_id=org.id, **row)
        session.add(dept)
        session.flush()
        if ref:
            dept_by_ref[ref] = dept
        counts["departments"] += 1

    # Должности (по ссылке ref) — профиль должности с уровнем согласования.
    pos_by_ref: dict[str, Position] = {}
    for row in data.get("positions", []):
        ref = row.pop("ref", None)
        pos = Position(organization_id=org.id, **row)
        session.add(pos)
        session.flush()
        if ref:
            pos_by_ref[ref] = pos
        counts["positions"] += 1

    # Связки роль → право.
    for role_code, perm_codes in data.get("role_permissions", {}).items():
        role = roles.get(role_code)
        if role is None:
            continue
        for pc in perm_codes:
            perm = perms.get(pc)
            if perm is None:
                continue
            session.add(RolePermission(role_id=role.id, permission_id=perm.id))
            counts["role_permissions"] += 1
    session.flush()

    # Демо-сотрудники (по ссылке ref). Должность и подразделение — по своим ref.
    emp_by_ref: dict[str, Employee] = {}
    for row in data.get("employees", []):
        ref = row.pop("ref", None)
        dept_ref = row.pop("department_ref", None)
        pos_ref = row.pop("position_ref", None)
        dept = dept_by_ref.get(dept_ref) if dept_ref else None
        pos = pos_by_ref.get(pos_ref) if pos_ref else None
        emp = Employee(
            organization_id=org.id,
            department_id=dept.id if dept else None,
            position_id=pos.id if pos else None,
            **row,
        )
        session.add(emp)
        session.flush()
        if ref:
            emp_by_ref[ref] = emp
        counts["employees"] += 1

    # Демо-пользователи + связки пользователь → роль.
    demo_password = os.environ.get("SEED_DEMO_PASSWORD", DEFAULT_DEMO_PASSWORD)
    for row in data.get("users", []):
        emp = emp_by_ref.get(row.get("employee_ref", ""))
        mfa = bool(row.get("mfa"))
        user = User(
            email=row["email"],
            password_hash=hash_password(demo_password),
            status="active",
            employee_id=emp.id if emp else None,
            mfa_enabled=mfa,
            mfa_secret=DEMO_OWNER_TOTP_SECRET if mfa else None,
        )
        session.add(user)
        session.flush()
        counts["users"] += 1
        role = roles.get(row.get("role", ""))
        if role is not None:
            session.add(UserRole(user_id=user.id, role_id=role.id))
            counts["user_roles"] += 1

    session.commit()
    return counts


def is_seeded(session: Session) -> bool:
    """Признак того, что демо-данные уже загружены (есть хотя бы одна организация)."""
    return (
        session.execute(select(Organization.id).limit(1)).scalars().first() is not None
    )


def seed_if_empty(
    session: Session, path: Path | None = None
) -> dict[str, int] | None:
    """Безопасно (идемпотентно) загружает демо-данные только в пустую БД.

    Возвращает счётчики вставленных строк или `None`, если БД уже засеяна —
    повторный запуск не создаёт дубликатов.
    """
    if is_seeded(session):
        return None
    return load_fixtures(session, path)


# Окружения, в которых сидирование разрешено без явного подтверждения.
SEEDABLE_ENVIRONMENTS = ("development", "test")


def main(argv: list[str] | None = None) -> int:
    """CLI безопасного сидирования: `python -m app.db.seed`.

    По умолчанию работает только в development/test и идемпотентно (пропускает уже
    засеянную БД). Флаг `--force` разрешает загрузку вне dev/test осознанно.
    """
    parser = argparse.ArgumentParser(
        prog="python -m app.db.seed",
        description="Безопасная загрузка обезличенных демо-данных (dev/test).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Разрешить сидирование вне окружений development/test.",
    )
    args = parser.parse_args(argv)

    # Импорт здесь, чтобы импорт модуля в тестах не создавал движок БД.
    from app.core.config import get_settings
    from app.db.session import SessionLocal

    settings = get_settings()
    env = settings.app_env.strip().lower()
    if env not in SEEDABLE_ENVIRONMENTS and not args.force:
        print(
            f"Отказано: сидирование в окружении '{settings.app_env}' запрещено. "
            f"Используйте --force осознанно.",
            file=sys.stderr,
        )
        return 2

    session = SessionLocal()
    try:
        result = seed_if_empty(session)
    finally:
        session.close()

    if result is None:
        print("Демо-данные уже загружены — пропуск (идемпотентно).")
    else:
        print(f"Демо-данные загружены: {result}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
