"""Конфигурация backend через переменные окружения (Pydantic settings).

Значения читаются из окружения / файла .env (D-008; ARCHITECTURE.md раздел 12.3).
Секреты в код не помещаются; в репозитории — только .env.example (T-1.A2).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Корень репозитория: backend/app/core/config.py -> parents[3].
# Нужен, чтобы `.env` и относительный путь файла SQLite резолвились одинаково
# независимо от рабочего каталога процесса: бутстрап запускается из корня, а
# uvicorn — из backend/ (DOCS/LOCAL_RUN.md). Без этой привязки приложение читало
# бы `.env`/БД из другого каталога и не видело бы сидированные данные.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    """Настройки приложения, считываемые из окружения."""

    app_name: str = "Badrudin AI OS"
    app_env: str = "development"  # development | test | staging | production
    app_debug: bool = True

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Разрешённые источники для CORS (интерфейс Next.js обращается к API из браузера).
    # Список через запятую; задаётся окружением для staging/production.
    cors_allow_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    # Файловое хранилище. Бэкенд выбирается окружением:
    #   local — локальная файловая система (разработка/тесты, реально пишет байты);
    #   s3    — S3-совместимое (MinIO/AWS S3) для staging/production.
    # Ключи S3 задаются только через окружение/secret manager, не в Git.
    storage_backend: str = "local"  # local | s3
    # Каталог локального хранилища. По умолчанию — вне репозитория (системный temp),
    # чтобы разработка/тесты не засоряли рабочее дерево; в production задаётся явно.
    local_storage_dir: str | None = None
    # Коммуникации: главный рубильник реальной отправки. По умолчанию ВЫКЛЮЧЕН —
    # работает безопасный sandbox без внешних вызовов. Реальная отправка возможна
    # только при comm_real_send=true И настроенных ключах канала (из окружения).
    comm_real_send: bool = False
    # SMTP (канал email, PR-3). Значения — только из окружения/secret manager.
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = ""
    smtp_use_tls: bool = True
    smtp_timeout_seconds: int = 20
    # Telegram Bot API (канал telegram, PR-4). Токен и секрет вебхука — из
    # окружения/secret manager. Без токена реальная отправка не выполняется.
    telegram_bot_token: str = ""
    telegram_webhook_secret: str = ""
    telegram_api_base: str = "https://api.telegram.org"

    # S3-совместимое хранилище (MinIO/AWS S3, D-008)
    minio_endpoint: str = "minio:9000"
    minio_access_key: str = "change-me"
    minio_secret_key: str = "change-me"
    minio_bucket: str = "badrudin-files"
    minio_region: str = "ru-central"
    minio_use_ssl: bool = False
    # ограничения загрузок (T-1.E2)
    max_upload_bytes: int = 104857600  # 100 МБ
    allowed_upload_mime: str = (
        "image/jpeg,image/png,image/heic,image/webp,video/mp4,video/quicktime,"
        "application/pdf,application/msword,"
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document,"
        "application/vnd.ms-excel,"
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

    # Подключение к базе данных (D-004: PostgreSQL). Значение берётся из окружения.
    database_url: str = (
        "postgresql+psycopg://badrudin:change-me@localhost:5432/badrudin"
    )

    # Redis / Celery (D-008)
    redis_url: str = "redis://redis:6379/0"
    celery_broker_url: str = "redis://redis:6379/1"
    celery_result_backend: str = "redis://redis:6379/2"

    # Аутентификация / JWT. Секрет задаётся через окружение (не хранится в коде).
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 30
    refresh_token_expire_days: int = 14
    max_failed_logins: int = 5
    lockout_minutes: int = 15
    # Роли, для которых обязательна MFA (ACCESS_CONTROL.md раздел 19)
    mfa_required_roles: str = (
        "system_owner,general_director,executive_director,accountant,"
        "finance_director,administrator"
    )

    # WebAuthn / FIDO2 passkey (персональные аппаратные/платформенные ключи).
    # RP ID — домен без схемы и порта; origin — полный источник фронтенда.
    webauthn_rp_id: str = "localhost"
    webauthn_rp_name: str = "Badrudin AI OS"
    webauthn_rp_origin: str = "http://localhost:3000"

    @field_validator("database_url")
    @classmethod
    def _anchor_sqlite_path(cls, value: str) -> str:
        """Привязывает относительный файловый путь SQLite к корню репозитория.

        Иначе `sqlite+pysqlite:///./badrudin_local.db` указывал бы на разные
        файлы в зависимости от рабочего каталога (бутстрап из корня vs uvicorn
        из backend/), и приложение не видело бы сидированную БД. На PostgreSQL,
        а также на абсолютные и in-memory пути не влияет.
        """
        marker = ":///"
        idx = value.find(marker)
        if not value.startswith("sqlite") or idx == -1:
            return value
        scheme, path_part = value[: idx + len(marker)], value[idx + len(marker) :]
        if not path_part or path_part == ":memory:" or path_part.startswith("/"):
            return value
        return f"{scheme}{(_REPO_ROOT / path_part).resolve()}"

    model_config = SettingsConfigDict(
        # Абсолютный путь к `.env` в корне репозитория: файл находится независимо
        # от рабочего каталога процесса (см. комментарий к _REPO_ROOT).
        env_file=_REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # прочие переменные окружения (БД, Redis и т. д.) игнорируются здесь
    )


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()
