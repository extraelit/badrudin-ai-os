"""Сервис резервных кодов восстановления MFA (этап 1).

Коды одноразовые и хранятся только в виде хеша. При генерации выдаётся новый
комплект, а прежние неиспользованные коды аннулируются (используются последние
выданные). Проверка кода при успехе помечает его использованным (`used_at`),
поэтому повторно тот же код не сработает.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.security import hash_password, verify_password
from app.models import MfaRecoveryCode

# Кол-во кодов в комплекте и алфавит без легко путаемых символов (без 0/O/1/I/L).
DEFAULT_CODE_COUNT = 10
_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
_GROUP = 4  # символов в группе


def _now() -> datetime:
    return datetime.now(UTC)


def normalize_code(code: str) -> str:
    """Приводит код к канону: без разделителей/пробелов, в верхнем регистре."""
    return "".join(ch for ch in code.strip().upper() if ch.isalnum())


def _random_code() -> str:
    raw = "".join(secrets.choice(_ALPHABET) for _ in range(_GROUP * 2))
    return f"{raw[:_GROUP]}-{raw[_GROUP:]}"


def generate_recovery_codes(
    session: Session, user_id: uuid.UUID, count: int = DEFAULT_CODE_COUNT
) -> list[str]:
    """Создаёт новый комплект кодов, аннулируя прежние неиспользованные.

    Возвращает коды в открытом виде (показываются пользователю один раз). В БД
    сохраняются только их хеши.
    """
    # аннулируем прежние ещё не использованные коды (перевыпуск заменяет комплект)
    now = _now()
    for row in session.execute(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
    ).scalars():
        row.used_at = now

    codes: list[str] = []
    for _ in range(count):
        code = _random_code()
        codes.append(code)
        session.add(
            MfaRecoveryCode(
                user_id=user_id,
                code_hash=hash_password(normalize_code(code)),
            )
        )
    session.commit()
    return codes


def remaining_count(session: Session, user_id: uuid.UUID) -> int:
    """Число ещё не использованных кодов пользователя."""
    rows = session.execute(
        select(MfaRecoveryCode.id).where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
    ).all()
    return len(rows)


def verify_and_consume(session: Session, user_id: uuid.UUID, code: str) -> bool:
    """Проверяет код против неиспользованных и при совпадении помечает использованным.

    Возвращает True при успешном погашении, иначе False. Пустой код не проходит.
    """
    candidate = normalize_code(code)
    if not candidate:
        return False
    for row in session.execute(
        select(MfaRecoveryCode).where(
            MfaRecoveryCode.user_id == user_id,
            MfaRecoveryCode.used_at.is_(None),
        )
    ).scalars():
        if verify_password(candidate, row.code_hash):
            row.used_at = _now()
            session.commit()
            return True
    return False
