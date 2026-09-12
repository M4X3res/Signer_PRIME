# Промпт для ИИ-агента: сервер лицензий Signer PRIME на Google Cloud (Cloud SQL + Secret Manager + Cloud Run)

Это продолжение задачи из `PROMPT_LICENSING_SYSTEM.md`. Клиентская часть
(`licensing/`, `ui/widgets/license_dialog.py`, интеграция в `main.py`) уже
реализована и работает в мок-режиме (`LICENSE_MOCK_MODE = True` в
`licensing/license_client.py`). Твоя задача — реализовать **реальный сервер
лицензий** и весь Cloud-инфраструктурный код для его развёртывания.

Работай в **отдельном репозитории/папке** (например `signer-license-server/`),
никак не смешивая его с кодом Signer PRIME. Единственная точка соприкосновения —
значение `license_server_url` в `configs/settings.py` клиента и публичный
Ed25519-ключ в `licensing/public_key.py`, которые ты обновишь в самом конце.

---

## 0. Обязательные решения (не пересматривай без явной причины)

Эти решения уже приняты и обоснованы — не заменяй их на альтернативы:

- **База данных: Cloud SQL for PostgreSQL**, НЕ SQLite, НЕ Firestore.
  - SQLite не переживёт горизонтальное масштабирование/пересоздание инстансов
    Cloud Run — файл на диске одного контейнера не виден другим и теряется при
    рестарте.
  - Firestore подошёл бы, но реляционная схема `licenses` + `devices` с
    уникальными ограничениями и подсчётом активных устройств прозрачнее и
    безопаснее на SQL, а миграции понятнее при будущей интеграции биллинга.
  - Cloud SQL — управляемый, переживает рестарты Cloud Run, подключается через
    Unix-сокет без отдельного VPC-коннектора (`--add-cloudsql-instances`).
- **Секреты: Google Secret Manager.** Приватный Ed25519-ключ, пароль к БД,
  Stripe webhook secret — никогда в коде, `.env`, или образе контейнера.
- **Рантайм: Cloud Run** (не GKE, не Compute Engine) — простой, автоскейлится
  до нуля, HTTPS из коробки.
- **Стек приложения: Python + FastAPI** (async, встроенная OpenAPI-документация,
  Pydantic-валидация запросов). Flask допустим только если ты уже на середине
  реализации и переписывание не даёт пользы — по умолчанию бери FastAPI.
- Формат токена, схема БД, эндпоинты и логика лимита устройств — **как описано
  в `PROMPT_LICENSING_SYSTEM.md`, раздел 2**. Не меняй payload токена и имена
  полей без необходимости — клиент уже написан под них.

---

## 1. Структура нового репозитория

```
signer-license-server/
  app/
    __init__.py
    main.py                 # FastAPI app, роуты, startup/shutdown
    config.py                # Settings через pydantic-settings, читает env/Secret Manager
    db.py                    # SQLAlchemy engine + сессии, Cloud SQL Python Connector
    models.py                # SQLAlchemy ORM: License, Device
    schemas.py                # Pydantic request/response модели
    crypto.py                # Ed25519 подпись токенов, генерация license_key
    routes/
      __init__.py
      license.py             # /api/license/activate|refresh|deactivate|status
      stripe_webhook.py       # /api/webhooks/stripe
      admin.py                 # /api/admin/* — создание ключей вручную (защищено API-ключом)
    services/
      license_service.py     # бизнес-логика активации/refresh/деактивации
      stripe_service.py       # обработка вебхуков, обновление licenses
  migrations/                # Alembic
    env.py
    versions/
  scripts/
    create_license_manual.py    # CLI для создания ключа без Stripe (для MVP/поддержки)
    generate_ed25519_keys.py    # копия/адаптация scripts/generate_ed25519_keys.py клиента
    deploy_gcloud.sh            # ⭐ одна команда: поднимает Cloud SQL + Secret Manager + Cloud Run
    local_dev_up.sh              # docker-compose с локальным Postgres для разработки
  tests/
    test_crypto.py
    test_license_service.py
    test_routes_activate.py
    test_routes_refresh.py
    test_routes_deactivate.py
    test_stripe_webhook.py
    conftest.py                # фикстуры: тестовая БД (sqlite/postgres testcontainers), тестовые ключи
  docker/
    Dockerfile
    .dockerignore
  docker-compose.dev.yml        # Postgres + adminer для локальной разработки
  alembic.ini
  pyproject.toml (или requirements.txt + requirements-dev.txt)
  .env.example
  README.md                     # как поднять локально и задеплоить
```

