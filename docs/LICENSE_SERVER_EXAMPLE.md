# Серверная часть системы лицензирования - Пример реализации

> **ВНИМАНИЕ:** Этот файл содержит ПРИМЕР кода для серверной части.
> Реальный сервер должен быть развёрнут в отдельном репозитории.

## Структура сервера

```
license-server/
├── main.py              # FastAPI приложение
├── models.py            # SQLAlchemy модели
├── auth.py              # Ed25519 подпись токенов
├── database.py          # Подключение к БД
├── stripe_webhooks.py   # Обработка Stripe webhooks
├── requirements.txt     # Зависимости
├── Dockerfile           # Docker образ
└── .env.example         # Пример переменных окружения
```

## Пример main.py

```python
from fastapi import FastAPI, HTTPException, Request, Header
from pydantic import BaseModel
import stripe
import os
from datetime import datetime, timedelta
from database import get_db, License, Device
from auth import sign_token, verify_signature
from sqlalchemy.orm import Session
from sqlalchemy import and_

app = FastAPI(title="Signer PRIME License Server")

# ════════════════════════════════════════════════════════════════
# Модели запросов
# ════════════════════════════════════════════════════════════════

class ActivateRequest(BaseModel):
    license_key: str
    fingerprint_hash: str
    device_label: str
    app_version: str

class RefreshRequest(BaseModel):
    token: str
    fingerprint_hash: str

class DeactivateRequest(BaseModel):
    token: str

# ════════════════════════════════════════════════════════════════
# Эндпоинты
# ════════════════════════════════════════════════════════════════

@app.post("/api/license/activate")
async def activate_license(req: ActivateRequest, db: Session = Depends(get_db)):
    \"\"\"Активация лицензии на устройстве.\"\"\"
    
    # Найти лицензию
    license = db.query(License).filter(
        License.license_key == req.license_key
    ).first()
    
    if not license:
        raise HTTPException(status_code=400, detail={
            "error_code": "INVALID_LICENSE",
            "error": "License key not found"
        })
    
    # Проверить статус
    if license.status != "active":
        raise HTTPException(status_code=403, detail={
            "error_code": "LICENSE_REVOKED",
            "error": f"License status: {license.status}"
        })
    
    # Проверить дату окончания
    if license.current_period_end < datetime.utcnow():
        raise HTTPException(status_code=403, detail={
            "error_code": "LICENSE_EXPIRED",
            "error": "License period has ended"
        })
    
    # Проверить/регистрировать устройство
    existing_device = db.query(Device).filter(
        and_(
            Device.license_id == license.id,
            Device.fingerprint_hash == req.fingerprint_hash,
            Device.deactivated_at == None
        )
    ).first()
    
    if existing_device:
        # Устройство уже зарегистрировано - обновляем last_seen
        existing_device.last_seen = datetime.utcnow()
        db.commit()
        device_id = str(existing_device.id)
    else:
        # Новое устройство - проверяем лимит
        active_devices = db.query(Device).filter(
            and_(
                Device.license_id == license.id,
                Device.deactivated_at == None
            )
        ).count()
        
        if active_devices >= license.max_devices:
            raise HTTPException(status_code=409, detail={
                "error_code": "DEVICE_LIMIT_REACHED",
                "error": f"Maximum {license.max_devices} devices allowed"
            })
        
        # Регистрируем новое устройство
        new_device = Device(
            license_id=license.id,
            fingerprint_hash=req.fingerprint_hash,
            device_label=req.device_label
        )
        db.add(new_device)
        db.commit()
        device_id = str(new_device.id)
    
    # Генерируем токен
    token = sign_token({
        "license_key": license.license_key,
        "device_id": device_id,
        "plan": license.plan,
        "status": license.status,
        "current_period_end": int(license.current_period_end.timestamp()),
        "issued_at": int(datetime.utcnow().timestamp())
    })
    
    return {
        "token": token,
        "plan": license.plan,
        "current_period_end": int(license.current_period_end.timestamp())
    }


@app.post("/api/license/refresh")
async def refresh_license(req: RefreshRequest, db: Session = Depends(get_db)):
    \"\"\"Обновление токена лицензии.\"\"\"
    
    # Декодируем текущий токен (без проверки подписи - только для извлечения данных)
    import base64, json
    try:
        payload_b64 = req.token.split(".")[0]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64.replace('-', '+').replace('_', '/')).decode()
        payload = json.loads(payload_json)
    except Exception:
        raise HTTPException(status_code=401, detail={
            "error_code": "INVALID_TOKEN",
            "error": "Token format invalid"
        })
    
    # Найти лицензию
    license = db.query(License).filter(
        License.license_key == payload["license_key"]
    ).first()
    
    if not license:
        raise HTTPException(status_code=401, detail={
            "error_code": "INVALID_TOKEN",
            "error": "License not found"
        })
    
    # Проверить статус
    if license.status != "active":
        raise HTTPException(status_code=403, detail={
            "error_code": "LICENSE_REVOKED",
            "error": f"License status: {license.status}"
        })
    
    # Проверить дату окончания
    if license.current_period_end < datetime.utcnow():
        raise HTTPException(status_code=403, detail={
            "error_code": "LICENSE_EXPIRED",
            "error": "License period has ended"
        })
    
    # Обновить last_seen устройства
    device = db.query(Device).filter(
        and_(
            Device.license_id == license.id,
            Device.fingerprint_hash == req.fingerprint_hash,
            Device.deactivated_at == None
        )
    ).first()
    
    if device:
        device.last_seen = datetime.utcnow()
        db.commit()
    
    # Генерируем новый токен
    token = sign_token({
        "license_key": license.license_key,
        "device_id": payload["device_id"],
        "plan": license.plan,
        "status": license.status,
        "current_period_end": int(license.current_period_end.timestamp()),
        "issued_at": int(datetime.utcnow().timestamp())
    })
    
    return {
        "token": token,
        "plan": license.plan,
        "current_period_end": int(license.current_period_end.timestamp())
    }


@app.post("/api/license/deactivate")
async def deactivate_device(req: DeactivateRequest, db: Session = Depends(get_db)):
    \"\"\"Деактивация устройства.\"\"\"
    
    # Декодируем токен
    import base64, json
    try:
        payload_b64 = req.token.split(".")[0]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64.replace('-', '+').replace('_', '/')).decode()
        payload = json.loads(payload_json)
    except Exception:
        raise HTTPException(status_code=401, detail={
            "error_code": "INVALID_TOKEN",
            "error": "Token format invalid"
        })
    
    # Найти устройство
    device = db.query(Device).filter(
        Device.id == payload["device_id"]
    ).first()
    
    if not device:
        raise HTTPException(status_code=404, detail={
            "error_code": "DEVICE_NOT_FOUND",
            "error": "Device not found"
        })
    
    # Деактивировать
    device.deactivated_at = datetime.utcnow()
    db.commit()
    
    return {"success": True}


@app.post("/api/webhooks/stripe")
async def stripe_webhook(request: Request, stripe_signature: str = Header(None)):
    \"\"\"Обработка Stripe webhooks.\"\"\"
    
    payload = await request.body()
    webhook_secret = os.getenv("STRIPE_WEBHOOK_SECRET")
    
    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, webhook_secret
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
    # Обработка событий
    if event["type"] == "checkout.session.completed":
        # Создание лицензии после оплаты
        session = event["data"]["object"]
        # ... (см. docs/LICENSE_SERVER.md)
        pass
    
    elif event["type"] == "customer.subscription.updated":
        # Обновление подписки
        subscription = event["data"]["object"]
        # ... (см. docs/LICENSE_SERVER.md)
        pass
    
    elif event["type"] == "customer.subscription.deleted":
        # Отмена подписки
        subscription = event["data"]["object"]
        # ... (см. docs/LICENSE_SERVER.md)
        pass
    
    return {"received": True}


# ════════════════════════════════════════════════════════════════
# Health check
# ════════════════════════════════════════════════════════════════

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "signer-license-server"}
```

