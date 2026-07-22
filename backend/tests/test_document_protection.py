"""Тесты защиты целостности документов после утверждения (этап 1).

Проверяют: утверждение версии блокирует версию, файл-носитель и документ и
делает версию текущей; заблокированные файл/версия/документ нельзя удалить на
уровне сессии; изменить содержание можно только новой версией; документ
архивируется, а не удаляется; каждое действие фиксируется в аудите.
"""

from __future__ import annotations

import uuid

import pytest

from app.models import (
    AuditEvent,
    Document,
    DocumentVersion,
    File,
    Organization,
)
from app.models.content import DocumentIntegrityError as ModelIntegrityError
from app.services.documents import (
    DocumentIntegrityError,
    approve_version,
    archive_document,
    assert_version_editable,
    create_new_version,
)


def _doc_with_version(session):
    org = Organization(legal_name="ТЕСТ")
    session.add(org)
    session.flush()
    file = File(
        organization_id=org.id,
        storage_key="k/1",
        original_name="акт.pdf",
        checksum_sha256="a" * 64,
    )
    session.add(file)
    session.flush()
    doc = Document(organization_id=org.id, title="Акт скрытых работ")
    session.add(doc)
    session.flush()
    version = create_new_version(
        session, doc.id, file_id=file.id, change_summary="исходная", commit=True
    )
    return org, doc, version, file


# ---------------------------------------------------------------------------
# Утверждение блокирует и делает текущей
# ---------------------------------------------------------------------------

def test_approve_locks_version_file_and_document(db_session) -> None:
    _, doc, version, file = _doc_with_version(db_session)
    approver = uuid.uuid4()
    approve_version(db_session, version.id, approver_id=approver)

    db_session.refresh(version)
    db_session.refresh(file)
    db_session.refresh(doc)
    assert version.status == "approved"
    assert version.locked_at is not None and version.locked_by == approver
    assert file.locked_at is not None  # файл-носитель заблокирован
    assert doc.current_version_id == version.id
    assert doc.status == "approved"
    assert doc.locked_at is not None


def test_double_approve_rejected(db_session) -> None:
    _, _, version, _ = _doc_with_version(db_session)
    approve_version(db_session, version.id)
    with pytest.raises(DocumentIntegrityError):
        approve_version(db_session, version.id)


# ---------------------------------------------------------------------------
# Заблокированное нельзя удалить
# ---------------------------------------------------------------------------

def test_locked_file_cannot_be_deleted(db_session) -> None:
    _, _, version, file = _doc_with_version(db_session)
    approve_version(db_session, version.id)
    db_session.refresh(file)
    db_session.delete(file)
    with pytest.raises(ModelIntegrityError):
        db_session.flush()
    db_session.rollback()


def test_locked_version_cannot_be_deleted(db_session) -> None:
    _, _, version, _ = _doc_with_version(db_session)
    approve_version(db_session, version.id)
    db_session.refresh(version)
    db_session.delete(version)
    with pytest.raises(ModelIntegrityError):
        db_session.flush()
    db_session.rollback()


def test_unlocked_draft_version_can_be_deleted(db_session) -> None:
    _, doc, version, _ = _doc_with_version(db_session)
    # черновик (не утверждён) удаляется свободно
    db_session.delete(version)
    db_session.flush()
    assert db_session.get(DocumentVersion, version.id) is None


# ---------------------------------------------------------------------------
# Изменение только новой версией; редактирование утверждённой запрещено
# ---------------------------------------------------------------------------

def test_new_version_increments_and_keeps_old_intact(db_session) -> None:
    _, doc, v1, _ = _doc_with_version(db_session)
    approve_version(db_session, v1.id)
    v2 = create_new_version(db_session, doc.id, change_summary="правка")
    assert v2.version_number == v1.version_number + 1
    assert v2.status == "draft"
    # прежняя утверждённая версия не изменилась
    db_session.refresh(v1)
    assert v1.status == "approved" and v1.locked_at is not None


def test_assert_editable_guards_approved_version(db_session) -> None:
    _, _, version, _ = _doc_with_version(db_session)
    assert_version_editable(version)  # черновик — ок
    approve_version(db_session, version.id)
    db_session.refresh(version)
    with pytest.raises(DocumentIntegrityError):
        assert_version_editable(version)


# ---------------------------------------------------------------------------
# Архивирование вместо удаления + аудит
# ---------------------------------------------------------------------------

def test_archive_marks_document_without_deleting(db_session) -> None:
    _, doc, _, _ = _doc_with_version(db_session)
    archive_document(db_session, doc.id)
    db_session.refresh(doc)
    assert doc.is_archived is True
    assert db_session.get(Document, doc.id) is not None  # запись сохранена


def test_approval_and_archive_recorded_in_audit(db_session) -> None:
    _, doc, version, _ = _doc_with_version(db_session)
    approve_version(db_session, version.id)
    archive_document(db_session, doc.id)
    actions = {
        e.action
        for e in db_session.query(AuditEvent).all()
    }
    assert "document.version.approve" in actions
    assert "document.archive" in actions