---

## 2. Схема БД и миграции (Alembic)

Используй **SQLAlchemy 2.x** ORM + **Alembic** для миграций (не создавай таблицы
через `create_all()` в проде — только через миграции, чтобы история схемы была
воспроизводима).

```python
# app/models.py
import uuid
from datetime import datetime
from sqlalchemy import String, Integer, DateTime, ForeignKey, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship, DeclarativeBase

class Base(DeclarativeBase):
    pass

class License(Base):
    __tablename__ = "licenses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    license_key: Mapped[str] = mapped_column(String(32), unique=True, index=True, nullable=False)
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    plan: Mapped[str] = mapped_column(String(16), nullable=False)          # monthly|quarterly|yearly
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")  # active|past_due|canceled|expired
    current_period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    max_devices: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=datetime.utcnow)

    devices: Mapped[list["Device"]] = relationship(back_populates="license")


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    license_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("licenses.id", ondelete="CASCADE"), nullable=False)
    fingerprint_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    device_label: Mapped[str | None] = mapped_column(String(128), nullable=True)
    first_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()")
    last_seen: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default="now()", onupdate=datetime.utcnow)
    deactivated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    license: Mapped["License"] = relationship(back_populates="devices")

    __table_args__ = (
        # Partial unique index: одно активное устройство с данным fingerprint на лицензию.
        # SQLAlchemy declarative не поддерживает partial unique constraint напрямую —
        # добавь его через Alembic raw SQL в миграции:
        #   CREATE UNIQUE INDEX uq_active_device
        #     ON devices (license_id, fingerprint_hash)
        #     WHERE deactivated_at IS NULL;
        Index("ix_devices_license_id", "license_id"),
    )
```

Требования к первой Alembic-миграции:
- Включи расширение `pgcrypto` или используй `uuid.uuid4()` на стороне приложения
  (не полагайся на `gen_random_uuid()` без явного `CREATE EXTENSION`).
- Создай **partial unique index** `(license_id, fingerprint_hash) WHERE deactivated_at IS NULL`
  через `op.execute("CREATE UNIQUE INDEX ...")` — этим ты гарантируешь на уровне БД,
  что одно и то же устройство не может быть зарегистрировано дважды как активное,
  даже при гонке запросов (не полагайся только на проверку в Python).
- Добавь обычный индекс на `licenses.license_key` (уже есть через `unique=True`)
  и на `devices.license_id`.

---

## 3. Формат токена и криптография (`app/crypto.py`)

Реализуй **строго** так же, как описано в исходном промпте (раздел 2.3), чтобы
клиент (`licensing/public_key.py`) не пришлось переписывать:

```python
payload = json.dumps({
    "license_key": ...,
    "device_id": str(device.id),
    "plan": ...,
    "status": ...,
    "current_period_end": int(current_period_end.timestamp()),
    "issued_at": int(time.time()),
}, sort_keys=True).encode()

signature = ed25519_private_key.sign(payload)
token = base64url_nopad(payload) + "." + base64url_nopad(signature)
```

- Приватный ключ загружается ОДИН РАЗ при старте приложения из переменной
  окружения `ED25519_PRIVATE_KEY_PEM`, которая монтируется из Secret Manager
  (см. раздел 6). Не читай Secret Manager на каждый запрос — кэшируй в памяти
  процесса.
- Генерация `license_key`: формат `SGNR-XXXX-XXXX-XXXX-XXXX`, алфавит base32
  без `O/0/I/1` (используй `Crockford base32` или свой алфавит
  `ABCDEFGHJKMNPQRSTUVWXYZ23456789`), проверяй уникальность в БД перед вставкой
  (retry при коллизии, коллизии почти невозможны, но код должен быть корректным).

