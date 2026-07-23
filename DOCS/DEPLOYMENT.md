# Развёртывание Badrudin AI OS (production) — PR-9

Инструкция промышленного развёртывания. Секреты задаются **только** через
окружение/secret manager и никогда не коммитятся.

## 1. Требования

- Сервер Linux с Docker + Docker Compose (или Kubernetes).
- PostgreSQL 16, Redis 7, S3-совместимое хранилище (MinIO/AWS S3).
- Обратный прокси с TLS (nginx/Caddy/Traefik) — терминирует HTTPS.

## 2. Переменные окружения (обязательные в production)

Скопируйте `.env.example` → `.env` и задайте безопасные значения:

- `APP_ENV=production`, `APP_DEBUG=false`, `COOKIE_SECURE=true`.
- `SECRET_KEY`, `JWT_SECRET` — случайные ≥32 байт
  (`python -c "import secrets;print(secrets.token_urlsafe(48))"`).
- `DATABASE_URL=postgresql+psycopg://USER:PASS@HOST:5432/badrudin` (не SQLite).
- `REDIS_URL`, `CELERY_BROKER_URL`, `CELERY_RESULT_BACKEND`, `CELERY_TASK_ALWAYS_EAGER=false`.
- `STORAGE_BACKEND=s3` + `MINIO_ENDPOINT/ACCESS_KEY/SECRET_KEY/BUCKET`.
- `CORS_ALLOW_ORIGINS` — реальные домены фронтенда.
- `NEXT_PUBLIC_API_BASE_URL` — публичный URL API.

**Preflight** при старте (`app.core.preflight`) блокирует запуск в production при
заглушках секретов, SQLite, `STORAGE_BACKEND!=s3`, `APP_DEBUG=true`,
`COOKIE_SECURE=false`.

## 3. Запуск (Docker Compose, production-like)

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Поднимаются: PostgreSQL, Redis, MinIO, backend (миграции + API), worker (Celery),
frontend. Секреты — только из `.env` (в compose нет значений). Демо-данные в
production не загружаются.

## 4. Миграции

Backend при старте выполняет `alembic upgrade head`. Вручную:

```bash
docker compose -f docker-compose.prod.yml exec backend alembic upgrade head
```

## 5. HTTPS / обратный прокси

Терминируйте TLS на прокси и проксируйте: `/` → frontend:3000, `/…` API →
backend:8000. Включите HSTS на прокси (приложение также ставит security-заголовки).
Пробы оркестратора: liveness `GET /health`, readiness `GET /health/ready`
(проверяет БД, 200/503).

## 6. Фоновые очереди

Отправка коммуникаций/рассылок выполняется задачами Celery
(`app.tasks.communications_tasks`) идемпотентно — повтор не создаёт дубль
отправки. В production запускается сервис `worker`; в dev/test — синхронно
(`CELERY_TASK_ALWAYS_EAGER=true`). Реальная внешняя отправка остаётся выключенной,
пока не заданы ключи каналов и `COMM_REAL_SEND=true`.

## 7. Резервное копирование

Бэкап БД — скриптом `backend/scripts/backup.sh` (по расписанию cron). Храните
дампы и объектное хранилище в защищённом месте; проверяйте восстановление.

## 8. Безопасность

- Rate limiting (`RATE_LIMIT_PER_MINUTE`) — мягкий per-IP лимит.
- Заголовки: `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, HSTS.
- Секреты не логируются; журнал структурированный с request-id.

## Требует решения специалистов ООО «Экстра-Элит»

- Реальные значения секретов и ключей внешних сервисов; TLS-сертификаты; политика
  бэкапов и хранения; выбор оркестратора. Реальную инфраструктуру поднимает
  заказчик — в репозитории только конфигурация без секретов.
