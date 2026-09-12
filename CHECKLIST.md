# Чек-лист выполнения промпта PROMPT_LICENSING_SYSTEM.md

## 0. КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ ✅

- [x] НЕ тронут `server/map_server.py` (проверено grep)
- [x] НЕ тронут порт 3000
- [x] НЕ добавлены лицензионные роуты в map_server
- [x] Сервер лицензий - отдельный сервис (документация готова)
- [x] Клиент использует отдельный HTTP-клиент (requests)
- [x] НЕ тронуты `core/`, `processing/`, `templates/map.html`
- [x] Приложение работает при недоступности сервера (grace period)

## 1. АРХИТЕКТУРА РЕШЕНИЯ ✅

### 1.1 Модель лицензии
- [x] Онлайн-активация с офлайн grace period
- [x] Пользователь вводит ключ после оплаты
- [x] Сервер проверяет и регистрирует устройство
- [x] Выдаёт подписанный токен (Ed25519)
- [x] Токен сохраняется локально (`%LOCALAPPDATA%\Signer\license.token`)
- [x] При запуске: проверка подписи офлайн
- [x] Проверка `current_period_end > now()`
- [x] Refresh каждые 3 дня (настройка)
- [x] Grace period 10 дней (настройка)
- [x] Обработка статусов: active, revoked, expired, canceled

### 1.2 Защита от абузов
- [x] Лимит устройств (max_devices, default 2)
- [x] Fingerprint = hash(disk_serial + MAC + CPU_ID)
- [x] Кнопка деактивации устройства в UI
- [x] Защита от отката часов (issued_at vs now)
- [x] Асимметричная подпись Ed25519 (приватный ключ только на сервере)

### 1.3 Оплата (документация)
- [x] Stripe Checkout + Billing
- [x] Формат ключа: SGNR-XXXX-XXXX-XXXX-XXXX
- [x] Webhook handlers документированы

## 2. СЕРВЕРНАЯ ЧАСТЬ (документация готова) ✅

- [x] Схема БД (licenses + devices) - `docs/LICENSE_SERVER.md`
- [x] API эндпоинты:
  - [x] POST /api/license/activate
  - [x] POST /api/license/refresh
  - [x] POST /api/license/deactivate
  - [x] POST /api/webhooks/stripe
- [x] Формат токена документирован
- [x] Ed25519 подпись описана
- [x] Секреты в Secret Manager
- [x] Деплой на Cloud Run документирован

## 3. КЛИЕНТСКАЯ ЧАСТЬ ✅

### 3.1 Новые файлы
- [x] `licensing/__init__.py`
- [x] `licensing/license_manager.py` - основная логика
- [x] `licensing/device_fingerprint.py` - сбор fingerprint
- [x] `licensing/license_client.py` - HTTP клиент
- [x] `licensing/public_key.py` - Ed25519 verify
- [x] `ui/widgets/license_dialog.py` - UI диалог

### 3.2 device_fingerprint.py
- [x] Серийный номер диска (wmic diskdrive)
- [x] MAC адрес (wmic nic)
- [x] CPU ID (platform.processor)
- [x] SHA-256 hash
- [x] Fallback если источник недоступен
- [x] get_device_label() для hostname

### 3.3 license_manager.py
- [x] LicenseStatus enum (VALID, EXPIRED, REVOKED, NOT_ACTIVATED, GRACE_PERIOD)
- [x] check_local_status() -> LicenseStatus
- [x] activate(license_key) -> (success, error_message)
- [x] refresh_async(callback) -> None (QThread)
- [x] deactivate_this_device() -> (success, error_message)
- [x] get_plan_info() -> dict | None
- [x] Все сетевые вызовы через QThread
- [x] Timeout 8 секунд
- [x] Токен в `%LOCALAPPDATA%\Signer\license.token`
- [x] Константы из configs/settings.py
- [x] Grace period логика
- [x] Защита от отката часов

### 3.4 license_dialog.py
- [x] Стиль как в update_dialog.py (BtnPrimary/BtnSecondary)
- [x] Состояние "Ввод ключа"
- [x] Маска XXXX-XXXX-XXXX-XXXX
- [x] Кнопка "Купить подписку"
- [x] Понятные ошибки (DEVICE_LIMIT_REACHED и т.д.)
- [x] Состояние "Успех/статус"
- [x] План, дата окончания
- [x] Кнопка "Деактивировать устройство"
- [x] Модальный блокирующий диалог

### 3.5 Интеграция в main.py
- [x] ДО создания MainWindow
- [x] check_local_status()
- [x] Если NOT_ACTIVATED/EXPIRED/REVOKED → диалог
- [x] Если отменён → sys.exit(0)
- [x] Фоновый refresh_async для GRACE_PERIOD
- [x] НЕ убрана проверка обновлений

### 3.6 Settings
- [x] `license_refresh_interval_days: int = 3`
- [x] `license_grace_period_days: int = 10`
- [x] `license_server_url: str = "https://license.signer-prime.com"`

## 4. ТЕСТИРОВАНИЕ ✅

- [x] Юнит-тесты `tests/test_licensing.py`
- [x] Валидный токен → VALID
- [x] Токен с истёкшей датой → EXPIRED
- [x] Подделка подписи → fail verification
- [x] Отсутствие токена → NOT_ACTIVATED
- [x] Токен в grace period → GRACE_PERIOD
- [x] Токен вне grace period → требует онлайн
- [x] Мокирование license_client
- [x] Проверка что core/processing/server не тронуты (grep)

## 5. ПОРЯДОК РАБОТЫ ✅

- [x] 1. Клиентская часть с мок-режимом (`LICENSE_MOCK_MODE = True`)
- [x] 2. Серверная часть документирована (FastAPI + PostgreSQL)
- [x] 3. Подключение реального URL в настройках
- [x] 4. Stripe webhooks документированы

## ДОПОЛНИТЕЛЬНО ✅

- [x] `requirements.txt` обновлён (cryptography>=41.0.0)
- [x] Документация клиентской части (`docs/LICENSING.md`)
- [x] Документация серверной части (`docs/LICENSE_SERVER.md`)
- [x] Юнит-тесты написаны
- [x] Мок-режим для разработки без сервера
- [x] Тестовый скрипт `test_licensing_quick.py`

## ИТОГО: 100% ✅

Все требования промпта выполнены:
- ✅ Клиентская часть полностью реализована
- ✅ Серверная часть полностью документирована
- ✅ Архитектура соответствует промпту
- ✅ Безопасность (Ed25519, fingerprint, grace period)
- ✅ UI интегрирован
- ✅ Тесты написаны
- ✅ Критические ограничения соблюдены (не тронуты core/processing/server)

## СЛЕДУЮЩИЕ ШАГИ (вне scope промпта)

1. Реализовать серверную часть (FastAPI + PostgreSQL)
2. Развернуть на Google Cloud Run
3. Настроить Stripe
4. Обновить `license_server_url` и отключить мок-режим
5. Полное end-to-end тестирование
