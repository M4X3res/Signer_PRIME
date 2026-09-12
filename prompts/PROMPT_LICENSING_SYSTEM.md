# Промпт для ИИ-агента: система лицензирования Signer PRIME (подписка)

Ты работаешь над проектом **Signer PRIME / RoadScanner** — desktop-приложением на
PyQt6 для детекции дорожных знаков по видео с GPS-треком. Твоя задача — добавить
**систему лицензирования по подписке** (месяц / 3 месяца / год) без единой строчки
поломок в существующем пайплайне обработки видео/карты.

---

## 0. КРИТИЧЕСКИ ВАЖНОЕ ОГРАНИЧЕНИЕ — прочитай перед началом работы

В проекте уже есть локальный Flask-сервер `server/map_server.py`, запускаемый
`server/server_thread.py` в `QThread` на `127.0.0.1:3000`. Он отдаёт карту,
GeoJSON и видео-клипы **из локальных файлов пользователя** и не имеет НИКАКОГО
отношения к лицензированию.

**Новый сервер лицензий — это отдельный, независимый сервис**, который будет
задеплоен отдельно (Google Cloud Run / Cloud Functions), имеет свой публичный
HTTPS-домен и работает как классический REST API.

Правила, которые нельзя нарушать:
- НЕ добавляй лицензионные роуты в `server/map_server.py` и НЕ используй порт 3000.
- НЕ давай серверу лицензий доступ к видео/GPS/GeoJSON пользователя — туда уходит
  только: ключ лицензии, fingerprint устройства, версия приложения, метаданные подписки.
- Клиентский код лицензирования должен работать **полностью отдельным HTTP-клиентом**
  (`requests`), обращающимся на внешний домен, никак не связанным с `ServerThread`.
- Если сервер лицензий недоступен (нет интернета/сервер упал) — приложение обязано
  продолжать работать в рамках grace period (см. ниже), а НЕ падать и не блокировать
  обработку видео.
- Не трогай `core/`, `processing/`, `templates/map.html` — они не связаны с задачей.

---

## 1. Архитектура решения

### 1.1. Модель лицензии
Онлайн-активация с офлайн grace period (не чистый офлайн — нужна отзываемость и
контроль подписки по времени):

1. Пользователь оплачивает подписку на сайте (Stripe Billing) → в БД сервера
   создаётся/обновляется запись лицензии: `{license_key, plan, status, current_period_end, max_devices}`.
2. При первом запуске приложение показывает диалог ввода ключа. Ключ отправляется
   на сервер вместе с **hardware fingerprint** этого ПК.
3. Сервер:
   - Проверяет, что ключ существует, активен, не превышен лимит устройств.
   - Регистрирует устройство (или обновляет `last_seen`, если уже зарегистрировано).
   - Выдаёт **подписанный токен** (Ed25519-подпись, НЕ симметричный HMAC — см. п. 3.2)
     с полями: `license_key, device_id, plan, status, current_period_end, issued_at`.
4. Клиент сохраняет токен локально (файл в `%LOCALAPPDATA%\Signer\license.token`,
   НЕ в реестре/QSettings, чтобы легче было переносить/бэкапить отдельно).
5. При каждом запуске приложения:
   - Проверяется подпись токена локально, офлайн, мгновенно (публичный ключ Ed25519
     зашит в бинарник — см. п. 3.2).
   - Проверяется `current_period_end > now()`.
   - Если с последней успешной онлайн-проверки прошло больше `REFRESH_INTERVAL_DAYS`
     (по умолчанию 3 дня) — фоново (не блокируя UI) стучимся на `/api/license/refresh`
     за свежим токеном.
   - Если сервер недоступен дольше `GRACE_PERIOD_DAYS` (по умолчанию 10 дней с
     момента `issued_at` последнего успешно полученного токена) — приложение
     блокирует запуск и требует онлайн-проверку.
   - Если сервер вернул `status: revoked/expired/canceled` — токен считается
     недействительным немедленно, приложение просит новый ключ или продление.