---

## 4. Эндпоинты — детали реализации

Общие требования ко всем эндпоинтам:
- Валидация тела запроса через Pydantic-схемы в `app/schemas.py`.
- Ошибки — единый формат `{"error_code": "...", "error": "человекочитаемое сообщение"}`
  с соответствующим HTTP-статусом (клиент `licensing/license_client.py` уже
  ожидает поля `error_code`/`error`).
- Rate limiting на `/api/license/activate` и `/api/license/refresh` (например,
  через `slowapi` или простой Redis/in-memory токен-бакет по IP +
  `license_key`) — защита от подбора ключей.
- Логируй КАЖДУЮ попытку активации/деактивации (license_key, fingerprint,
  результат) в структурированный лог (Cloud Logging подхватит stdout JSON) —
  это твой единственный источник данных для расследования абузов.

### `POST /api/license/activate`
Body: `{license_key, fingerprint_hash, device_label, app_version}`

Логика:
1. Найти `License` по `license_key`. Не найдена → `404 INVALID_LICENSE`.
2. `status != "active"` → `403 LICENSE_REVOKED` (или `LICENSE_EXPIRED`, если
   `status == "expired"` — различай коды, клиент показывает разный текст).
3. `current_period_end < now()` → `403 LICENSE_EXPIRED`.
4. Посчитать активные устройства (`deactivated_at IS NULL`) для этой лицензии
   через `SELECT ... FOR UPDATE` внутри транзакции (защита от гонки двух
   одновременных активаций).
5. Если `fingerprint_hash` уже среди активных устройств этой лицензии —
   обновить `last_seen`, `device_label`, выдать токен (переактивация с того же
   ПК всегда разрешена, не считается новым устройством).
6. Если `fingerprint_hash` новый и `count(active) >= max_devices` →
   `409 DEVICE_LIMIT_REACHED`.
7. Иначе — создать `Device`, выдать токен.
8. Ответ: `{"token": "...", "plan": ..., "current_period_end": <unix_ts>}`.

### `POST /api/license/refresh`
Body: `{token, fingerprint_hash}`

Логика:
1. Провалидировать подпись присланного токена (используй его только чтобы
   узнать `license_key`/`device_id` — НЕ доверяй его `status`/`current_period_end`,
   это могут быть устаревшие данные).
2. Найти `License` и `Device` по извлечённым id. Устройство деактивировано
   (`deactivated_at IS NOT NULL`) → `403 DEVICE_DEACTIVATED`.
3. `fingerprint_hash` в запросе должен совпадать с хранимым — иначе `403
   FINGERPRINT_MISMATCH` (защита от кражи токена и переноса на другой ПК без
   повторной активации).
4. Обновить `last_seen`, выдать **новый** токен с актуальными
   `status`/`current_period_end` из БД (именно так реализуется отзыв —
   следующий refresh вернёт `status: canceled`, и клиент сам обработает это как
   `LicenseStatus.REVOKED`).

### `POST /api/license/deactivate`
Body: `{token}` → провалидировать, найти `Device`, выставить
`deactivated_at = now()`. Идемпотентно (повторный вызов не должен падать).

### `POST /api/webhooks/stripe`
- Верифицируй `Stripe-Signature` заголовок через `stripe.Webhook.construct_event`
  с секретом из Secret Manager (`STRIPE_WEBHOOK_SECRET`).
- Обрабатывай минимум: `checkout.session.completed` (создать/найти `License`,
  сгенерировать `license_key`, записать `stripe_customer_id`,
  `stripe_subscription_id`, `current_period_end` из данных подписки Stripe,
  `status = "active"`), `customer.subscription.updated` (синхронизировать
  `status`/`current_period_end`; `status: "past_due"` → тот же статус в БД, не
  отзывай доступ сразу, дай grace period самого Stripe отработать),
  `customer.subscription.deleted` (`status = "canceled"`),
  `invoice.payment_failed` (можно только залогировать / пометить `past_due`,
  не отзывать немедленно).