## Пример auth.py (Ed25519)

```python
import os
import json
import base64
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

# Загрузка приватного ключа из Secret Manager
PRIVATE_KEY_PEM = os.getenv("ED25519_PRIVATE_KEY")
private_key = serialization.load_pem_private_key(
    PRIVATE_KEY_PEM.encode(),
    password=None
)

def sign_token(payload: dict) -> str:
    \"\"\"Подписывает payload и возвращает токен.\"\"\"
    payload_json = json.dumps(payload, sort_keys=True)
    payload_bytes = payload_json.encode()
    
    signature = private_key.sign(payload_bytes)
    
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip('=')
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    
    return f"{payload_b64}.{signature_b64}"
```

## requirements.txt

```
fastapi>=0.104.0
uvicorn[standard]>=0.24.0
sqlalchemy>=2.0.0
psycopg2-binary>=2.9.0
stripe>=7.0.0
cryptography>=41.0.0
python-dotenv>=1.0.0
```

## Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV PORT=8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

## .env.example

```
DATABASE_URL=postgresql://user:pass@localhost:5432/licenses
ED25519_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"
STRIPE_API_KEY=sk_test_...
STRIPE_WEBHOOK_SECRET=whsec_...
CORS_ORIGINS=https://signer-prime.com
```

## Деплой на Google Cloud Run

```bash
# Сборка
gcloud builds submit --tag gcr.io/PROJECT_ID/license-server

# Деплой
gcloud run deploy license-server \
  --image gcr.io/PROJECT_ID/license-server \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars="DATABASE_URL=..." \
  --set-secrets="ED25519_PRIVATE_KEY=...,STRIPE_WEBHOOK_SECRET=..."
```

---

**Полная документация:** `docs/LICENSE_SERVER.md`