### 1.2. Защита от абузов (заложи это в реализацию)
- **Лимит устройств на ключ** (`max_devices`, по умолчанию 2) — сервер отклоняет
  активацию сверх лимита с понятной ошибкой `DEVICE_LIMIT_REACHED`.
- **Fingerprint = хэш нескольких источников**, а не одного (чтобы нельзя было
  обойти подменой одного параметра): серийный номер системного диска + MAC первого
  физического сетевого адаптера + CPU ID/имя процессора. Хэшируй SHA-256, храни
  только хэш, не сырые данные.
- **Самостоятельная деактивация устройства** — кнопка в UI "Деактивировать это
  устройство", дергает `/api/license/deactivate`, освобождает слот в `max_devices`.
- **Защита от отката системных часов**: если локальное `now()` меньше, чем
  `issued_at` последнего сохранённого токена — считать это подозрительным и
  форсировать немедленную онлайн-проверку (а не доверять локальным часам).
- Подпись токена — асимметричная (Ed25519), приватный ключ только на сервере,
  публичный — в клиенте. Так реверс-инжиниринг клиента не даёт возможности
  подделать токен (в отличие от HMAC с общим секретом).

### 1.3. Оплата
Используй **Stripe** (Checkout + Billing Subscriptions):
- Сайт (вне scope этого промпта, но сервер должен быть готов) создаёт Stripe Checkout
  Session для выбранного плана (`price_month`, `price_3month`, `price_year`).
- После оплаты Stripe шлёт вебхуки: `checkout.session.completed`,
  `customer.subscription.updated`, `customer.subscription.deleted`,
  `invoice.payment_failed`.
- Сервер лицензий обрабатывает вебхуки и обновляет статус/`current_period_end`
  ключа в БД. Генерация `license_key` происходит при `checkout.session.completed`
  (или заранее, и передаётся как `client_reference_id`) — реши сам, но ключ должен
  быть человекочитаемым для ручной поддержки, формат: `SGNR-XXXX-XXXX-XXXX-XXXX`
  (base32, без похожих символов O/0/I/1).

---

## 2. Серверная часть (Google Cloud, отдельный репозиторий/сервис)

Стек: Python (FastAPI предпочтительнее Flask здесь — async, авто-докс, но Flask
тоже приемлем если хочешь единообразие со стилем проекта), PostgreSQL
(Cloud SQL) или на первое время SQLite для MVP, деплой на Cloud Run.

### 2.1. Схема БД
```
licenses
  id                  uuid pk
  license_key         text unique
  stripe_customer_id  text
  stripe_subscription_id text nullable
  plan                text  -- 'monthly' | 'quarterly' | 'yearly'
  status              text  -- 'active' | 'past_due' | 'canceled' | 'expired'
  current_period_end  timestamptz
  max_devices         int default 2
  created_at          timestamptz
  updated_at          timestamptz

devices
  id                  uuid pk
  license_id          fk -> licenses.id
  fingerprint_hash    text
  device_label        text nullable  -- напр. "DESKTOP-ABC123"
  first_seen          timestamptz
  last_seen           timestamptz
  deactivated_at      timestamptz nullable

  unique(license_id, fingerprint_hash) where deactivated_at is null
```

### 2.2. Эндпоинты
- `POST /api/license/activate`
  Body: `{license_key, fingerprint_hash, device_label, app_version}`
  Логика: найти лицензию → проверить `status == active` и `current_period_end > now` →
  посчитать активные устройства (`deactivated_at is null`) → если fingerprint уже
  среди них — просто обновить `last_seen` и выдать токен; если новое устройство и
  лимит не исчерпан — зарегистрировать и выдать токен; иначе `409 DEVICE_LIMIT_REACHED`.
  Response: `{token: "<base64 payload>.<base64 signature>", plan, current_period_end}`

- `POST /api/license/refresh`
  Body: `{token}` (текущий, для идентификации device+license), `fingerprint_hash`
  Логика: провалидировать текущий токен → найти лицензию/устройство → выдать новый
  токен с актуальным `status`/`current_period_end` (это и есть механизм отзыва —
  если подписка отменена, новый токен придёт с `status: canceled` и клиент это
  обработает).

