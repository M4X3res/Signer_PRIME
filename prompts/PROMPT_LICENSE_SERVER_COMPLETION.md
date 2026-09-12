# Промпт для ИИ-агента: завершение сервера лицензий Signer PRIME (продолжение работы)

## Контекст — прочти перед началом

Ты продолжаешь работу над `signer-license-server/`, начатую предыдущим агентом
по промпту `prompts/PROMPT_LICENSE_SERVER_CLOUD_RUN.md`. **НЕ верь markdown-отчётам
в репозитории** (`FINAL_STATUS.md`, `100_PERCENT_DONE.md`, `IMPLEMENTATION_REPORT.md`,
`PROMPT_EXECUTION_REPORT.md`, `TODO_FOR_AI.md` и др.) — они противоречат друг другу
(где-то написано "70%", где-то "100% done") и не отражают реальное состояние кода.
Ориентируйся **только на факты в коде**, перечисленные ниже.

Работай **исключительно** в `signer-license-server/` — не трогай `core/`,
`processing/`, `server/map_server.py`, `templates/map.html`, `ui/`, `licensing/`
клиента, кроме двух точечных правок в самом конце (см. раздел 7).

---

## 1. Реальное состояние на старте (проверено построчно)

### Готово и рабочее (не переделывать без необходимости)
- `app/models.py`, `app/config.py`, `app/crypto.py`, `app/db.py`, `app/schemas.py`
- `app/services/license_service.py` — activate/refresh/deactivate с `SELECT ... FOR UPDATE`
- `app/routes/license.py` — эндпоинты `/api/license/activate|refresh|deactivate`
- Клиент (`licensing/*`, `ui/widgets/license_dialog.py`, `main.py`, `configs/settings.py`,
  `tests/test_licensing.py`) — полностью готов и не требует изменений

### Сломано и требует немедленного фикса
- **`app/main.py` содержит мёртвый/дублирующий код после `if __name__ == "__main__":`.**
  Там повторно определяется `app.add_middleware(CORSMiddleware, ...)`, заново
  объявляется `class ActivateRequest(BaseModel)` и другие MVP-эндпоинты — но
  `BaseModel` в этом файле **не импортирован** в этой части файла. Если этот код
  вообще исполняется при импорте модуля (top-level statements в Python исполняются
  всегда, `if __name__` не защищает остальной модуль от повторного исполнения
  верхнеуровневого кода, написанного ПОСЛЕ него в том же файле) — это `NameError`
  при старте. Файл нужно полностью переписать с нуля по чистой архитектуре
  (см. раздел 2).

### Отсутствует полностью
- `migrations/` и `alembic.ini` — Alembic не подключен вообще. Сейчас `app/main.py`
  в `startup()` вызывает `Base.metadata.create_all()`, что прямо запрещено
  исходным промптом ("не создавай таблицы через create_all() в проде").
- **Partial unique index** `(license_id, fingerprint_hash) WHERE deactivated_at IS NULL`
  — нигде не создан. Это требование раздела 2 исходного промпта, defence-in-depth
  для лимита устройств на уровне БД, не только в Python.
- `app/routes/admin.py` — эндпоинт для ручного создания лицензий (`POST /api/admin/licenses`,
  защищён `X-Admin-Key`) отсутствует.
- `app/routes/stripe_webhook.py` и `app/services/stripe_service.py` — Stripe-интеграция
  не начата вообще.
- `scripts/deploy_gcloud.sh` — **ключевой скрипт всего промпта**, отсутствует.
- `scripts/create_license_manual.py`, `scripts/generate_ed25519_keys.py` (серверная
  копия), `scripts/local_dev_up.sh` — отсутствуют.
- `docker/Dockerfile`, `docker/.dockerignore`, `docker-compose.dev.yml` — отсутствуют.
- `tests/` для сервера — отсутствует полностью (`test_crypto.py`,
  `test_license_service.py`, `test_routes_activate.py`, `test_routes_refresh.py`,
  `test_routes_deactivate.py`, `test_stripe_webhook.py`, `conftest.py`). Особенно
  критичен тест на гонку (`SELECT FOR UPDATE`, п.10.9 исходного промпта) — сейчас
  никак не проверен, несмотря на то что код в `license_service.py` претендует на
  такую защиту.
- Rate limiting — `slowapi` есть в `requirements.txt`, но нигде не подключён к
  `/api/license/activate` и `/refresh`.