- Возвращай `200 OK` даже если событие не обработано конкретным хендлером
  (Stripe ретраит 4xx/5xx — отвечай `400` только на реальную ошибку верификации
  подписи).
- Не забудь: если `checkout.session.completed` создаёт лицензию, `license_key`
  должен быть где-то показан пользователю (email через Stripe Checkout success
  page или отдельный email-сервис — это уже вне scope сервера, но убедись что
  ключ **возвращается** в ответе на success-редирект / есть эндпоинт
  `GET /api/license/lookup?session_id=...` для сайта, чтобы показать ключ сразу
  после оплаты).

### `POST /api/admin/licenses` (защищено, для MVP без Stripe и для поддержки)
- Требует заголовок `X-Admin-Key`, сверяемый с секретом `ADMIN_API_KEY` из
  Secret Manager (constant-time сравнение, `hmac.compare_digest`).
- Body: `{plan, duration_days, max_devices}` → создаёт `License` с новым
  `license_key`, без привязки к Stripe. Именно этим пользуется
  `scripts/create_license_manual.py` для ручной выдачи ключей на старте, пока
  Stripe не подключён.

### `GET /api/license/status?key=...` (опционально, для личного кабинета сайта)
- Возвращает план, `current_period_end`, число активных устройств — БЕЗ
  чувствительных данных (fingerprint не отдавай).

---

## 5. Docker-образ и локальная разработка

`docker/Dockerfile` — многоступенчатая сборка, финальный образ на
`python:3.12-slim`, non-root пользователь, `CMD ["uvicorn", "app.main:app",
"--host", "0.0.0.0", "--port", "8080"]` (Cloud Run ожидает порт из переменной
`PORT`, читай её явно: `--port ${PORT:-8080}` через shell-обёртку или
`app.main:app` с явным использованием `os.environ["PORT"]`).

`docker-compose.dev.yml` — Postgres 16 + сам сервис для локальной разработки,
чтобы не нужен был доступ к Cloud SQL во время разработки:
```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: signer_license
      POSTGRES_PASSWORD: devpassword
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]
  api:
    build: { context: ., dockerfile: docker/Dockerfile }
    environment:
      DATABASE_URL: postgresql+psycopg://postgres:devpassword@db:5432/signer_license
      ED25519_PRIVATE_KEY_PEM: ${ED25519_PRIVATE_KEY_PEM}
      ADMIN_API_KEY: dev-admin-key
      STRIPE_SECRET_KEY: sk_test_...
      STRIPE_WEBHOOK_SECRET: whsec_test_...
    ports: ["8000:8080"]
    depends_on: [db]
volumes:
  pgdata:
```

`scripts/local_dev_up.sh` — обёртка: генерирует dev Ed25519-ключ если его ещё
нет (`scripts/generate_ed25519_keys.py --out .dev_keys/`), поднимает
`docker-compose up`, прогоняет `alembic upgrade head`.

---

## 6. `scripts/deploy_gcloud.sh` — одна команда для полного развёртывания

Это ключевой артефакт этого промпта. Скрипт должен быть **идемпотентным**
(повторный запуск не ломает существующую инфраструктуру — используй `gcloud ...
--quiet` и проверки `if ! gcloud ... describe ... &>/dev/null; then create;
fi`), с явными переменными в начале файла и комментариями на каждом шаге.
Целевая последовательность:

