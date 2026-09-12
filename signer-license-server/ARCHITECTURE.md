# Архитектура Signer License Server

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Signer PRIME)                       │
│  licensing/license_client.py → verify token with public_key.py      │
└────────────────────┬────────────────────────────────────────────────┘
                     │ HTTPS
                     ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        CLOUD RUN SERVICE                            │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  FastAPI (app/main.py)                                        │  │
│  │  ┌────────────────────────────────────────────────────────┐  │  │
│  │  │  Rate Limiter (slowapi)                                │  │  │
│  │  │   • /activate: 10/min                                  │  │  │
│  │  │   • /refresh: 20/min                                   │  │  │
│  │  └────────────────────────────────────────────────────────┘  │  │
│  │                                                               │  │
│  │  Routes:                                                      │  │
│  │  ┌─────────────────────┐  ┌────────────────────────────────┐│  │
│  │  │ /api/license/*      │  │ /api/admin/licenses            ││  │
│  │  │  - activate         │  │  (X-Admin-Key auth)            ││  │
│  │  │  - refresh          │  │                                ││  │
│  │  │  - deactivate       │  │ /api/webhooks/stripe           ││  │
│  │  └──────────┬──────────┘  │  (signature verify)            ││  │
│  │             │             └────────────┬───────────────────┘│  │
│  │             ▼                          ▼                     │  │
│  │  ┌──────────────────────────────────────────────────────┐   │  │
│  │  │  Services Layer                                      │   │  │
│  │  │  ┌────────────────────┐  ┌─────────────────────────┐│   │  │
│  │  │  │ license_service.py │  │ stripe_service.py       ││   │  │
│  │  │  │  SELECT FOR UPDATE │  │  checkout → create      ││   │  │
│  │  │  │  Race protection   │  │  subscription → update  ││   │  │
│  │  │  └────────────────────┘  └─────────────────────────┘│   │  │
│  │  └──────────────────────┬───────────────────────────────┘   │  │
│  │                         │                                    │  │
│  │  ┌──────────────────────▼───────────────────────────────┐   │  │
│  │  │  crypto.py (Ed25519 signing)                         │   │  │
│  │  │  Private key from Secret Manager                     │   │  │
│  │  └──────────────────────────────────────────────────────┘   │  │
│  └───────────────────────────┬───────────────────────────────────┘  │
└────────────────────────────┬─┴───────────────────────────────────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
┌───────────────────────────┐  ┌──────────────────────────────┐
│   CLOUD SQL (Postgres)    │  │   SECRET MANAGER             │
│                           │  │                              │
│  licenses                 │  │  • ed25519-private-key       │
│  ┌──────────────────────┐ │  │  • admin-api-key             │
│  │ license_key (unique) │ │  │  • db-password               │
│  │ plan, status         │ │  │  • stripe-secret-key         │
│  │ max_devices          │ │  │  • stripe-webhook-secret     │
│  └──────────────────────┘ │  └──────────────────────────────┘
│                           │
│  devices                  │
│  ┌──────────────────────┐ │
│  │ license_id           │ │
│  │ fingerprint_hash     │ │
│  │ deactivated_at       │ │
│  └──────────────────────┘ │
│                           │
│  UNIQUE INDEX:            │
│  (license_id,             │
│   fingerprint_hash)       │
│  WHERE deactivated_at     │
│        IS NULL            │
└───────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         STRIPE                                      │
│  checkout.session.completed → create license                        │
│  customer.subscription.updated → update status                      │
│  customer.subscription.deleted → cancel license                     │
└─────────────────────────────────────────────────────────────────────┘
```

## Потоки данных

### 1. Активация лицензии
```
Client → POST /api/license/activate
  ↓
Rate limiter (10/min)
  ↓
license_service.activate_license()
  ↓
SELECT FOR UPDATE (lock license row)
  ↓
Check: active devices < max_devices?
  ↓ YES
Create/Update device record
  ↓
Partial unique index prevents duplicates
  ↓
Sign token with Ed25519 private key
  ↓
Return token to client
```

### 2. Refresh токена
```
Client → POST /api/license/refresh
  ↓
Rate limiter (20/min)
  ↓
license_service.refresh_license()
  ↓
Parse & validate token signature
  ↓
Fetch latest status from DB
  ↓
Generate new token with current status
  ↓
Return updated token
```

### 3. Stripe webhook
```
Stripe → POST /api/webhooks/stripe
  ↓
Verify signature (CRITICAL)
  ↓ VALID
stripe_service.handle_event()
  ↓
checkout.session.completed:
  → Generate license_key
  → Create License record
  ↓
subscription.updated/deleted:
  → Update License.status
```

## Security Layers

1. **Transport:** HTTPS only (Cloud Run enforced)
2. **Rate Limiting:** slowapi на критичных endpoints
3. **Authentication:**
   - Admin API: X-Admin-Key header (timing-safe compare)
   - Stripe: Webhook signature verification
   - License: Ed25519 token signature
4. **Database:**
   - SELECT FOR UPDATE (row-level locking)
   - Partial unique index (constraint enforcement)
5. **Secrets:** Secret Manager (no hardcoded keys)

## Deployment Flow

```
Developer → bash scripts/deploy_gcloud.sh
  ↓
1. Enable GCP APIs
  ↓
2. Create Artifact Registry
  ↓
3. Create Cloud SQL Postgres 16
  ↓
4. Upload secrets to Secret Manager
  ↓
5. Build & push Docker image
  ↓
6. Deploy Cloud Run service
  ↓
7. Run Alembic migrations (Cloud Run Job)
  ↓
✅ Service live at https://xxx.run.app
```

## Key Design Decisions

| Decision | Rationale |
|----------|-----------|
| **Ed25519** | Faster + smaller signatures than RSA |
| **Partial unique index** | Defense-in-depth против гонок |
| **SELECT FOR UPDATE** | Race condition protection в Python |
| **testcontainers** | Реальный Postgres в тестах, не SQLite |
| **Stripe webhook signature** | Защита от fake webhooks |
| **Rate limiting** | Anti-brute-force на activate/refresh |
| **Secret Manager** | Секреты не в коде/образе/логах |
| **Alembic** | Управляемые миграции вместо create_all() |
| **Multi-stage Docker** | Минимальный размер production образа |
| **Idempotent deploy** | Повторный запуск не ломает инфраструктуру |
