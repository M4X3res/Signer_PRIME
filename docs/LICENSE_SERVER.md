# Сервер лицензий Signer PRIME

> **ВАЖНО:** Этот документ описывает СЕРВЕРНУЮ часть системы лицензирования,
> которая должна быть развёрнута отдельно (например, на Google Cloud Run).
> Клиентская часть уже интегрирована в основной репозиторий Signer PRIME.

## Архитектура

- **Клиент:** Signer PRIME (desktop приложение, PyQt6)
- **Сервер:** FastAPI (Python) + PostgreSQL (Cloud SQL)
- **Деплой:** Google Cloud Run
- **Оплата:** Stripe (Checkout + Billing Subscriptions)

## Схема БД

```sql
CREATE TABLE licenses (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_key TEXT UNIQUE NOT NULL,
    stripe_customer_id TEXT,
    stripe_subscription_id TEXT,
    plan TEXT NOT NULL,  -- 'monthly' | 'quarterly' | 'yearly'
    status TEXT NOT NULL,  -- 'active' | 'past_due' | 'canceled' | 'expired'
    current_period_end TIMESTAMPTZ NOT NULL,
    max_devices INTEGER NOT NULL DEFAULT 2,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE devices (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    license_id UUID NOT NULL REFERENCES licenses(id) ON DELETE CASCADE,
    fingerprint_hash TEXT NOT NULL,
    device_label TEXT,
    first_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    last_seen TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    deactivated_at TIMESTAMPTZ,
    
    UNIQUE(license_id, fingerprint_hash) WHERE deactivated_at IS NULL
);

CREATE INDEX idx_licenses_key ON licenses(license_key);
CREATE INDEX idx_licenses_stripe_sub ON licenses(stripe_subscription_id);
CREATE INDEX idx_devices_license ON devices(license_id);
CREATE INDEX idx_devices_fingerprint ON devices(fingerprint_hash);
```

## API Endpoints

### POST /api/license/activate

Активировать лицензию на устройстве.

**Request:**
```json
{
  "license_key": "SGNR-XXXX-XXXX-XXXX-XXXX",
  "fingerprint_hash": "sha256_hash_of_device",
  "device_label": "DESKTOP-ABC123",
  "app_version": "2.0.0"
}
```

**Response (200 OK):**
```json
{
  "token": "base64url(payload).base64url(signature)",
  "plan": "monthly",
  "current_period_end": 1735689600
}
```

**Errors:**
- `400 INVALID_LICENSE` - ключ не найден или неверный формат
- `403 LICENSE_EXPIRED` - подписка истекла
- `403 LICENSE_REVOKED` - лицензия отозвана
- `409 DEVICE_LIMIT_REACHED` - достигнут лимит устройств

---

### POST /api/license/refresh

Обновить токен (получить актуальный статус лицензии).

**Request:**
```json
{
  "token": "current_token",
  "fingerprint_hash": "sha256_hash_of_device"
}
```

**Response (200 OK):**
```json
{
  "token": "new_token",
  "plan": "monthly",
  "current_period_end": 1735689600
}
```

**Errors:**
- `401 INVALID_TOKEN` - токен невалиден
- `403 LICENSE_EXPIRED` - подписка истекла
- `403 LICENSE_REVOKED` - лицензия отозвана

---

### POST /api/license/deactivate

Деактивировать устройство (освободить слот).

**Request:**
```json
{
  "token": "current_token"
}
```

**Response (200 OK):**
```json
{
  "success": true
}
```

---

### POST /api/webhooks/stripe

Обработка вебхуков Stripe.

**Headers:**
- `Stripe-Signature` (для верификации)

**Events:**
- `checkout.session.completed` - создание лицензии после оплаты
- `customer.subscription.updated` - обновление статуса подписки
- `customer.subscription.deleted` - отмена подписки
- `invoice.payment_failed` - неудачная оплата

---

## Формат токена

Токен состоит из двух частей: payload и signature (Ed25519).

```
token = base64url(payload) + "." + base64url(signature)
```

**Payload (JSON):**
```json
{
  "license_key": "SGNR-XXXX-XXXX-XXXX-XXXX",
  "device_id": "uuid",
  "plan": "monthly",
  "status": "active",
  "current_period_end": 1735689600,
  "issued_at": 1735603200
}
```

**Подпись:**
- Алгоритм: Ed25519
- Приватный ключ хранится только на сервере (Secret Manager)
- Публичный ключ захардкожен в клиенте (`licensing/public_key.py`)

---

## Генерация ключей Ed25519

```python
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Генерация пары ключей
private_key = ed25519.Ed25519PrivateKey.generate()
public_key = private_key.public_key()

# Экспорт приватного ключа (СЕКРЕТНЫЙ, только на сервере)
private_pem = private_key.private_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PrivateFormat.PKCS8,
    encryption_algorithm=serialization.NoEncryption()
)

# Экспорт публичного ключа (вставить в licensing/public_key.py)
public_pem = public_key.public_bytes(
    encoding=serialization.Encoding.PEM,
    format=serialization.PublicFormat.SubjectPublicKeyInfo
)

print("PRIVATE KEY (Secret Manager):")
print(private_pem.decode())
print("\nPUBLIC KEY (licensing/public_key.py):")
print(public_pem.decode())
```

---

## Генерация лицензионных ключей

Формат: `SGNR-XXXX-XXXX-XXXX-XXXX` (base32, без похожих символов O/0/I/1/L).

