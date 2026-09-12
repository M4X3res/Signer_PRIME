# Signer License Server — Статус реализации

**Дата:** 2026-09-12  
**Версия:** 1.0.0

---

## ✅ Реализовано и покрыто тестами

### 1. Архитектура и код
- [x] `app/main.py` — чистая архитектура без MVP fallback, с rate limiting
- [x] `app/routes/license.py` — activate/refresh/deactivate с rate limiting (10/min, 20/min)
- [x] `app/routes/admin.py` — Admin API с X-Admin-Key защитой
- [x] `app/routes/stripe_webhook.py` — Stripe webhook с проверкой подписи
- [x] `app/services/license_service.py` — SELECT FOR UPDATE защита от гонок
- [x] `app/services/stripe_service.py` — обработка Stripe событий
- [x] `app/config.py` — CORS настраивается через `CORS_ALLOWED_ORIGINS`

### 2. База данных
- [x] Alembic миграции (`alembic.ini`, `migrations/env.py`)
- [x] Миграция `001_initial_schema.py` с partial unique index
- [x] Index: `(license_id, fingerprint_hash) WHERE deactivated_at IS NULL`

### 3. Локальная разработка
- [x] `docker/Dockerfile` — multi-stage build
- [x] `docker-compose.dev.yml` — Postgres + API + Adminer
- [x] `scripts/local_dev_up.sh` — скрипт запуска dev-стека

### 4. Тестирование
- [x] `tests/conftest.py` — testcontainers с реальным Postgres 16
- [x] Тесты #1-8, #12 из промпта (интеграционные через HTTP)
- [x] **Тест #9** — race condition (SELECT FOR UPDATE)
- [x] **Тест #10** — Stripe webhook с неверной подписью
- [x] `tests/test_crypto.py` — юнит-тесты криптографии без HTTP
- [x] `tests/test_license_service.py` — юнит-тесты LicenseService без HTTP
- [x] `tests/test_routes_refresh.py` — включая rate limiting тест (20/min)

### 5. Скрипты
- [x] `scripts/create_license_manual.py` — CLI для создания лицензий
- [x] `scripts/generate_ed25519_keys.py` — генератор ключей
- [x] `scripts/validate_structure.py` — валидация структуры проекта

---

## ⚙️ Код готов, но не проверен end-to-end в реальном облаке

### Deployment на GCP
- [x] `scripts/deploy_gcloud.sh` — идемпотентный скрипт деплоя
- [x] Создание секретов: `ed25519-private-key`, `db-password`, `admin-api-key`
- [x] Условное создание Stripe секретов (`stripe-secret-key`, `stripe-webhook-secret`)
- [x] Передача всех секретов в Cloud Run через `--set-secrets`
- [x] Настройка CORS через переменную окружения `CORS_ALLOWED_ORIGINS`
- [ ] Реальный прогон на тестовом GCP проекте (требует креды)

### Stripe интеграция
- [x] Код обработки webhook событий (`checkout.session.completed`, `customer.subscription.*`)
- [x] Проверка подписи webhook
- [ ] Тестирование с реальными Stripe test-ключами и webhook
- [ ] Настройка webhook URL в Stripe Dashboard

### Admin API
- [x] Эндпоинты создания лицензий с X-Admin-Key защитой
- [ ] Тестирование в реальном проде с реальным `ADMIN_API_KEY` из Secret Manager

---

## 🚧 Требует действий человека с доступом к GCP/Stripe

1. **Первичный деплой на GCP:**
   ```bash
   export PROJECT_ID="your-gcp-project"
   export ED25519_PRIVATE_KEY_PATH="path/to/private_key.pem"
   export STRIPE_SECRET_KEY="sk_test_..."  # опционально
   export STRIPE_WEBHOOK_SECRET="whsec_..."  # опционально
   export CORS_ALLOWED_ORIGINS="https://your-domain.com"  # рекомендуется
   
   bash scripts/deploy_gcloud.sh
   ```

2. **Сгенерировать production Ed25519-пару:**
   ```bash
   python scripts/generate_ed25519_keys.py
   ```
   - Приватный ключ отдать скрипту деплоя
   - Публичный ключ вставить в `licensing/public_key.py` клиента

3. **Обновить клиент:**
   - Скопировать публичный ключ в `licensing/public_key.py`
   - Обновить `license_server_url` в `configs/settings.py`
   - Выставить `LICENSE_MOCK_MODE = False` в `licensing/license_client.py`

4. **Создать тестовую лицензию:**
   ```bash
   python scripts/create_license_manual.py \
     --server-url https://your-server.run.app \
     --admin-key <ADMIN_API_KEY из деплоя> \
     --plan monthly \
     --days 30
   ```

5. **Сквозной тест:**
   - Запустить клиент Signer PRIME
   - Ввести лицензионный ключ
   - Проверить активацию, refresh, деактивацию
   - Проверить работу на нескольких устройствах (лимит)

6. **Настроить Stripe (если нужен):**
   - Добавить webhook URL в Stripe Dashboard: `https://your-server.run.app/api/stripe/webhook`
   - Обновить `STRIPE_WEBHOOK_SECRET` и передеплоить

---

## 📋 Критерии приёмки

| Критерий | Статус |
|----------|--------|
| docker-compose работает локально | ✅ |
| pytest зелёный с тестами на гонку и unit-тестами | ✅ |
| deploy_gcloud.sh создаёт все секреты | ✅ |
| Секреты только в Secret Manager | ✅ |
| Повторная активация не создаёт дубли | ✅ |
| Лимит устройств → 409 | ✅ |
| Status change отражается в refresh | ✅ |
| Rate limiting → 429 | ✅ |
| CORS настраивается через env | ✅ |
| Только README.md + STATUS.md + CLIENT_INTEGRATION.md | ✅ |
| Реальный деплой на GCP выполнен | ⏳ Требует человека |
| Клиент интегрирован с сервером | ⏳ Требует человека |
| Сквозной тест выполнен | ⏳ Требует человека |

---

## 🚀 Что делать дальше

**Для разработчика:**
1. `docker-compose -f docker-compose.dev.yml up` — запустить локально
2. `pytest tests/ -v` — убедиться что тесты проходят

**Для DevOps/владельца GCP:**
1. Выполнить шаги из раздела "Требует действий человека"
2. После реального деплоя обновить этот STATUS.md с результатами

**Текущий статус:** Код протестирован локально и готов к деплою, но реальный production-деплой и интеграция с клиентом требуют доступа к GCP и Stripe.
