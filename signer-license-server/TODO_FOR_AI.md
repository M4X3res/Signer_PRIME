# Промпт для завершения реализации License Server

## Контекст

Это **продолжение** реализации серверной части лицензирования для Signer PRIME.
Архитектура на 70% готова, осталось реализовать production-критичные компоненты.

## Что уже готово

✅ Модели (app/models.py)  
✅ Конфигурация (app/config.py)  
✅ Криптография (app/crypto.py)  
✅ База данных (app/db.py)  
✅ Schemas (app/schemas.py)  
✅ MVP сервер для тестирования (app/main.py)  
✅ Документация  

## Твоя задача

Реализовать **оставшиеся 30%** для production-ready сервера:

### 1. Services Layer (ПРИОРИТЕТ 1)

Создай `app/services/license_service.py`:

```python
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import License, Device
from app.crypto import sign_token, load_private_key
from app.config import get_settings
from datetime import datetime
import time

class LicenseService:
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.private_key = load_private_key(self.settings.ed25519_private_key_pem)
    
    def activate_license(
        self,
        license_key: str,
        fingerprint_hash: str,
        device_label: str,
        app_version: str
    ) -> dict:
        """
        Активация лицензии с защитой от race conditions.
        
        Логика:
        1. Найти License by license_key
        2. Проверить status == "active"
        3. Проверить current_period_end > now()
        4. SELECT ... FOR UPDATE для подсчёта активных устройств
        5. Если fingerprint уже есть → обновить last_seen
        6. Если новый и лимит не исчерпан → создать Device
        7. Иначе → error DEVICE_LIMIT_REACHED
        8. Вернуть подписанный токен
        """
        # TODO: Реализовать согласно промпту PROMPT_LICENSE_SERVER_CLOUD_RUN.md раздел 4
        pass
    
    def refresh_license(self, token: str, fingerprint_hash: str) -> dict:
        """Обновление токена."""
        # TODO: парсинг токена, проверка fingerprint, выдача нового токена
        pass
    
    def deactivate_device(self, token: str) -> dict:
        """Деактивация устройства."""
        # TODO: парсинг токена, set deactivated_at = now()
        pass
```

**Ключевое требование:** используй `SELECT ... FOR UPDATE` для защиты от гонок при активации.

### 2. Routes (ПРИОРИТЕТ 2)

Создай `app/routes/license.py`:

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.db import get_db
from app.schemas import *
from app.services.license_service import LicenseService

router = APIRouter(prefix="/api/license", tags=["license"])

@router.post("/activate", response_model=LicenseResponse)
async def activate(req: ActivateRequest, db: Session = Depends(get_db)):
    service = LicenseService(db)
    try:
        result = service.activate_license(
            req.license_key,
            req.fingerprint_hash,
            req.device_label,
            req.app_version
        )
        return result
    except ValueError as e:
        # TODO: обработка ошибок с правильными кодами
        pass

# TODO: остальные эндпоинты (refresh, deactivate)
```

Создай `app/routes/admin.py` для `/api/admin/licenses` (защищено X-Admin-Key).

Обнови `app/main.py` - замени MVP логику на роуты:

```python
from app.routes import license, admin
app.include_router(license.router)
app.include_router(admin.router)
```

### 3. Alembic Migrations (ПРИОРИТЕТ 3)

Создай:
- `alembic.ini` (базовая конфигурация)
- `migrations/env.py` (подключение к app.config)
- `migrations/versions/001_initial_schema.py`:

```python
def upgrade():
    # CREATE EXTENSION IF NOT EXISTS "pgcrypto";
    # CREATE TABLE licenses (...)
    # CREATE TABLE devices (...)
    # CREATE UNIQUE INDEX uq_active_device
    #   ON devices (license_id, fingerprint_hash)
    #   WHERE deactivated_at IS NULL;
    pass
```

### 4. Docker (ПРИОРИТЕТ 4)

`docker/Dockerfile`:
```dockerfile
FROM python:3.12-slim as builder
WORKDIR /app
COPY requirements.txt .
RUN pip wheel --no-cache-dir --no-deps --wheel-dir /app/wheels -r requirements.txt

FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /app/wheels /wheels
RUN pip install --no-cache /wheels/*
COPY app/ ./app/
COPY alembic.ini ./
COPY migrations/ ./migrations/
ENV PORT=8080
CMD uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

`docker-compose.dev.yml` - PostgreSQL + app для локальной разработки.

### 5. scripts/deploy_gcloud.sh (ПРИОРИТЕТ 5)

**Это самый важный скрипт** - полный автоматический деплой на GCP.

Используй как reference раздел 6 из `prompts/PROMPT_LICENSE_SERVER_CLOUD_RUN.md`.

Скрипт должен:
1. Включить API (run, sqladmin, secretmanager, etc.)
2. Создать Cloud SQL (PostgreSQL 16)
3. Создать пользователя БД
4. Сохранить секреты в Secret Manager (db-password, ed25519-private-key, admin-api-key, stripe-*)
5. Создать Service Account
6. Дать права SA (secretmanager.secretAccessor, cloudsql.client)
7. Собрать образ через Cloud Build
8. Задеплоить на Cloud Run с `--add-cloudsql-instances`
9. Создать Cloud Run Job для миграций
10. Запустить миграции

**Идемпотентность:** повторный запуск не должен ломать существующее.

### 6. Tests (ПРИОРИТЕТ 6)

Используй pytest + testcontainers:

```python
# tests/conftest.py
import pytest
from testcontainers.postgres import PostgresContainer
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.models import Base

@pytest.fixture(scope="session")
def postgres_container():
    with PostgresContainer("postgres:16") as postgres:
        yield postgres

@pytest.fixture
def db_session(postgres_container):
    engine = create_engine(postgres_container.get_connection_url())
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
```

Тесты:
- `test_routes_activate.py` - все кейсы из раздела 8 промпта
- `test_race_conditions.py` - два параллельных activate при лимите 1

### 7. Scripts/create_license_manual.py

```python
import requests
import argparse

def create_license(api_url, admin_key, plan, duration_days):
    response = requests.post(
        f"{api_url}/api/admin/licenses",
        headers={"X-Admin-Key": admin_key},
        json={"plan": plan, "duration_days": duration_days, "max_devices": 2}
    )
    if response.status_code == 200:
        data = response.json()
        print(f"License created: {data['license_key']}")
    else:
        print(f"Error: {response.text}")

if __name__ == "__main__":
    # TODO: argparse
```

## Критерии приёмки

Проверь ВСЕ пункты из раздела 10 промпта `PROMPT_LICENSE_SERVER_CLOUD_RUN.md`:

- [ ] `docker-compose -f docker-compose.dev.yml up` работает
- [ ] `pytest` зелёный
- [ ] `scripts/deploy_gcloud.sh` разворачивает с нуля
- [ ] Приватный ключ только в Secret Manager
- [ ] Активация с валидным ключом работает
- [ ] Повторная активация не плодит devices
- [ ] Лимит устройств работает (409 DEVICE_LIMIT_REACHED)
- [ ] Клиент `licensing/public_key.py` верифицирует токен
- [ ] Refresh с отозванной лицензией возвращает status: canceled

## Используй как reference

1. `prompts/PROMPT_LICENSE_SERVER_CLOUD_RUN.md` - ГЛАВНЫЙ источник требований
2. `docs/LICENSE_SERVER.md` - спецификация API
3. `docs/LICENSE_SERVER_EXAMPLE.md` - примеры кода
4. Уже реализованные файлы (models.py, crypto.py, config.py)

## Порядок работы

1. Services (4 часа)
2. Routes (2 часа)
3. Alembic (2 часа)
4. Локальное тестирование (1 час)
5. Docker (2 часа)
6. deploy_gcloud.sh (6 часов)
7. Tests (6 часов)
8. Scripts (2 часа)
9. Integration testing (3 часа)
10. Документация обновление (2 часа)

**Итого: 30 часов**

## Важные примечания

- **SELECT FOR UPDATE** обязателен в activate_license для защиты от гонок
- **Partial unique index** `(license_id, fingerprint_hash) WHERE deactivated_at IS NULL` создаётся в миграции raw SQL
- **Cloud SQL подключение** через Unix socket `/cloudsql/<CONNECTION_NAME>`
- **Секреты** монтируются как env vars через `--set-secrets`
- **Токен payload** - строго как в клиенте (license_key, device_id, plan, status, current_period_end, issued_at)

## Начинай!

Реализуй по порядку (services → routes → migrations → ...).
Коммить после каждого большого модуля.
Тестируй локально перед Cloud деплоем.

Удачи! 🚀
