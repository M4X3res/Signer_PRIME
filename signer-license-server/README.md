# Signer PRIME License Server

Серверная часть системы лицензирования для Signer PRIME.

## Стек

- **Backend:** FastAPI (Python 3.12+)
- **Database:** Google Cloud SQL (PostgreSQL 16)
- **Secrets:** Google Secret Manager
- **Deployment:** Google Cloud Run
- **Migrations:** Alembic
- **Crypto:** Ed25519 (cryptography)
- **Payments:** Stripe (Checkout + Billing)

## Структура

```
app/
├── main.py              # FastAPI приложение
├── config.py            # Настройки (pydantic-settings)
├── db.py                # SQLAlchemy engine + Cloud SQL connector
├── models.py            # ORM модели (License, Device)
├── schemas.py           # Pydantic схемы запросов/ответов
├── crypto.py            # Ed25519 подпись, генерация ключей
├── routes/
│   ├── license.py       # /api/license/activate|refresh|deactivate
│   ├── stripe_webhook.py # /api/webhooks/stripe
│   └── admin.py         # /api/admin/licenses (защищено)
└── services/
    ├── license_service.py  # Бизнес-логика лицензий
    └── stripe_service.py   # Обработка Stripe вебхуков

migrations/              # Alembic миграции
scripts/                 # Скрипты деплоя и утилиты
tests/                   # Тесты (pytest)
docker/                  # Dockerfile
```

## Локальная разработка

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
pip install -r requirements-dev.txt
```

### 2. Генерация Ed25519 ключей (dev)

```bash
python scripts/generate_ed25519_keys.py --out .deploy_keys/
```

### 3. Запуск локально (Docker Compose)

```bash
bash scripts/local_dev_up.sh
```

Или вручную:

```bash
docker-compose -f docker-compose.dev.yml up
```

API будет доступно на `http://localhost:8000`

### 4. Применение миграций

```bash
alembic upgrade head
```

### 5. Создание тестового ключа

```bash
python scripts/create_license_manual.py \
  --api-url http://localhost:8000 \
  --admin-key dev-admin-key \
  --plan yearly \
  --duration-days 365
```

## Деплой на Google Cloud

### Предварительные требования

- Google Cloud SDK установлен и настроен
- Проект GCP создан
- Billing включен

### Одна команда для полного развёртывания

```bash
bash scripts/deploy_gcloud.sh
```

Скрипт автоматически:
- Включает необходимые API
- Создаёт Cloud SQL (PostgreSQL)
- Настраивает Secret Manager
- Создаёт Service Account с минимальными правами
- Собирает и деплоит на Cloud Run
- Применяет миграции через Cloud Run Job

### Обновление публичного ключа в клиенте

После первого деплоя скопируйте `.deploy_keys/ed25519_public.pem` в клиент:

```bash
# В клиенте Signer PRIME обновите licensing/public_key.py
LICENSE_PUBLIC_KEY_PEM = """<содержимое ed25519_public.pem>"""
```

### Обновление URL в клиенте

В `configs/settings.py` клиента:

```python
license_server_url: str = "https://signer-license-api-xxxxx.run.app"
```

Отключите мок-режим в `licensing/license_client.py`:

```python
LICENSE_MOCK_MODE = False
```

## Тестирование

```bash
# Все тесты
pytest

# С покрытием
pytest --cov=app --cov-report=html

# Конкретный модуль
pytest tests/test_license_service.py -v
```

## API Endpoints

### Public

- `POST /api/license/activate` - Активация лицензии
- `POST /api/license/refresh` - Обновление токена
- `POST /api/license/deactivate` - Деактивация устройства
- `GET /api/license/status?key=...` - Статус лицензии
- `POST /api/webhooks/stripe` - Stripe вебхуки

### Admin (требует X-Admin-Key)

- `POST /api/admin/licenses` - Создание лицензии вручную

### Health

- `GET /health` - Health check

## Переменные окружения

### Локальная разработка

См. `.env.example`

### Production (Secret Manager)

- `DB_CONNECTION_NAME` - Cloud SQL connection name
- `DB_USER` - Database user
- `DB_NAME` - Database name
- `DB_PASSWORD` - Database password (secret)
- `ED25519_PRIVATE_KEY_PEM` - Приватный ключ Ed25519 (secret)
- `ADMIN_API_KEY` - API ключ для admin эндпоинтов (secret)
- `STRIPE_SECRET_KEY` - Stripe secret key (secret)
- `STRIPE_WEBHOOK_SECRET` - Stripe webhook secret (secret)

## Документация

- **API Docs:** `https://your-service.run.app/docs` (Swagger UI)
- **ReDoc:** `https://your-service.run.app/redoc`

## Мониторинг

- **Cloud Logging:** Все логи автоматически в Cloud Logging
- **Cloud Monitoring:** Метрики Cloud Run (latency, errors, requests/sec)
- **Alerting:** Настройте alert policies для критических ошибок

## Безопасность

- ✅ Ed25519 асимметричная криптография
- ✅ Приватные ключи только в Secret Manager
- ✅ Rate limiting на критических эндпоинтах
- ✅ Валидация всех входных данных (Pydantic)
- ✅ SQL injection защита (SQLAlchemy ORM)
- ✅ HTTPS обязателен (Cloud Run)
- ✅ Service Account с минимальными правами

## Troubleshooting

### Миграции не применились

```bash
# Через Cloud Run Job
gcloud run jobs execute signer-license-migrate --region=europe-west1 --wait
```

### Проверка секретов

```bash
gcloud secrets versions access latest --secret=ed25519-private-key
```

### Логи Cloud Run

```bash
gcloud run services logs read signer-license-api --region=europe-west1
```

## License

Проприетарное ПО. Все права защищены.