```bash
#!/usr/bin/env bash
set -euo pipefail

# ── Переменные (отредактируй перед первым запуском) ──────────────────────
PROJECT_ID="signer-prime-licensing"
REGION="europe-west1"
SQL_INSTANCE="signer-license-db"
SQL_TIER="db-f1-micro"           # хватает для MVP, апгрейди позже при нагрузке
DB_NAME="signer_license"
DB_USER="signer_app"
SERVICE_NAME="signer-license-api"
SERVICE_ACCOUNT="signer-license-sa"
AR_REPO="signer-license"          # Artifact Registry repo для образа

# ── 1. Включить нужные API ────────────────────────────────────────────────
gcloud services enable \
  run.googleapis.com \
  sqladmin.googleapis.com \
  secretmanager.googleapis.com \
  artifactregistry.googleapis.com \
  cloudbuild.googleapis.com \
  --project "$PROJECT_ID"

# ── 2. Cloud SQL (Postgres) ───────────────────────────────────────────────
if ! gcloud sql instances describe "$SQL_INSTANCE" --project "$PROJECT_ID" &>/dev/null; then
  gcloud sql instances create "$SQL_INSTANCE" \
    --database-version=POSTGRES_16 \
    --tier="$SQL_TIER" \
    --region="$REGION" \
    --storage-auto-increase \
    --backup-start-time=03:00 \
    --project "$PROJECT_ID"
fi

DB_PASSWORD="$(openssl rand -base64 24)"
gcloud sql users create "$DB_USER" --instance="$SQL_INSTANCE" \
  --password="$DB_PASSWORD" --project "$PROJECT_ID" || \
  gcloud sql users set-password "$DB_USER" --instance="$SQL_INSTANCE" \
    --password="$DB_PASSWORD" --project "$PROJECT_ID"

gcloud sql databases create "$DB_NAME" --instance="$SQL_INSTANCE" \
  --project "$PROJECT_ID" || true

CONNECTION_NAME="$(gcloud sql instances describe "$SQL_INSTANCE" \
  --project "$PROJECT_ID" --format='value(connectionName)')"

# ── 3. Secret Manager: секреты приложения ─────────────────────────────────
create_or_update_secret() {
  local name="$1" value="$2"
  if ! gcloud secrets describe "$name" --project "$PROJECT_ID" &>/dev/null; then
    echo -n "$value" | gcloud secrets create "$name" \
      --data-file=- --replication-policy=automatic --project "$PROJECT_ID"
  else
    echo -n "$value" | gcloud secrets versions add "$name" \
      --data-file=- --project "$PROJECT_ID"
  fi
}

create_or_update_secret "db-password" "$DB_PASSWORD"

if [ ! -f ".deploy_keys/ed25519_private.pem" ]; then
  python scripts/generate_ed25519_keys.py --out .deploy_keys/
  echo "⚠️  Публичный ключ .deploy_keys/ed25519_public.pem нужно скопировать"
  echo "    в licensing/public_key.py клиента ПОСЛЕ первого деплоя."
fi
create_or_update_secret "ed25519-private-key" "$(cat .deploy_keys/ed25519_private.pem)"
create_or_update_secret "admin-api-key" "$(openssl rand -hex 32)"
create_or_update_secret "stripe-secret-key" "${STRIPE_SECRET_KEY:-sk_test_placeholder}"
create_or_update_secret "stripe-webhook-secret" "${STRIPE_WEBHOOK_SECRET:-whsec_placeholder}"

# ── 4. Service Account с минимальными правами ────────────────────────────
if ! gcloud iam service-accounts describe \
  "${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --project "$PROJECT_ID" &>/dev/null; then
  gcloud iam service-accounts create "$SERVICE_ACCOUNT" \
    --display-name="Signer License API" --project "$PROJECT_ID"
fi

for secret in db-password ed25519-private-key admin-api-key \
              stripe-secret-key stripe-webhook-secret; do
  gcloud secrets add-iam-policy-binding "$secret" \
    --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
    --role="roles/secretmanager.secretAccessor" --project "$PROJECT_ID"
done

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/cloudsql.client"

# ── 5. Собрать и запушить образ через Cloud Build ─────────────────────────
gcloud artifacts repositories create "$AR_REPO" \
  --repository-format=docker --location="$REGION" \
  --project "$PROJECT_ID" 2>/dev/null || true

IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/api:latest"
gcloud builds submit --tag "$IMAGE" --project "$PROJECT_ID" .

# ── 6. Деплой на Cloud Run ────────────────────────────────────────────────
gcloud run deploy "$SERVICE_NAME" \
  --image="$IMAGE" \
  --region="$REGION" \
  --platform=managed \
  --service-account="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --add-cloudsql-instances="$CONNECTION_NAME" \
  --set-env-vars="DB_CONNECTION_NAME=${CONNECTION_NAME},DB_USER=${DB_USER},DB_NAME=${DB_NAME}" \
  --set-secrets="DB_PASSWORD=db-password:latest,ED25519_PRIVATE_KEY_PEM=ed25519-private-key:latest,ADMIN_API_KEY=admin-api-key:latest,STRIPE_SECRET_KEY=stripe-secret-key:latest,STRIPE_WEBHOOK_SECRET=stripe-webhook-secret:latest" \
  --min-instances=0 \
  --max-instances=10 \
  --allow-unauthenticated \
  --project "$PROJECT_ID"

# ── 7. Применить миграции (одноразовый Cloud Run Job) ────────────────────
gcloud run jobs create signer-license-migrate \
  --image="$IMAGE" \
  --region="$REGION" \
  --service-account="${SERVICE_ACCOUNT}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --set-cloudsql-instances="$CONNECTION_NAME" \
  --set-env-vars="DB_CONNECTION_NAME=${CONNECTION_NAME},DB_USER=${DB_USER},DB_NAME=${DB_NAME}" \
  --set-secrets="DB_PASSWORD=db-password:latest" \
  --command="alembic" --args="upgrade,head" \
  --project "$PROJECT_ID" 2>/dev/null || \
gcloud run jobs update signer-license-migrate \
  --image="$IMAGE" --project "$PROJECT_ID"

gcloud run jobs execute signer-license-migrate --region="$REGION" --project "$PROJECT_ID" --wait

echo "✅ Готово. URL сервиса:"
gcloud run services describe "$SERVICE_NAME" --region="$REGION" \
  --project "$PROJECT_ID" --format='value(status.url)'
```