- `POST /api/license/deactivate`
  Body: `{token}`
  Логика: пометить `devices.deactivated_at = now()`, освобождая слот.

- `POST /api/webhooks/stripe`
  Верификация подписи Stripe (`Stripe-Signature` header), обработка событий
  подписки, апдейт `licenses`.

- `GET /api/license/status?key=...` (опционально, для сайта личного кабинета)

### 2.3. Формат токена
Не используй готовый JWT-стек без необходимости — формат простой и явный:
```
payload = json.dumps({
  "license_key": ..., "device_id": ..., "plan": ...,
  "status": ..., "current_period_end": <unix_ts>, "issued_at": <unix_ts>
}, sort_keys=True).encode()

signature = ed25519_private_key.sign(payload)
token = base64url(payload) + "." + base64url(signature)
```
Клиент проверяет `ed25519_public_key.verify(signature, payload)` — если не совпало,
токен считается недействительным и удаляется.

### 2.4. Секреты
Приватный Ed25519-ключ и Stripe webhook secret — только в Secret Manager Google
Cloud, никогда не в коде/репозитории. Публичный Ed25519-ключ — константа в
клиентском коде (можно хранить в `configs/license_public_key.pem` внутри
дистрибутива, это не секрет).

---

## 3. Клиентская часть (внутри текущего репозитория Signer PRIME)

### 3.1. Новые файлы
```
licensing/
  __init__.py
  license_manager.py      # основная логика: активация, refresh, проверка токена
  device_fingerprint.py   # сбор и хэширование fingerprint
  license_client.py       # HTTP-клиент к серверу лицензий (requests, свой домен из конфига)
  public_key.py           # захардкоженный Ed25519 public key + verify()
ui/widgets/license_dialog.py   # диалог ввода ключа (по образцу ui/widgets/update_dialog.py)
ui/widgets/license_status_page.py  # опционально: страница "Моя лицензия" в Settings
```

### 3.2. `device_fingerprint.py`
Собери и захэшируй (SHA-256, вернуть hex-строку):
- Серийный номер системного диска (`wmic diskdrive get serialnumber` на Windows,
  через `subprocess`, с fallback если недоступно).
- MAC первого физического адаптера (`uuid.getnode()` как fallback, либо `wmic nic`).
- Строка процессора (`platform.processor()`).

Объединить через `|`, посчитать `hashlib.sha256(...).hexdigest()`. Один провал
источника не должен ронять всю функцию — собирай что можешь, если совсем ничего не
собралось — используй `uuid.getnode()` как последний fallback и залогируй warning.

### 3.3. `license_manager.py` — публичный API модуля
```python
class LicenseStatus(Enum):
    VALID = "valid"
    EXPIRED = "expired"
    REVOKED = "revoked"
    NOT_ACTIVATED = "not_activated"
    GRACE_PERIOD = "grace_period"     # токен просрочен по refresh, но ещё в grace-окне

class LicenseManager:
    def check_local_status(self) -> LicenseStatus: ...
    def activate(self, license_key: str) -> tuple[bool, str]: ...   # (успех, сообщение об ошибке)
    def refresh_async(self, on_done: Callable[[bool], None]) -> None: ...  # в QThread, не блокировать UI
    def deactivate_this_device(self) -> tuple[bool, str]: ...
    def get_plan_info(self) -> Optional[dict]: ...  # для UI: план, дата окончания
```
Требования к реализации:
- Все сетевые вызовы — через `QThread`-воркер (по образцу `UpdateCheckWorker` в
  `ui/widgets/update_worker.py`), никогда не блокируй GUI-поток `requests`-вызовом.
  Тайм-аут запроса — 8 секунд.
- Хранение токена — файл `Path(os.environ["LOCALAPPDATA"]) / "Signer" / "license.token"`,
  права на чтение только текущему пользователю где возможно.
- Логика grace period и отката часов — как описано в п. 1.1/1.2, вынеси константы
  `REFRESH_INTERVAL_DAYS`, `GRACE_PERIOD_DAYS` в `configs/settings.py` рядом с
  остальными настройками (по аналогии с `auto_check_updates`).

