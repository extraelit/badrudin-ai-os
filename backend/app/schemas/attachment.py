"""Схемы универсальных вложений (PR-1)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AttachmentIn(BaseModel):
    entity_type: str = Field(max_length=48)
    entity_id: uuid.UUID
    original_name: str = Field(max_length=512)
    content_base64: str = Field(description="Содержимое файла в base64")
    mime_type: str | None = Field(default=None, max_length=128)
    attachment_type: str = Field(default="document", max_length=48)
    description: str | None = None
    project_id: uuid.UUID | None = None
    replaces_id: uuid.UUID | None = Field(
        default=None, description="ID заменяемого вложения (новая версия)"
    )


class AttachmentOut(BaseModel):
    id: uuid.UUID
    file_id: uuid.UUID
    entity_type: str
    entity_id: uuid.UUID
    project_id: uuid.UUID | None
    attachment_type: str
    description: str | None
    original_name: str
    mime_type: str | None
    size_bytes: int | None
    checksum_sha256: str | None
    version: int
    is_current: bool
    is_archived: bool
    uploaded_by: uuid.UUID | None
    created_at: datetime


class ArchiveIn(BaseModel):
    reason: str = Field(min_length=1, max_length=512)