Важные детали, которые ИИ-агент должен реализовать в `app/db.py`, чтобы
переменные окружения выше реально сработали:
- В Cloud Run подключение к Cloud SQL идёт через Unix-сокет
  `/cloudsql/<CONNECTION_NAME>`, а НЕ через TCP host/port. Собери
  `DATABASE_URL` внутри `app/config.py` динамически:
  ```python
  if os.environ.get("DB_CONNECTION_NAME"):
      db_socket_dir = "/cloudsql"
      instance_conn = os.environ["DB_CONNECTION_NAME"]
      DATABASE_URL = (
          f"postgresql+psycopg://{DB_USER}:{DB_PASSWORD}@/{DB_NAME}"
          f"?host={db_socket_dir}/{instance_conn}"
      )
  else:
      DATABASE_URL = os.environ["DATABASE_URL"]  # локальная разработка (docker-compose)
  ```
- Секреты, смонтированные через `--set-secrets=VAR=secret:latest`, приходят как
  обычные переменные окружения — не нужен явный вызов Secret Manager API из
  кода приложения (это делает Cloud Run runtime).

---

## 7. `scripts/create_license_manual.py`

CLI для выдачи ключей без Stripe, чтобы можно было начать продавать/тестировать
до готовности биллинга:

```
python scripts/create_license_manual.py \
  --api-url https://signer-license-api-xxxxx.run.app \
  --admin-key <ADMIN_API_KEY из Secret Manager> \
  --plan yearly --duration-days 365 --max-devices 2
```
Выводит созданный `license_key` в stdout. Реализуй через простой `requests.post`
к `/api/admin/licenses`.

---

## 8. Тесты — обязательный минимум

Используй `pytest` + `httpx.AsyncClient` (или `TestClient` FastAPI) + тестовую
БД. Для БД используй **testcontainers-python с реальным Postgres** (не SQLite —
партиционный уникальный индекс и типы `UUID`/`timestamptz` специфичны для
Postgres, тест на SQLite не поймает реальные баги).

Обязательные кейсы:
1. `activate` с валидным ключом, новое устройство → 200, токен валиден по
   `verify_token` тестовым публичным ключом, `device` создан в БД.
2. `activate` с валидным ключом, тем же fingerprint повторно → 200, устройство
   НЕ дублируется (проверь `count(devices) == 1`).