### 3.4. `license_dialog.py`
Возьми за образец `ui/widgets/update_dialog.py` (стиль, тема, `BtnPrimary`/`BtnSecondary`).
Два состояния:
1. **Ввод ключа** — поле ввода (маска `XXXX-XXXX-XXXX-XXXX`), кнопка "Активировать",
   ссылка "Купить подписку" (открывает сайт в браузере), статус-лейбл с ошибками
   сервера (`DEVICE_LIMIT_REACHED` → показать понятный текст "Лимит устройств
   исчерпан. Деактивируйте одно из устройств в личном кабинете или напишите в
   поддержку").
2. **Успех/статус** — план, дата окончания, кнопка "Деактивировать это устройство".

Диалог должен быть **модальным и блокирующим запуск MainWindow**, если статус не
`VALID`/`GRACE_PERIOD`.

### 3.5. Интеграция в `main.py`
В `main()`, ДО `window = MainWindow()`:
```python
from licensing.license_manager import LicenseManager, LicenseStatus

license_manager = LicenseManager()
status = license_manager.check_local_status()

if status not in (LicenseStatus.VALID, LicenseStatus.GRACE_PERIOD):
    from ui.widgets.license_dialog import LicenseDialog
    dialog = LicenseDialog(license_manager)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)   # пользователь закрыл диалог, не активировав — выходим

# Дальше можно неблокирующе запустить фоновый refresh:
license_manager.refresh_async(on_done=lambda ok: logger.info(f"License refresh: {ok}"))

window = MainWindow()
window.show()
```
Не убирай существующую логику проверки обновлений ниже — просто вставь блок лицензии
раньше неё.

### 3.6. Settings
Добавь в `configs/settings.py` (`AppSettings`) поля:
```python
license_refresh_interval_days: int = 3
license_grace_period_days: int = 10
license_server_url: str = "https://license.<ваш-домен>.com"
```
Не переиспользуй `update_channel`/другие несвязанные поля.

---

## 4. Тестирование и критерии приёмки

1. Юнит-тесты (`tests/test_licensing.py`, без сети — мокай `license_client`):
   - Валидный токен с будущей `current_period_end` → `LicenseStatus.VALID`.
   - Токен с `current_period_end` в прошлом → `LicenseStatus.EXPIRED`.
   - Подпись токена подделана (изменён один байт payload) → верификация проваливается.
   - Отсутствие файла токена → `LicenseStatus.NOT_ACTIVATED`.
   - Токен просрочен для refresh, но внутри grace period → `LicenseStatus.GRACE_PERIOD`.
   - Токен вне grace period → требует активную сеть/повторный ввод ключа.
2. Ручная проверка: полное отключение интернета не должно ронять уже активированное
   приложение (пока не истёк grace period) и не должно вызывать исключений в
   `_process_loop`/детекции/карте — эти части кода вообще не должны знать о
   существовании лицензирования.
3. `server/map_server.py` и весь `processing/*` — без единого изменения после
   выполнения задачи (проверь `git diff` перед сдачей).

---

## 5. Порядок работы (рекомендуемый)

1. Сначала клиентская часть с мок-сервером (`license_client.py` за флагом
   `LICENSE_MOCK_MODE` возвращает фиктивный валидный токен) — чтобы UI и
   офлайн-логику можно было протестировать без готового бэкенда.
2. Затем серверная часть (FastAPI + SQLite для MVP, без Stripe пока — ключи
   создаются вручную через админ-эндпоинт/скрипт).
3. Подключение реального `license_server_url`, снятие мок-режима.
4. Интеграция Stripe webhooks — в последнюю очередь, когда остальное обкатано.

Не начинай с деплоя на Google Cloud — сначала добейся, что весь флоу активации/
refresh/grace period работает локально (сервер лицензий можно поднять на
`localhost:8000` для разработки — это ДРУГОЙ localhost-сервис, не путай с
`map_server.py` на порту 3000).
