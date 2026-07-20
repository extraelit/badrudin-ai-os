# Локальный запуск Badrudin AI OS (Windows / macOS)

Пошаговая инструкция первого **безопасного** запуска на личном компьютере: без
внешних интеграций (ИИ, почта, Telegram, n8n выключены) и **без реальной отправки
сообщений, писем и публикаций**. Все внешние коммуникации в системе — только
черновики на утверждение человеком; фактическая отправка вне модулей не
выполняется.

> Файл размещён в каталоге `DOCS/` (канон имён — решение D-016). Отдельный
> каталог `docs/` в нижнем регистре не создаётся: на файловых системах Windows и
> macOS (регистронезависимых) он конфликтовал бы с существующим `DOCS/`.

---

## 1. Что понадобится

| Компонент | Версия | Проверка |
|---|---|---|
| Python | 3.11+ | `python --version` (Windows) / `python3 --version` (macOS) |
| Node.js | 20+ | `node --version` |
| Git | любая свежая | `git --version` |
| Docker Desktop | опционально (только для варианта B) | `docker --version` |

Есть два пути запуска:

- **Вариант A — рекомендуемый (без Docker).** База данных SQLite, никаких внешних
  сервисов. Самый быстрый и безопасный первый запуск.
- **Вариант B — «как в проде».** PostgreSQL + Redis + MinIO в Docker (без n8n,
  без AI/SMTP/Telegram). Ближе к целевому окружению.

Оба варианта используют один общий шаг подготовки БД —
`python scripts/dev_bootstrap.py`, который **проверяет секреты, применяет
миграции и безопасно загружает демо-данные** одной командой.

---

## 2. Общие шаги (обязательны для A и B)

### 2.1. Клонирование и переход в проект

**Windows (PowerShell):**
```powershell
git clone https://github.com/extraelit/badrudin-ai-os.git
cd badrudin-ai-os
```

**macOS (Terminal):**
```bash
git clone https://github.com/extraelit/badrudin-ai-os.git
cd badrudin-ai-os
```

### 2.2. Файл окружения `.env`

Скопируйте шаблон:

**Windows (PowerShell):**
```powershell
Copy-Item .env.example .env
```

**macOS:**
```bash
cp .env.example .env
```

### 2.3. Сгенерируйте безопасные секреты

Значения `change-me` обязательны к замене. Сгенерируйте случайный секрет
(≥32 байт) и подставьте его в `.env` в поля `SECRET_KEY` и `JWT_SECRET`:

**Windows (PowerShell):**
```powershell
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

**macOS:**
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
# или: openssl rand -base64 48
```

Откройте `.env` и замените:

```dotenv
SECRET_KEY=<вставьте_сгенерированное_значение>
JWT_SECRET=<вставьте_другое_сгенерированное_значение>
```

> Проверка секретов автоматическая: `dev_bootstrap.py` и запуск API отклонят
> заглушки/короткие значения в `staging`/`production`. В `development` выводится
> предупреждение, но запуск не блокируется.

---

## 3. Вариант A — запуск на SQLite (рекомендуется)

### 3.1. Настройте `.env` под SQLite

В файле `.env` задайте строку подключения к SQLite (замените строку
`DATABASE_URL`):

```dotenv
APP_ENV=development
DATABASE_URL=sqlite+pysqlite:///./badrudin_local.db
```

Остальные внешние сервисы (Redis, MinIO, n8n, AI, SMTP, Telegram) для варианта A
не нужны и остаются незаполненными — система в них не обращается.

### 3.2. Backend: виртуальное окружение и зависимости

**Windows (PowerShell):**
```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -e ".[dev]"
cd ..
```

**macOS:**
```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -e ".[dev]"
cd ..
```

### 3.3. Подготовка БД одной командой (секреты → миграции → демо-данные)

Из корня репозитория (виртуальное окружение backend активно):

```bash
python scripts/dev_bootstrap.py
```

Ожидаемый вывод завершается строкой `[bootstrap] Готово.` и сводкой загруженных
демо-данных. Команда **идемпотентна** — повторный запуск не создаёт дубликатов.

### 3.4. Запуск API

**Windows (PowerShell):**
```powershell
cd backend
uvicorn app.main:app --reload --port 8000
```

**macOS:**
```bash
cd backend
uvicorn app.main:app --reload --port 8000
```

Проверка: <http://localhost:8000/health> → `{"status":"ok",...}`;
интерактивная документация — <http://localhost:8000/docs>.

### 3.5. Frontend (в отдельном терминале)

