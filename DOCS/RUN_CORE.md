# Запуск рабочего ядра Badrudin AI OS

Рабочее ядро — минимальный управленческий цикл (CLAUDE.md §31): вход → объекты и
проекты → задачи → согласование руководителем → исполнение → ежедневный отчёт →
сводка директора. Ядро реализовано и подключено «сквозняком»: интерфейс работает
через backend, без mock-данных в этом контуре.

## 1. Переменные окружения

Скопируйте `.env.example` в `.env` и задайте как минимум:

```
DATABASE_URL=postgresql+psycopg://badrudin:...@localhost:5432/badrudin
JWT_SECRET=<длинная случайная строка>
CORS_ALLOW_ORIGINS=http://localhost:3000
SEED_DEMO_PASSWORD=<пароль демо-пользователей, только для dev>
# frontend
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```

Для локальной проверки допустима SQLite: `DATABASE_URL=sqlite:////tmp/badrudin.db`
(и `ALEMBIC_DATABASE_URL` то же значение).

## 2. Миграции и тестовые данные

```bash
# из корня репозитория
ALEMBIC_DATABASE_URL=$DATABASE_URL alembic upgrade head

# загрузка обезличенных dev-данных и бутстрапа доступа
python -c "from sqlalchemy import create_engine; from sqlalchemy.orm import Session; \
from app.db.seed import load_fixtures; \
s=Session(create_engine('$DATABASE_URL')); print(load_fixtures(s))"
```

Загрузчик создаёт: права, связки роль→право, демо-сотрудников, демо-пользователей
и связки пользователь→роль.

## 3. Демо-учётные записи (только development)

| Логин | Роль | MFA | Назначение |
|---|---|---|---|
| `director@extra-elit.demo` | production_director | нет | рабочий вход для демонстрации цикла |
| `owner@extra-elit.demo` | system_owner | да | полный доступ (вход требует кода TOTP) |
| `foreman@extra-elit.demo` | foreman | нет | полевой сотрудник |

Пароль — значение `SEED_DEMO_PASSWORD` (по умолчанию — демо-значение из
`app/db/seed.py`, **только для development**; в production обязателен свой).
Владелец (`system_owner`) требует MFA (демо-секрет TOTP задаётся сидом только для
локальной разработки).

## 4. Запуск

```bash
# backend
uvicorn app.main:app --host 0.0.0.0 --port 8000
# frontend
cd frontend && npm run dev
```

Откройте `http://localhost:3000/login`, войдите как `director@extra-elit.demo`.

## 5. Сквозной сценарий (проверяется автоматически, `test_core_e2e.py`)

1. Вход `/auth/login` → JWT; `/auth/me` возвращает роли и права.
2. Создание проекта (`/core/projects`) — автор становится участником (ABAC).
3. Создание объекта (`/core/projects/{id}/sites`).
4. Создание поручения (`/core/projects/{id}/tasks`).
5. Отправка на согласование (`/core/tasks/{id}/submit`) — R2.
6. Решение руководителя (`/core/approvals/{id}/decision`).
7. Приёмка → ход → завершение (`accept` / `progress` / `complete`).
8. Ежедневный отчёт (`/core/projects/{id}/daily-reports` → `submit` → согласование).
9. Отражение в сводке (`/core/dashboard`).

Все значимые действия фиксируются в `audit_events`. Доступ ограничен ролями
(RBAC, `require_permission`) и проектами (ABAC, членство в `project_members`).
Критические решения принимает человек (согласование).