```python
import secrets
import base64

def generate_license_key() -> str:
    """Генерирует лицензионный ключ."""
    # 16 байт = 128 бит энтропии
    random_bytes = secrets.token_bytes(16)
    
    # base32 (без padding) и удаляем похожие символы
    b32 = base64.b32encode(random_bytes).decode().rstrip('=')
    
    # Удаляем O, I, L (похожи на 0, 1)
    b32 = b32.replace('O', '2').replace('I', '3').replace('L', '4')
    
    # Форматируем: SGNR-XXXX-XXXX-XXXX-XXXX
    parts = [b32[i:i+4] for i in range(0, 16, 4)]
    return f"SGNR-{'-'.join(parts)}"
```

---

## Интеграция Stripe

### 1. Создание продукта и цен

```bash
# Месячная подписка
stripe prices create \
  --product prod_xxx \
  --unit-amount 1000 \
  --currency usd \
  --recurring[interval]=month

# Квартальная подписка (скидка)
stripe prices create \
  --product prod_xxx \
  --unit-amount 2500 \
  --currency usd \
  --recurring[interval]=month \
  --recurring[interval_count]=3

# Годовая подписка (скидка)
stripe prices create \
  --product prod_xxx \
  --unit-amount 8000 \
  --currency usd \
  --recurring[interval]=year
```

### 2. Создание Checkout Session

```python
import stripe

def create_checkout_session(plan: str):
    price_id = {
        "monthly": "price_xxx",
        "quarterly": "price_yyy",
        "yearly": "price_zzz"
    }[plan]
    
    session = stripe.checkout.Session.create(
        mode="subscription",
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        success_url="https://signer-prime.com/success?session_id={CHECKOUT_SESSION_ID}",
        cancel_url="https://signer-prime.com/pricing",
        client_reference_id=generate_license_key(),  # Предгенерированный ключ
    )
    
    return session.url
```

### 3. Обработка вебхуков

```python
@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, webhook_secret
        )
    except ValueError:
        return JSONResponse({"error": "Invalid payload"}, status_code=400)
    except stripe.error.SignatureVerificationError:
        return JSONResponse({"error": "Invalid signature"}, status_code=400)
    
    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]
        license_key = session["client_reference_id"]
        subscription_id = session["subscription"]
        
        # Создаём лицензию в БД
        await create_license(
            license_key=license_key,
            stripe_customer_id=session["customer"],
            stripe_subscription_id=subscription_id,
            plan="monthly",  # Определить по price_id
            status="active",
            current_period_end=...
        )
    
    elif event["type"] == "customer.subscription.updated":
        subscription = event["data"]["object"]
        await update_license_from_subscription(subscription)
    
    elif event["type"] == "customer.subscription.deleted":
        subscription = event["data"]["object"]
        await update_license_status(subscription["id"], "canceled")
    
    return {"received": True}
```

---

## Деплой на Google Cloud Run

### 1. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

### 2. Сборка и деплой

```bash
# Сборка образа
gcloud builds submit --tag gcr.io/PROJECT_ID/license-server

# Деплой на Cloud Run
gcloud run deploy license-server \
  --image gcr.io/PROJECT_ID/license-server \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=postgresql://..." \
  --set-secrets="ED25519_PRIVATE_KEY=ed25519-key:latest,STRIPE_WEBHOOK_SECRET=stripe-secret:latest"
```

---

## Переменные окружения

```bash
DATABASE_URL=postgresql://user:pass@host:5432/dbname
ED25519_PRIVATE_KEY=<base64 приватного ключа>
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...
CORS_ORIGINS=https://signer-prime.com
```

---

## Безопасность

1. **Ed25519 приватный ключ** - хранить в Secret Manager, никогда в коде/репозитории
2. **Stripe webhook secret** - хранить в Secret Manager
3. **HTTPS** - обязательно (Cloud Run автоматически)
4. **Rate limiting** - защита от brute-force активации (например, 10 попыток/минуту)
5. **CORS** - разрешить только клиентское приложение
6. **SQL injection** - использовать параметризованные запросы (SQLAlchemy/asyncpg)

---

## Мониторинг

- **Google Cloud Logging** - все запросы и ошибки
- **Alerting** - при сбое активации/webhook
- **Metrics** - количество активаций, рефрешей, деактиваций

---

## Тестирование

```bash
# Локальный запуск
uvicorn main:app --reload --port 8000

# Тесты
pytest tests/

# Тестовый вебхук Stripe
stripe trigger checkout.session.completed
```

---

## FAQ

**Q: Можно ли обойти лицензию, подделав токен?**  
A: Нет. Токен подписан Ed25519, приватный ключ только на сервере. Реверс-инжиниринг клиента даёт только публичный ключ, который не позволяет создать валидную подпись.

**Q: Что если пользователь отключит интернет?**  
A: Приложение продолжит работать в течение grace period (10 дней). После этого потребуется онлайн-проверка.

**Q: Как пользователь переносит лицензию на другой компьютер?**  
A: Деактивирует устройство в приложении (освобождает слот) или через личный кабинет на сайте. Затем активирует на новом устройстве тем же ключом.

**Q: Что если пользователь переустановит Windows?**  
A: Fingerprint изменится (новый hardware ID диска), придётся деактивировать старое устройство или обратиться в поддержку для ручного сброса.

---

## Контакты

- **Support:** support@signer-prime.com
- **Docs:** https://docs.signer-prime.com
