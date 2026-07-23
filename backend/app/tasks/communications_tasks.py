"""Фоновые задачи отправки коммуникаций (PR-9).

Идемпотентная отправка сообщений и рассылок через очередь: повторный вызов не
создаёт дубль отправки (защита от двойного проведения). В dev/test выполняется
синхронно (Celery eager); реальный брокер не требуется.
"""

from __future__ import annotations

import uuid

from app.db.session import SessionLocal
from app.models import Broadcast, CommunicationMessage
from app.services import broadcasts as bsvc
from app.services import communications as comm
from app.tasks.celery_app import celery_app


@celery_app.task(name="communications.dispatch_message", bind=True, max_retries=3)
def dispatch_message(self, message_id: str, actor_user_id: str | None = None) -> str:
    """Отправляет сообщение идемпотентно. Возвращает итоговый статус."""
    db = SessionLocal()
    try:
        msg = db.get(CommunicationMessage, uuid.UUID(message_id))
        if msg is None:
            return "not_found"
        actor = uuid.UUID(actor_user_id) if actor_user_id else msg.approved_by_user_id
        comm.dispatch_idempotent(db, msg, actor_user_id=actor or msg.author_user_id)
        db.commit()
        return msg.status
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise self.retry(exc=exc, countdown=30) if not celery_app.conf.task_always_eager else exc
    finally:
        db.close()


@celery_app.task(name="communications.dispatch_broadcast", bind=True, max_retries=3)
def dispatch_broadcast(self, broadcast_id: str, actor_user_id: str) -> str:
    """Отправляет рассылку идемпотентно (уже отправленная не рассылается повторно)."""
    db = SessionLocal()
    try:
        b = db.get(Broadcast, uuid.UUID(broadcast_id))
        if b is None:
            return "not_found"
        if b.status == "sent":
            return "already_sent"
        bsvc.dispatch_broadcast(db, b, actor_user_id=uuid.UUID(actor_user_id))
        db.commit()
        return b.status
    except Exception as exc:  # noqa: BLE001
        db.rollback()
        raise self.retry(exc=exc, countdown=30) if not celery_app.conf.task_always_eager else exc
    finally:
        db.close()
