# Signer PRIME License Server

Production-ready лицензионный сервер для Signer PRIME с PostgreSQL, Ed25519 подписями и Stripe интеграцией.

## 🚀 Быстрый старт (локальная разработка)

### Требования

- Docker и Docker Compose
- Python 3.12+
- PostgreSQL 16 (через Docker)

### Запуск

```bash
# 1. Поднять все сервисы (Postgres + Adminer + API)
docker-compose -f docker-compose.dev.yml up

# Или через bash-скрипт (Linux/Mac/Git Bash):
bash scripts/local_dev_up.sh
```

Сервисы будут доступны:
- **License Server API**: http://localhost:8000
- **API Docs**: http://localhost:8000/docs
- **Adminer (Database UI)**: http://localhost:8081

### Создание тестовой лицензии

```bash
# Установить зависимости
pip install requests

# Создать лицензию
python scripts/create_license_manual.py \
  --plan monthly \
  --days 30 \
  --devices 2
```

Лицензионный ключ будет выведен в stdout.

## 📦 Структура проекта

```
signer-license-server/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── config.py            # Конфигурация
│   ├── models.py            # SQLAlchemy модели
│   ├── schemas.py           # Pydantic схемы
│   ├── crypto.py            # Ed25519 подписи
│   ├── db.py                # Database setup
│   ├── routes/
│   │   ├── license.py       # Эндпоинты активации/refresh/deactivate
│   │   ├── admin.py         # Admin API для создания лицензий
│   │   └── stripe_webhook.py # Stripe интеграция
│   └── services/
│       ├── license_service.py  # Бизнес-логика лицензий
│       └── stripe_service.py   # Обработка Stripe событий
├── migrations/
│   ├── env.py               # Alembic environment
│   └── versions/
│       └── 001_initial_schema.py  # Начальная схема БД
├── tests/
│   ├── conftest.py          # Pytest фикстуры с testcontainers
│   ├── test_routes_activate.py
│   ├── test_routes_refresh.py
│   ├── test_race_condition.py  # Тест на SELECT FOR UPDATE
│   ├── test_stripe_webhook.py
│   └── test_admin_api.py
├── scripts/
│   ├── deploy_gcloud.sh           # Деплой на Google Cloud
│   ├── create_license_manual.py   # CLI для создания лицензий
│   ├── generate_ed25519_keys.py   # Генератор ключей
│   └── local_dev_up.sh            # Локальный запуск
├── docker/
│   ├── Dockerfile           # Multi-stage production build
│   └── .dockerignore
├── docker-compose.dev.yml   # Локальная разработка
├── alembic.ini              # Alembic конфигурация
├── requirements.txt
└── README.md
```

## 🔐 Безопасность

### Переменные окружения

**Обязательные:**
- `DATABASE_URL` или `DB_CONNECTION_NAME` (Cloud SQL)
- `ED25519_PRIVATE_KEY_PEM` — приватный ключ для подписи токенов
- `ADMIN_API_KEY` — ключ для admin API

**Опциональные:**
- `STRIPE_SECRET_KEY` — Stripe API ключ
- `STRIPE_WEBHOOK_SECRET` — секрет для проверки Stripe вебхуков

### Генерация Ed25519 ключей

```bash
python scripts/generate_ed25519_keys.py
```

**ВАЖНО:**
- Приватный ключ → Secret Manager (production) или `.env` (dev)
- Публичный ключ → `licensing/public_key.py` в клиентском коде
- НЕ коммитьте приватный ключ в Git

## 🧪 Тестирование

```bash
# Установить зависимости для тестов
pip install -r requirements.txt
pip install -r tests/requirements.txt

# Запустить все тесты (требуется Docker для testcontainers)
pytest tests/ -v

# Конкретный тест
pytest tests/test_race_condition.py -v
```

### Критические тесты

- **test_race_condition.py** — проверка `SELECT FOR UPDATE` при параллельной активации
- **test_stripe_webhook.py** — проверка защиты от поддельных вебхуков
- **test_routes_activate.py** — rate limiting на эндпоинтах

