# Backend — Badrudin AI OS

Серверное приложение на FastAPI (D-004; `DOCS/ARCHITECTURE.md` раздел 5.2).
Backend — единственная точка доступа к данным для интерфейса и ИИ-агентов.

Состояние: каркас Этапа 1 (задача T-1.A4) — health-check и конфигурация через
переменные окружения (Pydantic settings). Работа с базой и миграции (блок 1.B),
аутентификация и доступ (1.C), фоновые задачи Celery (1.F) добавляются
последующими задачами.

## Структура

```text
backend/
├── app/
│   ├── api/        — маршруты API (health)
│   ├── core/       — конфигурация и общие компоненты
│   ├── main.py     — точка входа (create_app)
│   ├── models/     — модели данных (блок 1.B)
│   ├── schemas/    — схемы Pydantic (блок 1.B)
│   ├── services/   — бизнес-логика
│   ├── workflows/  — процессы
│   ├── integrations/ — внешние интеграции
│   └── agents/     — ИИ-агенты
├── tests/          — тесты
├── Dockerfile
└── pyproject.toml
```

## Локальный запуск (для разработки)

```bash
cd backend
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
uvicorn app.main:app --reload
```

Проверка: `GET http://localhost:8000/health`.

## Тесты

```bash
cd backend
pip install -e ".[dev]"
pytest
```

Конфигурация читается из переменных окружения / файла `.env` (шаблон —
`.env.example` в корне репозитория). Секреты в код и в репозиторий не помещаются.
