# Backend (FastAPI) — образ dev-профиля (T-1.A4)
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Установка зависимостей по метаданным проекта
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .

EXPOSE 8000

# Запуск API; конфигурация — через переменные окружения
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