## ☁️ Деплой на Google Cloud Platform

### Подготовка

1. Сгенерировать production Ed25519 ключи:
   ```bash
   python scripts/generate_ed25519_keys.py > keys.txt
   # Сохраните приватный ключ в private_key.pem
   ```

2. Установить переменные окружения:
   ```bash
   export PROJECT_ID=your-gcp-project
   export REGION=us-central1
   export ADMIN_API_KEY=your_secure_random_key
   export ED25519_PRIVATE_KEY_PATH=./private_key.pem
   export STRIPE_SECRET_KEY=sk_live_... # опционально
   export STRIPE_WEBHOOK_SECRET=whsec_... # опционально
   ```

### Деплой

```bash
bash scripts/deploy_gcloud.sh
```

Скрипт идемпотентен — можно запускать повторно для обновления.

**Что создаётся:**
- Cloud SQL Postgres 16 instance
- Artifact Registry repository
- Secret Manager секреты (приватный ключ, DB пароль, Stripe ключи)
- Cloud Run service
- Database migrations (через Cloud Run Job)

### После деплоя

1. Получить URL сервиса:
   ```bash
   gcloud run services describe signer-license-server \
     --region=us-central1 \
     --format="value(status.url)"
   ```

2. Проверить health check:
   ```bash
   curl https://your-service-url.run.app/health
   ```

3. Создать тестовую лицензию:
   ```bash
   python scripts/create_license_manual.py \
     --server-url https://your-service-url.run.app \
     --admin-key YOUR_ADMIN_KEY \
     --plan monthly --days 30
   ```

4. Обновить клиентский код:
   - `licensing/public_key.py` — вставить публичный ключ
   - `configs/settings.py` — `license_server_url = "https://your-service-url.run.app"`
   - `licensing/license_client.py` — `LICENSE_MOCK_MODE = False`

## 📊 API Endpoints

### Public API

- `POST /api/license/activate` — активация лицензии (rate limit: 10/min)
- `POST /api/license/refresh` — обновление токена (rate limit: 20/min)
- `POST /api/license/deactivate` — деактивация устройства
- `GET /health` — health check

### Admin API

- `POST /api/admin/licenses` — создание лицензии (требует `X-Admin-Key`)

### Webhooks

- `POST /api/webhooks/stripe` — Stripe webhook (проверяет подпись)

Полная документация: http://localhost:8000/docs (Swagger UI)

## 🔧 Разработка

### Миграции БД

```bash
# Создать новую миграцию
alembic revision -m "description"

# Применить миграции
alembic upgrade head

# Откат
alembic downgrade -1
```

### Архитектура

- **Rate limiting**: `slowapi` на критичных эндпоинтах
- **Конкурентность**: `SELECT FOR UPDATE` для защиты от гонок
- **Partial unique index**: `(license_id, fingerprint_hash) WHERE deactivated_at IS NULL`
- **Токены**: Ed25519 подпись, формат `base64url(payload).base64url(signature)`

## 🐛 Troubleshooting

### Docker compose не стартует

```bash
# Проверить логи Postgres
docker-compose -f docker-compose.dev.yml logs postgres

# Пересоздать volumes
docker-compose -f docker-compose.dev.yml down -v
docker-compose -f docker-compose.dev.yml up
```

### Alembic ошибки

```bash
# Проверить подключение к БД
psql $DATABASE_URL -c "SELECT 1"

# Сбросить миграции (dev only!)
alembic downgrade base
alembic upgrade head
```

### Cloud Run деплой падает

```bash
# Логи Cloud Run
gcloud run services logs read signer-license-server --region=us-central1

# Проверить секреты
gcloud secrets list

# Проверить Cloud SQL доступ
gcloud sql instances describe signer-license-db
```

## 📝 Лицензия

Proprietary — Signer PRIME License Server

## 🔗 Связанные проекты

- **Signer PRIME Client** — основное приложение (`../licensing/`, `../ui/widgets/license_dialog.py`)
- **Клиентская документация** — `../docs/LICENSING.md`
