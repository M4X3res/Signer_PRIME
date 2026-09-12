# 🚀 Quick Start Guide

**Signer PRIME License Server — из коробки до production за 15 минут**

---

## Вариант 1: Локальная разработка (5 минут)

```bash
cd signer-license-server

# 1. Запустить всё (Postgres + API + Adminer)
docker-compose -f docker-compose.dev.yml up

# 2. Открыть в браузере
# - API Docs: http://localhost:8000/docs
# - Adminer: http://localhost:8081 (user: signer_app, password: dev_password_change_in_prod)

# 3. Создать тестовую лицензию
python scripts/create_license_manual.py \
  --plan monthly \
  --days 30 \
  --devices 2

# 4. Скопировать лицензионный ключ (SGNR-XXXX-XXXX-XXXX-XXXX)
# Готово! Используйте ключ в приложении Signer PRIME
```

---

## Вариант 2: Production на Google Cloud (15 минут)

### Предварительные требования
- Google Cloud Project с включённым billing
- gcloud CLI установлен и настроен

### Шаги

```bash
cd signer-license-server

# 1. Сгенерировать Ed25519 ключи
python scripts/generate_ed25519_keys.py

# Сохраните вывод:
# - Приватный ключ → скопировать в файл private_key.pem
# - Публичный ключ → понадобится для клиента позже

# 2. Настроить переменные окружения
export PROJECT_ID=your-gcp-project-id
export REGION=us-central1
export ADMIN_API_KEY=$(openssl rand -hex 32)
export ED25519_PRIVATE_KEY_PATH=./private_key.pem

# Опционально (для Stripe):
# export STRIPE_SECRET_KEY=sk_live_...
# export STRIPE_WEBHOOK_SECRET=whsec_...

# 3. Проверить окружение
bash scripts/check_env.sh

# 4. Деплой (идемпотентен, можно запускать повторно)
bash scripts/deploy_gcloud.sh

# Ждите ~10 минут. Скрипт создаст:
# - Cloud SQL Postgres 16
# - Artifact Registry
# - Secret Manager секреты
# - Cloud Run сервис
# - Применит миграции БД

# 5. Получить URL сервиса
gcloud run services describe signer-license-server \
  --region=$REGION \
  --format="value(status.url)"

# 6. Проверить работоспособность
curl https://YOUR_SERVICE_URL/health

# 7. Создать первую лицензию
python scripts/create_license_manual.py \
  --server-url https://YOUR_SERVICE_URL \
  --admin-key $ADMIN_API_KEY \
  --plan monthly \
  --days 30

# Готово! Сервис запущен на production
```

---

## Вариант 3: Интеграция с клиентом (5 минут)

После деплоя обновите клиентский код:

```bash
# 1. Открыть файл licensing/public_key.py
# 2. Вставить публичный ключ из шага 1 (вывод generate_ed25519_keys.py)

LICENSE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
<ВСТАВЬТЕ ВАШ ПУБЛИЧНЫЙ КЛЮЧ>
-----END PUBLIC KEY-----
"""

# 3. Обновить configs/settings.py
license_server_url: str = "https://YOUR_SERVICE_URL"

# 4. Выключить mock mode в licensing/license_client.py
LICENSE_MOCK_MODE = False  # Было True

# 5. Запустить Signer PRIME и активировать с ключом из шага 7 выше
```

---

## Troubleshooting (1 минута на проблему)

### Проблема: docker-compose не запускается
```bash
docker-compose -f docker-compose.dev.yml down -v  # Удалить volumes
docker-compose -f docker-compose.dev.yml up       # Запустить заново
```

### Проблема: pytest падает
```bash
pip install -r requirements.txt -r tests/requirements.txt
# Убедитесь, что Docker запущен (testcontainers требует Docker)
```

### Проблема: deploy_gcloud.sh падает
```bash
# Проверить, что вы залогинены
gcloud auth list

# Проверить billing
gcloud beta billing projects describe $PROJECT_ID

# Проверить квоты (Cloud SQL, Cloud Run)
```

### Проблема: "Failed to verify token signature" в клиенте
```bash
# Убедитесь, что публичный ключ в licensing/public_key.py
# соответствует приватному ключу на сервере

# Перегенерируйте ключи и обновите оба:
python scripts/generate_ed25519_keys.py
# → Приватный на сервер (через deploy)
# → Публичный в licensing/public_key.py
```

---

## Полезные команды

```bash
# Логи Cloud Run
gcloud run services logs read signer-license-server --region=$REGION --limit=50

# Перезапуск Cloud Run (применить новые секреты)
gcloud run services update signer-license-server --region=$REGION

# Ручной тест API
python scripts/test_api.py --url https://YOUR_URL --admin-key $ADMIN_API_KEY

# Подключиться к Cloud SQL напрямую
gcloud sql connect signer-license-db --user=signer_app --database=signer_license

# Просмотр лицензий в БД
SELECT license_key, plan, status, max_devices FROM licenses;

# Просмотр активных устройств
SELECT d.device_label, l.license_key 
FROM devices d 
JOIN licenses l ON d.license_id = l.id 
WHERE d.deactivated_at IS NULL;
```

---

## Документация

- 📖 **README.md** — полная документация
- 🏗️ **ARCHITECTURE.md** — диаграммы и дизайн
- ✅ **STATUS.md** — критерии готовности
- 🔗 **CLIENT_INTEGRATION.md** — интеграция с клиентом
- ✅ **PRE_DEPLOYMENT_CHECKLIST.md** — чек-лист перед production
- 📋 **EXECUTION_COMPLETE.md** — отчёт о выполнении промпта

---

## Поддержка

**Проблемы с сервером?**
1. Проверьте логи: `gcloud run services logs read signer-license-server`
2. Health check: `curl https://YOUR_URL/health`
3. API docs: `https://YOUR_URL/docs`

**Вопросы по коду?**
- Все файлы задокументированы
- Тесты показывают примеры использования
- `scripts/test_api.py` — reference implementation

**Нужна помощь?**
- GitHub Issues (если репозиторий публичный)
- Внутренняя документация команды
- Slack / Email support

---

**🎉 Поздравляем! Сервер лицензий готов к работе.**