3. `activate` при `max_devices` исчерпаны → `409 DEVICE_LIMIT_REACHED`.
4. `activate` с несуществующим ключом → `404 INVALID_LICENSE`.
5. `activate` с `status = "canceled"` → `403`.
6. `refresh` с токеном отозванного устройства (`deactivated_at` проставлен) →
   `403 DEVICE_DEACTIVATED`.
7. `refresh`, когда лицензия в БД сменила статус на `canceled` после выдачи
   исходного токена → новый токен содержит `status: canceled` (проверка, что
   именно так реализуется отзыв).
8. `deactivate` → повторный `deactivate` того же устройства не падает
   (идемпотентность).
9. Гонка: два параллельных `activate` с новым fingerprint при
   `max_devices - active_count == 1` — ровно один должен получить `200`,
   второй `409` (тест на корректность `SELECT ... FOR UPDATE`).
10. `stripe_webhook` с неверной подписью → `400`, БД не изменена.
11. `stripe_webhook` c `checkout.session.completed` → создаётся `License` с
    правильным `license_key` форматом и уникальностью.
12. Нагрузочный smoke-тест не обязателен, но rate-limiter должен иметь unit-тест
    (превышение лимита → `429`).

---

## 9. Порядок работы (рекомендуемый)

1. Схема БД + Alembic-миграции + модели, тесты на уровне `license_service.py`
   без HTTP (юнит-тесты бизнес-логики напрямую).
2. FastAPI-роуты `activate`/`refresh`/`deactivate` + `admin/licenses`, тесты
   через `TestClient` на локальном Postgres (`docker-compose.dev.yml`).
3. `Dockerfile` + прогон `docker-compose.dev.yml` целиком локально — убедись,
   что `uvicorn` поднимается, миграции применяются, `curl` до `/api/license/activate`
   отвечает.
4. `scripts/deploy_gcloud.sh` — прогони на реальном (тестовом) GCP-проекте,
   убедись что скрипт идемпотентен (запусти дважды подряд).
5. Обнови `configs/settings.py` клиента: `license_server_url` на реальный
   Cloud Run URL. Скопируй сгенерированный публичный ключ в
   `licensing/public_key.py`. Выключи `LICENSE_MOCK_MODE` в
   `licensing/license_client.py`.
6. Ручной сквозной тест: `scripts/create_license_manual.py` → ключ → активация
   в реальном приложении Signer PRIME → перезапуск приложения (проверка
   grace period логики) → деактивация через UI.
7. В последнюю очередь — `stripe_webhook.py` и реальные Stripe-ключи
   (используй Stripe test mode до полной проверки).

---

## 10. Критерии приёмки

- [ ] `docker-compose -f docker-compose.dev.yml up` поднимает рабочий сервис
      локально без доступа к GCP.
- [ ] `pytest` зелёный, включая гонку из п.8 теста №9.
- [ ] `scripts/deploy_gcloud.sh` разворачивает всю инфраструктуру с нуля одной
      командой на чистом GCP-проекте и идемпотентен при повторном запуске.
- [ ] Приватный ключ, пароль БД и Stripe-секреты нигде не встречаются в коде,
      логах или образе контейнера — только в Secret Manager.
- [ ] `curl -X POST .../api/license/activate` с валидным вручную созданным
      ключом возвращает токен, который клиентский `licensing/public_key.py`
      (с реальным публичным ключом) успешно верифицирует.
- [ ] Повторная активация того же устройства не плодит записи в `devices`.
- [ ] Активация сверх `max_devices` возвращает `409 DEVICE_LIMIT_REACHED` с
      телом, которое `ui/widgets/license_dialog.py` уже умеет показывать
      человеку понятным текстом (сверься с `_format_error_message` в
      `licensing/license_manager.py` — коды ошибок должны совпадать).
- [ ] Изменение статуса лицензии в БД вручную (`UPDATE licenses SET status =
      'canceled'`) приводит к тому, что следующий `refresh` с клиента
      возвращает токен с `status: canceled`, и приложение Signer PRIME
      корректно переходит в `LicenseStatus.REVOKED` и просит новый ключ.
