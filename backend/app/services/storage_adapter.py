"""Абстракция файлового хранилища: локальный и S3-совместимый адаптеры (PR-1).

Бизнес-логика не завязана на конкретное хранилище (ARCHITECTURE.md: замена
поставщика). Выбор бэкенда — через `settings.storage_backend`:

* ``local`` — локальная файловая система. Реально пишет байты на диск; ссылка на
  скачивание отдаётся не напрямую, а через API-эндпоинт (``presigned_url`` → None).
  Каталог по умолчанию вне репозитория (системный temp), чтобы разработка и тесты
  не засоряли рабочее дерево; в production задаётся ``LOCAL_STORAGE_DIR``.
* ``s3`` — S3-совместимое хранилище (MinIO/AWS S3). Ключи — только через окружение.

Ни один адаптер не удаляет объекты по умолчанию (архивирование вместо удаления —
решение на уровне сервиса вложений). Метод ``delete`` оставлен для будущих задач
обслуживания и в обычном потоке не используется.
"""

from __future__ import annotations

import io
import os
import tempfile
from pathlib import Path
from typing import Protocol

from app.core.config import get_settings


class StorageError(RuntimeError):
    """Ошибка операции с хранилищем (запись/чтение объекта)."""


class StorageAdapter(Protocol):
    """Единый контракт хранилища объектов."""

    provider: str

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        """Сохраняет объект под ключом ``key`` (идемпотентно перезаписывает)."""

    def open(self, key: str) -> bytes:
        """Возвращает содержимое объекта; бросает ``StorageError`` при отсутствии."""

    def exists(self, key: str) -> bool:
        """Проверяет наличие объекта."""

    def presigned_url(self, key: str, expires_minutes: int = 15) -> str | None:
        """Временная ссылка на скачивание или ``None`` (тогда скачивание — через API)."""


def _default_local_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "badrudin_storage")


class LocalStorageAdapter:
    """Локальное файловое хранилище для разработки и тестов (реально пишет байты)."""

    provider = "local"

    def __init__(self, base_dir: str | None = None) -> None:
        self.base_dir = Path(base_dir or _default_local_dir()).resolve()

    def _path(self, key: str) -> Path:
        # Ключи формируются системой (uuid-имена), но на всякий случай не выпускаем
        # путь за пределы базового каталога (защита от traversal).
        target = (self.base_dir / key).resolve()
        if not str(target).startswith(str(self.base_dir)):
            raise StorageError("Недопустимый ключ хранения")
        return target

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def open(self, key: str) -> bytes:
        path = self._path(key)
        if not path.is_file():
            raise StorageError(f"Объект не найден: {key}")
        return path.read_bytes()

    def exists(self, key: str) -> bool:
        return self._path(key).is_file()

    def presigned_url(self, key: str, expires_minutes: int = 15) -> str | None:
        return None  # локально скачивание идёт через API-эндпоинт


class S3StorageAdapter:
    """S3-совместимое хранилище (MinIO/AWS S3) для staging/production."""

    provider = "s3"

    def __init__(self) -> None:
        from minio import Minio  # локальный импорт: не нужен для local-бэкенда

        settings = get_settings()
        self._bucket = settings.minio_bucket
        self._client = Minio(
            settings.minio_endpoint,
            access_key=settings.minio_access_key,
            secret_key=settings.minio_secret_key,
            secure=settings.minio_use_ssl,
            region=settings.minio_region,
        )

    def put(self, key: str, data: bytes, content_type: str | None = None) -> None:
        self._client.put_object(
            self._bucket, key, io.BytesIO(data), length=len(data),
            content_type=content_type or "application/octet-stream",
        )

    def open(self, key: str) -> bytes:
        try:
            resp = self._client.get_object(self._bucket, key)
            try:
                return resp.read()
            finally:
                resp.close()
                resp.release_conn()
        except Exception as exc:  # noqa: BLE001 — оборачиваем в доменную ошибку
            raise StorageError(f"Не удалось прочитать объект: {key}") from exc

    def exists(self, key: str) -> bool:
        try:
            self._client.stat_object(self._bucket, key)
            return True
        except Exception:  # noqa: BLE001
            return False

    def presigned_url(self, key: str, expires_minutes: int = 15) -> str | None:
        from datetime import timedelta

        return self._client.presigned_get_object(
            self._bucket, key, expires=timedelta(minutes=expires_minutes)
        )


def get_storage_adapter() -> StorageAdapter:
    """Возвращает адаптер согласно конфигурации (без кэша: учитывает смену env)."""
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3StorageAdapter()
    return LocalStorageAdapter(settings.local_storage_dir)
