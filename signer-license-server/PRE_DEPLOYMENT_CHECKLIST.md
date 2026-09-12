# Pre-Deployment Checklist

Используйте этот чек-лист перед деплоем на production.

## ✅ Код и структура

- [ ] `python scripts/smoke_test.py` — все модули импортируются
- [ ] `python scripts/validate_structure.py` — структура полная
- [ ] Все тесты зелёные: `pytest tests/ -v`
- [ ] `.gitignore` исключает секреты (*.pem, *.key, .env)
- [ ] Нет hardcoded секретов в коде (grep -r "sk_live_" не находит)

## ✅ Локальная разработка

- [ ] `docker-compose -f docker-compose.dev.yml up` запускается
- [ ] Health check работает: `curl http://localhost:8000/health`
- [ ] API docs доступны: http://localhost:8000/docs
- [ ] Adminer открывается: http://localhost:8081
- [ ] Миграции применяются: `alembic upgrade head`
- [ ] Создание лицензии работает: `python scripts/create_license_manual.py`

## ✅ Тестирование

- [ ] Все unit-тесты зелёные
- [ ] Тест на race condition (#9) проходит
- [ ] Тест на Stripe webhook signature (#10) проходит
- [ ] Rate limiting тест (#12) проходит
- [ ] `python scripts/test_api.py --url http://localhost:8000 --admin-key test_key`

## ✅ Безопасность

- [ ] Сгенерированы новые Ed25519 ключи (не dev ключи!)
- [ ] `ADMIN_API_KEY` — криптографически случайный (32+ символов)
- [ ] Приватный ключ сохранён безопасно (Secret Manager / KMS)
- [ ] Публичный ключ скопирован для клиента
- [ ] Stripe ключи — production (начинаются с `sk_live_`, `whsec_`)
- [ ] `DB_PASSWORD` — сильный пароль (не "dev_password")

## ✅ GCP конфигурация

- [ ] `PROJECT_ID` установлен и проект существует
- [ ] `REGION` выбран (рекомендуется `us-central1`)
- [ ] gcloud CLI установлен: `gcloud --version`
- [ ] Аутентифицирован: `gcloud auth list`
- [ ] Billing включён для проекта
- [ ] Квоты проверены (Cloud SQL, Cloud Run)

## ✅ Переменные окружения

Обязательные:
- [ ] `PROJECT_ID`
- [ ] `REGION`
- [ ] `ADMIN_API_KEY`
- [ ] `ED25519_PRIVATE_KEY_PATH` (файл существует)

Опциональные (для Stripe):
- [ ] `STRIPE_SECRET_KEY`
- [ ] `STRIPE_WEBHOOK_SECRET`

Проверка: `bash scripts/check_env.sh`

## ✅ Deployment

- [ ] `bash scripts/deploy_gcloud.sh` выполнен без ошибок
- [ ] Cloud Run сервис запущен: `gcloud run services list`
- [ ] Health check отвечает: `curl https://YOUR_URL/health`
- [ ] Логи чистые: `gcloud run services logs read signer-license-server`
- [ ] Миграции применены (проверить Cloud Run Job logs)

## ✅ Post-Deployment проверки

- [ ] Создать тестовую лицензию через admin API
- [ ] Активировать лицензию через `/api/license/activate`
- [ ] Refresh токена работает
- [ ] Деактивация устройства работает
- [ ] Лимит устройств соблюдается (попробовать превысить)

## ✅ Stripe интеграция (если используется)

- [ ] Продукты созданы в Stripe Dashboard
- [ ] Price IDs скопированы в `app/services/stripe_service.py`
- [ ] Webhook endpoint настроен: `https://YOUR_URL/api/webhooks/stripe`
- [ ] Webhook secret получен и сохранён в Secret Manager
- [ ] Тестовый checkout создаёт лицензию в БД

## ✅ Клиентская интеграция

- [ ] Публичный ключ вставлен в `licensing/public_key.py`
- [ ] `license_server_url` обновлён в `configs/settings.py`
- [ ] `LICENSE_MOCK_MODE = False` в `licensing/license_client.py`
- [ ] Сквозной тест: активация → перезапуск приложения → работает

## ✅ Мониторинг

- [ ] Настроены алерты на high error rate (рекомендуется)
- [ ] Настроен мониторинг latency (рекомендуется)
- [ ] Cloud SQL backups включены (рекомендуется)
- [ ] Установлен retention для логов

## ✅ Документация

- [ ] README.md актуален
- [ ] CLIENT_INTEGRATION.md содержит реальные URLs
- [ ] Команда знает, как создавать лицензии вручную
- [ ] Runbook для troubleshooting подготовлен

## ✅ Rollback план

- [ ] Предыдущая версия image сохранена в Artifact Registry
- [ ] Команда откатa: `gcloud run services update-traffic --to-revisions=PREV_REVISION=100`
- [ ] Backups БД сделаны перед миграциями

---

## Быстрая проверка (5 минут)

```bash
# 1. Код
python scripts/smoke_test.py
pytest tests/ -v

# 2. Окружение
bash scripts/check_env.sh

# 3. Локальный тест
docker-compose -f docker-compose.dev.yml up -d
curl http://localhost:8000/health
python scripts/test_api.py --url http://localhost:8000 --admin-key dev_admin_key_change_in_prod

# 4. Deploy
bash scripts/deploy_gcloud.sh

# 5. Production тест
SERVICE_URL=$(gcloud run services describe signer-license-server --region=$REGION --format="value(status.url)")
curl $SERVICE_URL/health
python scripts/test_api.py --url $SERVICE_URL --admin-key $ADMIN_API_KEY
```

---

## ❌ Красные флаги (не деплойте, если видите)

- ❌ Тесты падают
- ❌ Hardcoded секреты в коде
- ❌ Dev ключи Ed25519 используются
- ❌ `LICENSE_MOCK_MODE = True` в production
- ❌ `allow_origins=["*"]` в CORS (без ограничений)
- ❌ `ADMIN_API_KEY = "dev_admin_key_change_in_prod"`
- ❌ Миграции не применились
- ❌ Health check не отвечает
- ❌ Ошибки в логах Cloud Run

---

## ✅ Go/No-Go Decision

**GO для production, если:**
- ✅ Все обязательные чекбоксы отмечены
- ✅ Нет красных флагов
- ✅ Локальные и deployment тесты прошли
- ✅ Команда знает runbook

**NO-GO, если:**
- ❌ Хотя бы один красный флаг
- ❌ Тесты не все зелёные
- ❌ Секреты не настроены правильно
