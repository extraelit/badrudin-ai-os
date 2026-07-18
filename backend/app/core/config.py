"""Конфигурация backend через переменные окружения (Pydantic settings).

Значения читаются из окружения / файла .env (D-008; ARCHITECTURE.md раздел 12.3).
Секреты в код не помещаются; в репозитории — только .env.example (T-1.A2).
"""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Настройки приложения, считываемые из окружения."""

    app_name: str = "Badrudin AI OS"
    app_env: str = "development"  # development | test | staging | production
    app_debug: bool = True

    backend_host: str = "0.0.0.0"
    backend_port: int = 8000

    # Объектное хранилище MinIO (D-008)
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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # прочие переменные окружения (БД, Redis и т. д.) игнорируются здесь
    )


@lru_cache
def get_settings() -> Settings:
    """Возвращает кэшированный экземпляр настроек."""
    return Settings()
