FROM python:3.12-slim as builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ libpq-dev \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

RUN useradd -m -u 1000 appuser
COPY --from=builder --chown=appuser:appuser /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

COPY app/ /app/app/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/
RUN chown -R appuser:appuser /app

USER appuser
ENV PYTHONUNBUFFERED=1
ENV PORT=8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:${PORT}/health || exit 1
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}