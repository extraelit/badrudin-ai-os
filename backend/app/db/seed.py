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

import json
import os
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password
from app.models import (
    Employee,
    Organization,
    Permission,
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

    # Демо-сотрудники (по ссылке ref).
    emp_by_ref: dict[str, Employee] = {}
    for row in data.get("employees", []):
        ref = row.pop("ref", None)
        emp = Employee(organization_id=org.id, **row)
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
