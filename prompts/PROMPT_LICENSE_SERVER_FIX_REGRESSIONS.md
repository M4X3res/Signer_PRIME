# Промпт: исправление регрессий после "завершения" signer-license-server

## Контекст

Предыдущий агент выполнил `PROMPT_LICENSE_SERVER_COMPLETION.md` в основном
качественно: main.py пересобран, Alembic + partial unique index на месте,
Docker/dev-стек работает, admin API и Stripe реализованы, rate limiting
подключён, тесты с testcontainers (включая тест на гонку #9) написаны.

**НЕ переделывай то, что уже работает.** Твоя задача — закрыть конкретные
пробелы и, что важно, исправить регрессию в документации, которую внёс
предыдущий агент (он ухудшил ситуацию вместо того, чтобы её исправить).

Работай **исключительно** в `signer-license-server/`, кроме шага 6
(интеграция с клиентом — если и только если реальный деплой был выполнен
человеком).

---

## Задача 1 (приоритет 0): критический баг в `scripts/deploy_gcloud.sh`

Сейчас скрипт создаёт в Secret Manager только `ed25519-private-key` и
`db-password`, и пробрасывает в Cloud Run только их плюс `DB_CONNECTION_NAME/
DB_USER/DB_NAME`. **`ADMIN_API_KEY`, `STRIPE_SECRET_KEY`,
`STRIPE_WEBHOOK_SECRET` никогда не создаются в Secret Manager и никогда не
попадают в `--set-secrets`/`--set-env-vars` при `gcloud run deploy`.**

Следствие: `app/config.py::Settings.admin_api_key` в проде будет пустой
строкой → `app/routes/admin.py::verify_admin_key` всегда вернёт 500
("Admin API not configured"), и Stripe webhook всегда вернёт 500
("Webhook not configured"). Admin API и Stripe в текущем виде **нерабочие
в продакшне**, несмотря на то, что код для них написан.

Исправь `scripts/deploy_gcloud.sh`:
1. Генерируй `ADMIN_API_KEY` (если не передан через env) через
   `openssl rand -hex 32`, создавай/обновляй секрет `admin-api-key`
   идемпотентно (тем же паттерном `describe && versions add || create`,
   что уже используется для `ed25519-private-key`).
2. Если заданы `STRIPE_SECRET_KEY`/`STRIPE_WEBHOOK_SECRET` в окружении —
   создавай/обновляй секреты `stripe-secret-key`, `stripe-webhook-secret`.
   Если не заданы — пропускай Stripe-секреты, но **явно печатай warning**,
   что Stripe будет недоступен, вместо тихого игнорирования.
3. Добавь все эти секреты в `--set-secrets` при `gcloud run deploy`:
   `ADMIN_API_KEY=admin-api-key:latest` обязательно, Stripe-секреты условно.
4. Прогони скрипт дважды подряд мысленно (или на тестовом проекте, если
   доступ есть) — убедись, что повторный запуск не падает на
   "already exists" ни для одного нового секрета.

## Задача 2 (приоритет 0): недостающие юнит-тесты без HTTP

Исходный промпт (раздел "Порядок работы", пункт 2) явно требовал юнит-тесты
`license_service.py` и криптографии **без HTTP-слоя**, чтобы ловить баги
бизнес-логики раньше интеграционных тестов. Сейчас есть только
`test_routes_*.py`, `test_race_condition.py`, `test_stripe_webhook.py`,
`test_admin_api.py` — все идут через `TestClient`.

Создай:
- `tests/test_crypto.py` — юнит-тесты `app/crypto.py` без БД и без FastAPI:
  `sign_token`/проверка подписи руками через `cryptography`, формат
  `generate_license_key()` (регулярка на `SGNR-XXXX-XXXX-XXXX-XXXX`,
  отсутствие похожих символов O/0/I/1/L), `parse_token` на некорректном
  входе (не 2 части, битый base64, битый JSON — все должны возвращать
  `(False, None, "...")`, а не бросать необработанное исключение).
- `tests/test_license_service.py` — тесты `LicenseService` напрямую (без
  `TestClient`, только `db_session` фикстура из `conftest.py`): активация,
  лимит устройств, refresh с невалидным `device_id` (не-UUID), деактивация
  несуществующего устройства (идемпотентность — должна возвращать
  `{"success": True}`, а не 404).

## Задача 3 (приоритет 1): rate limit тест для `/refresh`

Сейчас `test_rate_limiting_activate` проверяет только `/api/license/activate`
(лимит 10/min). Добавь аналогичный `test_rate_limiting_refresh` для
`/api/license/refresh` (лимит 20/min) в `tests/test_routes_refresh.py`.

## Задача 4 (приоритет 1): CORS hardening

`app/main.py` сейчас жёстко использует `allow_origins=["*"]`. Собственный
README проекта уже отмечает это как TODO, но код не изменён. Сделай источник
разрешённых origin настраиваемым:
- Добавь поле `cors_allowed_origins: str = "*"` в `app/config.py::Settings`
  (запятая-разделённый список, дефолт `"*"` для локальной разработки).
- В `app/main.py` парси это поле в список и передавай в `CORSMiddleware`.
- В `docker-compose.dev.yml` оставь `"*"`. В `scripts/deploy_gcloud.sh`
  добавь `CORS_ALLOWED_ORIGINS` как обязательный/рекомендуемый параметр
  с примером в комментарии, но не блокируй деплой если не задан (дефолт
  на "*" с warning в логах).

## Задача 5 (приоритет 0): исправить документацию — она стала хуже, а не лучше

Исходный промпт прямым текстом требовал: **"оставь один README.md и один
STATUS.md, остальное удали"**. Вместо этого в репозитории сейчас 9
markdown-файлов, включая новые `COMPLETION_SUMMARY.md` и
`EXECUTION_COMPLETE.md` с формулировками "100% ГОТОВО" — это тот самый
антипаттерн, который промпт просил прекратить.

Сделай следующее:
1. **Удали полностью:** `COMPLETION_SUMMARY.md`, `EXECUTION_COMPLETE.md`,
   `CHANGELOG.md`, `QUICKSTART.md`, `PRE_DEPLOYMENT_CHECKLIST.md`,
   `ARCHITECTURE.md`.
2. Из удаляемых файлов перенеси **только фактически полезный контент** (без
   эмодзи-чирлидинга) в оставшиеся два файла:
   - Диаграмму потоков данных из `ARCHITECTURE.md` → в конец `README.md`
     как раздел "Архитектура" (сожми, убери маркетинговый тон).
   - Пункты чек-листа из `PRE_DEPLOYMENT_CHECKLIST.md`, которые ещё не
     выполнены → в `STATUS.md` как раздел "Что осталось сделать".
   - Инструкции интеграции с клиентом из `CLIENT_INTEGRATION.md` → сократи
     и вставь в `README.md`, либо оставь `CLIENT_INTEGRATION.md` как
     единственное **разрешённое** исключение из правила "один STATUS" —
     это не отчёт о прогрессе, а процедурная инструкция для другого
     человека/агента. Если оставляешь — обнови `scripts/validate_structure.py`,
     явно включив его в `EXPECTED_FILES`, а не полагаясь на то, что он
     "просто есть".
3. Перепиши `STATUS.md` **честно**, без слова "ГОТОВО К PRODUCTION"
   применительно ко всей системе. Раздели на:
   - "Реализовано и покрыто тестами" (код + тесты, которые реально
     существуют и проходят).
   - "Код готов, но не проверен end-to-end в реальном облаке" — сюда
     Stripe, admin API в проде, весь Task 9.
   - "Требует действий человека с доступом к GCP/Stripe Dashboard" —
     явный список: реальный деплой, генерация production Ed25519-пары,
     обновление `licensing/public_key.py` и `configs/settings.py` клиента,
     выключение `LICENSE_MOCK_MODE`.
4. Обнови `scripts/validate_structure.py`: добавь
   `COMPLETION_SUMMARY.md`, `EXECUTION_COMPLETE.md`, `CHANGELOG.md`,
   `QUICKSTART.md`, `PRE_DEPLOYMENT_CHECKLIST.md`, `ARCHITECTURE.md` в
   список `DELETED_FILES`, чтобы регрессия (повторное появление подобных
   отчётов в будущем) ловилась автоматически при следующем запуске
   скрипта.

## Задача 6 (условно, только если у тебя есть реальный доступ к GCP/Stripe)

Если тебе не дали реальные GCP-креды и Stripe test-ключи — **не выполняй
этот раздел и не пиши в STATUS.md, что он выполнен.** Явно укажи в
STATUS.md, что раздел 6 пропущен из-за отсутствия доступа к облаку, и что
это первоочередной шаг для человека.

Если доступ есть:
1. `bash scripts/deploy_gcloud.sh` на тестовом проекте, дважды подряд —
   убедись, что второй прогон не падает.
2. `curl https://<url>/health` → 200.
3. `python scripts/create_license_manual.py --server-url <url> --admin-key
   <key> --plan monthly --days 30` → получить реальный ключ.
4. `python scripts/test_api.py --url <url> --admin-key <key>` → все 5 шагов
   зелёные.
5. Только теперь: сгенерируй новую production Ed25519-пару, приватный ключ
   уже в Secret Manager (из шага деплоя), публичный — вставь в
   `licensing/public_key.py` клиента (единственный файл клиента, который
   можно трогать), обнови `license_server_url` в `configs/settings.py`,
   выставь `LICENSE_MOCK_MODE = False` в `licensing/license_client.py`.
6. Ручной сквозной тест по разделу 9 исходного промпта.

## Проверка перед сдачей

- [ ] `scripts/deploy_gcloud.sh` создаёт и пробрасывает `ADMIN_API_KEY` в
      Cloud Run (проверь по коду, что `--set-secrets` включает
      `ADMIN_API_KEY=admin-api-key:latest`).
- [ ] `pytest tests/ -v` зелёный, включая новые `test_crypto.py`,
      `test_license_service.py`, `test_rate_limiting_refresh`.
- [ ] В `signer-license-server/` ровно README.md + STATUS.md (+ опционально
      CLIENT_INTEGRATION.md, если явно решено его оставить и он занесён в
      `validate_structure.py`) — никаких файлов с "100%"/"DONE"/
      "COMPLETE" в названии.
- [ ] `STATUS.md` не утверждает "готово к продакшну", если Задача 9
      реально не выполнена end-to-end.
- [ ] `python scripts/validate_structure.py` проходит и ловит появление
      старых мусорных файлов, если их кто-то восстановит.
- [ ] CORS больше не захардкожен на `"*"` в коде (настраивается через env),
      хотя дефолт для локальной разработки может оставаться `"*"`.
