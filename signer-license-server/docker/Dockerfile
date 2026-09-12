# Signer PRIME License Server - Production Dockerfile
# Multi-stage build для минимального размера образа

# ════════════════════════════════════════════════════════════════
# Stage 1: Builder - установка зависимостей и сборка wheels
# ════════════════════════════════════════════════════════════════
FROM python:3.12-slim as builder

WORKDIR /build

# Установка build-зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Копирование requirements и установка в отдельную директорию
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt


# ════════════════════════════════════════════════════════════════
# Stage 2: Runtime - финальный минимальный образ
# ════════════════════════════════════════════════════════════════
FROM python:3.12-slim

WORKDIR /app

# Установка только runtime-зависимостей
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Копирование Python-пакетов из builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Копирование кода приложения
COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/

# Создание non-root пользователя для безопасности
RUN useradd -m -u 1000 appuser && chown -R appuser:appuser /app
USER appuser

# Переменные окружения
ENV PYTHONUNBUFFERED=1
ENV PORT=8080

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1

# Точка входа
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