- Реального деплоя не было: `licensing/public_key.py` у клиента содержит временный
  dev-ключ (в самом файле написано "Это временный ключ для разработки"),
  `license_server_url` в `configs/settings.py` указывает на несуществующий
  `https://license.signer-prime.com`, и `LICENSE_MOCK_MODE = True` в
  `licensing/license_client.py` всё ещё включён. То есть ни разу не было
  end-to-end прогона клиент → реальный сервер.

---

## 2. Задача 1 (приоритет 0): пересобрать `app/main.py`

Полностью перепиши `app/main.py` без дублирующегося кода. Целевая архитектура:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.routes import license, admin, stripe_webhook
from app.db import init_db

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()  # только engine/session setup, БЕЗ create_all()
    yield

app = FastAPI(title="Signer PRIME License Server", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(license.router)
app.include_router(admin.router)
app.include_router(stripe_webhook.router)

@app.get("/health")
async def health():
    return {"status": "ok"}
```

Требования:
- **Никакого MVP in-memory фоллбэка.** Если `DATABASE_URL`/`DB_CONNECTION_NAME` не
  настроены — сервер должен упасть при старте с понятной ошибкой, а не тихо
  переключиться на моки. In-memory режим уже выполнил свою роль для раннего
  тестирования клиента и больше не нужен — он маскирует реальные баги.
- Таблицы создаются **только** через `alembic upgrade head` (см. Задачу 2), не через
  `create_all()`.
- Убедись, что модуль **импортируется без побочных ошибок** — прогони
  `python -c "import app.main"` (с настроенными env vars) как smoke-тест сразу после
  переписывания, до перехода к следующей задаче.

---

## 3. Задача 2 (приоритет 0): Alembic-миграции

Создай `alembic.ini`, `migrations/env.py`, `migrations/versions/001_initial_schema.py`.

Обязательно включи в первую миграцию:
```sql
CREATE UNIQUE INDEX uq_active_device
  ON devices (license_id, fingerprint_hash)
  WHERE deactivated_at IS NULL;
```
через `op.execute(...)` — это защита на уровне БД от дублирования активных устройств
даже при гонке запросов, отдельно от `SELECT FOR UPDATE` в Python-коде.

`migrations/env.py` должен брать `DATABASE_URL`/`DB_CONNECTION_NAME` из
`app.config.get_settings()`, а не хардкодить.

Проверка: `alembic upgrade head` на локальном Postgres (docker-compose, см. Задачу 4)
должен создать обе таблицы + partial index без ошибок, и `alembic downgrade base`
должен корректно всё удалить.

---

## 4. Задача 3 (приоритет 1): Docker + локальная разработка

- `docker/Dockerfile` — multi-stage build (builder ставит зависимости в wheels,
  финальный слой — `python:3.12-slim` + `uvicorn app.main:app --host 0.0.0.0 --port $PORT`).
- `docker/.dockerignore` — исключи `.git`, `__pycache__`, `.env`, тесты.
- `docker-compose.dev.yml` — Postgres 16 + сам сервис + (опционально) adminer для
  визуального доступа к БД. Сервис должен на старте (или через отдельный шаг)
  применять `alembic upgrade head`.
- `scripts/local_dev_up.sh` — обёртка над `docker-compose -f docker-compose.dev.yml up`,
  которая ждёт готовности Postgres перед стартом API (healthcheck или `pg_isready` в цикле).

Проверка: `docker-compose -f docker-compose.dev.yml up` поднимает рабочий сервис,
`curl -X POST http://localhost:8000/api/license/activate -d '{...}'` отвечает без
падения контейнера.

---

## 5. Задача 4 (приоритет 1): admin API + ручная выдача ключей

- `app/routes/admin.py`: `POST /api/admin/licenses`, защищён заголовком
  `X-Admin-Key` (сравнение с `settings.admin_api_key`, `secrets.compare_digest`
  для защиты от timing-атак). Тело запроса — `CreateLicenseRequest` из
  `app/schemas.py` (уже есть). Генерирует `license_key` через
  `app.crypto.generate_license_key()` (уже реализовано), создаёт `License` в БД,
  возвращает `CreateLicenseResponse`.
- `scripts/create_license_manual.py` — CLI-обёртка, вызывающая этот эндпоинт через
  `requests.post`, как описано в разделе 7 исходного промпта. Выводит `license_key`
  в stdout и ничего больше (чтобы скрипт был удобен для пайплайнов/копипасты).
- `scripts/generate_ed25519_keys.py` — адаптируй существующий клиентский скрипт
  `scripts/generate_ed25519_keys.py` (в корне основного репозитория Signer) под
  серверный контекст: тот же вывод (приватный + публичный PEM), но с явным
  указанием "приватный ключ → Secret Manager, публичный → клиент".

---

## 6. Задача 5 (приоритет 2): Stripe-интеграция

- `app/services/stripe_service.py`: обработка вебхуков
  `checkout.session.completed`, `customer.subscription.updated`,
  `customer.subscription.deleted`. При `checkout.session.completed` — создать
  `License` (план берётся из Stripe Price ID → маппинг на `monthly|quarterly|yearly`,
  вынеси маппинг в конфиг/константу). При `subscription.deleted` или переходе в
  `canceled`/`unpaid` — обнови `status` существующей `License` по
  `stripe_subscription_id`.
- `app/routes/stripe_webhook.py`: `POST /api/webhooks/stripe`. **Обязательно**
  проверяй подпись через `stripe.Webhook.construct_event(payload, sig_header,
  settings.stripe_webhook_secret)` — неверная подпись должна давать `400` и
  **не изменять БД** (это тест №10 из исходного промпта).
- Используй Stripe test mode для разработки, реальные ключи подключай в последнюю
  очередь (см. порядок работы в разделе 9 исходного промпта — это осознанный выбор,
  не меняй порядок).

---

## 7. Задача 6 (приоритет 1): rate limiting

Подключи `slowapi` (уже в `requirements.txt`) к `app/main.py`:
```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
```
Примени `@limiter.limit("10/minute")` (подбери разумное значение) как минимум к
`/api/license/activate` и `/api/license/refresh` — это точки, которые легче всего
задосить перебором ключей. Добавь юнит-тест, что превышение лимита даёт `429`
(это явно указано в критерии приёмки исходного промпта, п.12 раздела 8).

---

## 8. Задача 7 (приоритет 0 для критериев приёмки): тесты

Создай `tests/conftest.py` с фикстурой на **реальный Postgres через testcontainers**
(не SQLite — partial unique index и типы `UUID`/`timestamptz` специфичны для
Postgres, промпт явно это требует). Фикстура должна:
1. Поднять `PostgresContainer("postgres:16")`.
2. Прогнать `alembic upgrade head` на нём (не `create_all()`).
3. Дать сессию SQLAlchemy тестам.
4. Дать тестовую пару Ed25519-ключей (через `cryptography` напрямую, не через
   реальный Secret Manager).

Реализуй **все** кейсы из раздела 8 исходного промпта — особенно:
- **Тест №9 (гонка):** два параллельных `activate` с новым fingerprint при
  `max_devices - active_count == 1`. Используй `concurrent.futures.ThreadPoolExecutor`
  или `asyncio.gather` с двумя отдельными сессиями БД, запущенными по-настоящему
  параллельно (не последовательно в одном потоке — иначе тест ничего не проверяет).
  Ровно один должен получить `200`, второй — `409 DEVICE_LIMIT_REACHED`.
- **Тест №2:** повторная активация того же fingerprint не создаёт вторую запись
  `Device` — проверь `count(devices) == 1` в БД напрямую, не только по ответу API.
- **Тест №7:** после `activate` вручную смени `status` лицензии в БД на `canceled`,
  вызови `refresh` — убедись, что новый токен содержит `status: canceled` (это и
  есть механизм отзыва, клиент уже умеет на это реагировать через
  `LicenseManager.check_local_status()`).
- **Тест №10:** вебхук с неверной Stripe-подписью → `400`, ни одна запись в БД
  не создана и не изменена (сравни snapshot таблиц до/после).

Прогони `pytest` полностью зелёным перед переходом дальше.

---

## 9. Задача 8 (приоритет 2): `scripts/deploy_gcloud.sh`

Реализуй по образцу, уже частично описанному в исходном промпте (раздел 6, там
есть готовый скелет команд `gcloud`). Скрипт должен быть **идемпотентным** —
прогони его дважды подряд на тестовом GCP-проекте и убедись, что второй запуск
не падает на "resource already exists" (используй `|| true` или явные проверки
существования там, где `gcloud ... create` не идемпотентен по умолчанию — в
черновике промпта это уже частично сделано для Artifact Registry и Cloud Run Job,
доделай для Cloud SQL instance и секретов).

Не запускай реальный деплой на прод, пока не пройдены Задачи 1–7 и локальный
`docker-compose` не подтверждён рабочим — деплоить сломанный `main.py` на Cloud Run
бессмысленно.

---

## 10. Задача 9 (в самом конце, после реального деплоя и зелёных тестов): интеграция с клиентом

Только когда сервер реально развёрнут на Cloud Run и вручную проверен через
`curl`/`scripts/create_license_manual.py`:

1. Сгенерируй **новую** production-пару Ed25519 через
   `scripts/generate_ed25519_keys.py`. Приватный ключ — в Secret Manager (уже
   должно быть сделано скриптом деплоя), публичный — вставь в
   `licensing/public_key.py` клиента, заменив текущий dev-плейсхолдер (файл
   `LICENSE_PUBLIC_KEY_PEM = """..."""`, единственное место, которое трогаешь в
   клиентском коде).
2. Обнови `license_server_url` в `configs/settings.py` клиента на реальный
   Cloud Run URL.
3. Выключи `LICENSE_MOCK_MODE = False` в `licensing/license_client.py`.
4. Ручной сквозной тест (раздел 9, шаг 6 исходного промпта): создать ключ через
   `create_license_manual.py` → активировать в реальном приложении Signer PRIME
   → перезапустить приложение и проверить, что grace period логика работает
   офлайн → деактивировать устройство через UI → убедиться, что слот
   освободился в БД.

---

## 11. Задача 10: уборка документации

В `signer-license-server/` сейчас минимум 6 markdown-файлов с противоречивыми
процентами готовности (`FINAL_STATUS.md`, `100_PERCENT_DONE.md`,
`IMPLEMENTATION_STATUS.md`, `IMPLEMENTATION_REPORT.md`, `PROMPT_EXECUTION_REPORT.md`,
`TODO_FOR_AI.md`). После завершения задач 1–9:
- Оставь **один** `README.md` с реальными инструкциями запуска (локально +
  деплой) и **один** `STATUS.md` с честным текущим состоянием (что готово, что
  нет, со ссылкой на актуальные критерии приёмки).
- Удали остальные отчётные файлы — они не несут ценности и создают путаницу для
  следующего человека/агента, который откроет репозиторий.

---

## Критерии приёмки (дословно из исходного промпта — не считай задачу
## завершённой, пока не выполнены все пункты)

- [ ] `docker-compose -f docker-compose.dev.yml up` поднимает рабочий сервис
      локально без доступа к GCP.
- [ ] `pytest` зелёный, включая тест на гонку (`SELECT FOR UPDATE`).
- [ ] `scripts/deploy_gcloud.sh` разворачивает всю инфраструктуру с нуля одной
      командой на чистом GCP-проекте и идемпотентен при повторном запуске.
- [ ] Приватный ключ, пароль БД и Stripe-секреты нигде не встречаются в коде,
      логах или образе контейнера — только в Secret Manager.
- [ ] `curl -X POST .../api/license/activate` с валидным вручную созданным
      ключом возвращает токен, который клиентский `licensing/public_key.py`
      (с реальным публичным ключом) успешно верифицирует.
- [ ] Повторная активация того же устройства не плодит записи в `devices`.
- [ ] Активация сверх `max_devices` возвращает `409 DEVICE_LIMIT_REACHED`.
- [ ] Изменение статуса лицензии в БД вручную (`UPDATE licenses SET status =
      'canceled'`) приводит к тому, что следующий `refresh` с клиента
      возвращает токен с `status: canceled`, и приложение Signer PRIME
      корректно переходит в `LicenseStatus.REVOKED` и просит новый ключ.
- [ ] Rate limiting на `/activate` и `/refresh` подтверждён тестом на `429`.
- [ ] В репозитории остался один README и один STATUS-файл с честным описанием
      состояния, все противоречивые "100% done" отчёты удалены.

## Порядок работы (не меняй без причины)

1. Задача 1 (починить `main.py`) → 2 (Alembic) — без этого ничего остальное не
   имеет смысла проверять.
2. Задача 7 (тесты) частично — юнит-тесты `license_service.py` без HTTP, чтобы
   ловить баги бизнес-логики рано.
3. Задача 3 (Docker) — прогони локально весь стек.
4. Задача 7 полностью (HTTP-тесты через `TestClient` на локальном Postgres).
5. Задача 4 (admin API) → 6 (rate limiting).
6. Задача 8 (`deploy_gcloud.sh`) на тестовом GCP-проекте.
7. Задача 5 (Stripe) — в последнюю очередь, как и указано в исходном промпте.
8. Задача 9 (реальная интеграция с клиентом) — только после всего вышеперечисленного.
9. Задача 10 (уборка документации) — в самом конце.