**Windows (PowerShell):**
```powershell
cd frontend
npm install
Set-Content -Path .env.local -Value "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000`nNEXT_PUBLIC_APP_NAME=Badrudin AI OS"
npm run dev
```

**macOS:**
```bash
cd frontend
npm install
printf 'NEXT_PUBLIC_API_BASE_URL=http://localhost:8000\nNEXT_PUBLIC_APP_NAME=Badrudin AI OS\n' > .env.local
npm run dev
```

Интерфейс: <http://localhost:3000>.

Перейдите к разделу [5. Вход в систему](#5-вход-в-систему).

---

## 4. Вариант B — инфраструктура в Docker (PostgreSQL)

### 4.1. Настройте `.env` под PostgreSQL

Задайте локальный пароль БД и приведите хост к `localhost` (backend запускается
на хосте, а не внутри контейнера):

```dotenv
APP_ENV=development
POSTGRES_PASSWORD=localdev
DATABASE_URL=postgresql+psycopg://badrudin:localdev@localhost:5432/badrudin
```

### 4.2. Поднимите только инфраструктуру (без приложения, n8n и прокси)

```bash
docker compose up -d postgresql redis minio
```

Дождитесь статуса `healthy`:
```bash
docker compose ps
```

### 4.3. Backend: окружение, зависимости, подготовка БД

Выполните шаги [3.2](#32-backend-виртуальное-окружение-и-зависимости) и
[3.3](#33-подготовка-бд-одной-командой-секреты--миграции--демо-данные) — они
одинаковы для обоих вариантов. `dev_bootstrap.py` применит миграции к PostgreSQL
и загрузит демо-данные.

### 4.4. Запуск API и frontend

Шаги [3.4](#34-запуск-api) и [3.5](#35-frontend-в-отдельном-терминале) без
изменений.

> MinIO нужен только для загрузки файлов. При первом входе он не требуется. Если
> будете проверять вложения — создайте бакет `badrudin-files` в консоли MinIO
> (<http://localhost:9001>).

---

## 5. Вход в систему

Откройте <http://localhost:3000/login>. Пароль всех демо-пользователей задаётся
переменной `SEED_DEMO_PASSWORD` (по умолчанию `BadrudinDemo!2026`).

| E-mail | Роль | MFA | Для первого входа |
|---|---|---|---|
| `director@extra-elit.demo` | Производственный директор | нет | ✅ рекомендуется |
| `foreman@extra-elit.demo` | Прораб | нет | ✅ ограниченный доступ |
| `owner@extra-elit.demo` | Владелец системы | **да** | требуется код TOTP |

Для роли владельца включена обязательная многофакторная аутентификация. Демо-
секрет TOTP для локальной разработки — `JBSWY3DPEHPK3PXP`: добавьте его в любое
TOTP-приложение (Google Authenticator и т. п.) и введите 6-значный код. Для
первого знакомства проще войти под `director`.

---

## 6. Почему это безопасно

- **ИИ / почта / Telegram выключены:** `AI_PROVIDER=none`, поля `SMTP_*` и
  `TELEGRAM_BOT_TOKEN` пустые — система к внешним сервисам не подключается.
- **Исходящие сообщения не отправляются:** модуль интеграций создаёт только
  черновики и переводит их в статус «утверждено» (готово к отправке человеком вне
  модуля). SMTP/HTTP-клиентов отправки в коде нет.
- **Уведомления — только внутренние (`in_app`)**, публикации SMM — черновики.
- **n8n, reverse-proxy и мониторинг** в инструкции не запускаются.
- **Данные обезличенные** (`database/fixtures/dev_seed.json`, D-011): реальных
  персональных данных и секретов нет.
- **Критические действия (R4)** и вход под привилегированными ролями требуют
  подтверждения человеком / MFA.

---

## 7. Возможные проблемы

| Симптом | Причина и решение |
|---|---|
| `[bootstrap] ОШИБКА секретов` | `JWT_SECRET` не задан или короткий и окружение — staging/production. Задайте секрет ≥32 байт (см. [2.3](#23-сгенерируйте-безопасные-секреты)). |
| `uvicorn: command not found` | Не активировано виртуальное окружение backend (шаг 3.2). |
| `Activate.ps1 … отключено политикой` (Windows) | Выполните `Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`, затем активируйте venv. |
| Backend не видит БД (вариант B) | Проверьте, что в `DATABASE_URL` хост `localhost`, а контейнеры `healthy` (`docker compose ps`). |
| Вход `owner` возвращает 401 | Для владельца обязателен код TOTP. Войдите под `director` или введите код по секрету из раздела 5. |
| Порт 8000/3000 занят | Запустите с другим портом (`--port` для uvicorn; `PORT=3001 npm run dev` для frontend) и обновите `NEXT_PUBLIC_API_BASE_URL`. |

---

## 8. Остановка

- API / frontend — `Ctrl + C` в соответствующем терминале.
- Docker (вариант B): `docker compose down` (данные сохраняются в томах) или
  `docker compose down -v` (удалить данные).
- Локальный файл БД (вариант A) — `badrudin_local.db` в каталоге `backend/`;
  удалите его, чтобы начать с чистой базы.
