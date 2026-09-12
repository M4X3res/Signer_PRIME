# Система лицензирования Signer PRIME

## Обзор

Система подписок (месяц / 3 месяца / год) с онлайн-активацией и офлайн grace period.

- **Клиентская часть:** интегрирована в основной проект (модуль `licensing/`)
- **Серверная часть:** отдельный сервис (см. `docs/LICENSE_SERVER.md`)

## Архитектура

```
┌─────────────────────┐
│  Signer PRIME       │
│  (PyQt6 Desktop)    │
│                     │
│  licensing/         │
│  ├─ license_manager │  ◄── Проверка токена офлайн (Ed25519)
│  ├─ license_client  │  ◄── HTTP клиент к серверу
│  ├─ device_fingerprint
│  └─ public_key      │
└──────────┬──────────┘
           │ HTTPS
           │ (activate/refresh/deactivate)
           ▼
┌─────────────────────┐
│  License Server     │
│  (Google Cloud Run) │
│                     │
│  FastAPI + PostgreSQL
│  + Ed25519 signing  │
│  + Stripe webhooks  │
└─────────────────────┘
```

## Клиентская часть (уже интегрирована)

### Модули

- **`licensing/license_manager.py`** - основной менеджер лицензий
- **`licensing/license_client.py`** - HTTP клиент к серверу
- **`licensing/device_fingerprint.py`** - сбор hardware fingerprint
- **`licensing/public_key.py`** - верификация токенов (Ed25519)
- **`ui/widgets/license_dialog.py`** - UI для активации

### Настройки (configs/settings.py)

```python
license_refresh_interval_days: int = 3   # Интервал обновления токена
license_grace_period_days: int = 10      # Офлайн grace period
license_server_url: str = "https://license.signer-prime.com"
```

### Статусы лицензии

- **VALID** - токен валиден, подписка активна
- **EXPIRED** - подписка истекла
- **REVOKED** - лицензия отозвана
- **NOT_ACTIVATED** - токен отсутствует (первый запуск)
- **GRACE_PERIOD** - токен просрочен для refresh, но в grace period

### Логика при запуске (main.py)

1. Проверка локального токена (офлайн, Ed25519 подпись)
2. Если статус NOT_ACTIVATED / EXPIRED / REVOKED → показать диалог активации
3. Если статус GRACE_PERIOD → запустить фоновое обновление токена
4. Если статус VALID → запуск приложения

## Серверная часть

**Полная документация:** `docs/LICENSE_SERVER.md`

### Стек

- FastAPI (Python)
- PostgreSQL (Cloud SQL)
- Google Cloud Run
- Stripe (оплата)
- Ed25519 (подпись токенов)

### Основные эндпоинты

- `POST /api/license/activate` - активация лицензии
- `POST /api/license/refresh` - обновление токена
- `POST /api/license/deactivate` - деактивация устройства
- `POST /api/webhooks/stripe` - обработка вебхуков Stripe

### Схема БД

```sql
licenses (id, license_key, stripe_subscription_id, plan, status, current_period_end, max_devices)
devices (id, license_id, fingerprint_hash, device_label, first_seen, last_seen, deactivated_at)
```

## Безопасность

### Ed25519 подпись токенов

- **Приватный ключ:** только на сервере (Secret Manager)
- **Публичный ключ:** в клиенте (`licensing/public_key.py`)
- Реверс-инжиниринг клиента НЕ позволяет подделать токен

### Fingerprint устройства

Комбинация (SHA-256):
- Серийный номер системного диска
- MAC-адрес физического сетевого адаптера
- CPU ID

### Защита от абузов

- **Лимит устройств:** по умолчанию 2 на лицензию
- **Деактивация:** пользователь может освободить слот
- **Grace period:** 10 дней без онлайн-проверки
- **Защита от отката часов:** форсированная онлайн-проверка

## Разработка

### Тестирование клиентской части

```bash
# Юнит-тесты (без сети)
pytest tests/test_licensing.py -v

# Мок-режим (без сервера)
# В licensing/license_client.py установить LICENSE_MOCK_MODE = True
python main.py
```

### Тестирование UI диалога

```bash
python -m ui.widgets.license_dialog
```

### Тестирование fingerprint

```bash
python -m licensing.device_fingerprint
```

### Генерация ключей Ed25519

```bash
python -m licensing.public_key
```

## Тестирование полного флоу

### 1. Локальный сервер (разработка)

```bash
# В отдельном терминале запустить локальный сервер лицензий
cd license-server
uvicorn main:app --reload --port 8000
```

### 2. Обновить URL в настройках

```python
# configs/settings.py
license_server_url: str = "http://localhost:8000"
```

### 3. Запустить клиент

```bash
python main.py
```

## Troubleshooting

### Ошибка "requests library not installed"

```bash
pip install requests
```

### Ошибка "cryptography library not installed"

```bash
pip install cryptography>=41.0.0
```

### Диалог лицензии не показывается

Проверьте статус:
```python
from licensing.license_manager import LicenseManager
manager = LicenseManager()
print(manager.check_local_status())
```

### Токен считается невалидным

- Проверьте публичный ключ в `licensing/public_key.py`
- Убедитесь, что токен подписан соответствующим приватным ключом
- Проверьте формат токена: `base64url(payload).base64url(signature)`

### Grace period постоянно активен

- Сервер лицензий недоступен
- Проверьте `license_server_url` в настройках
- Проверьте интернет-соединение

## FAQ

**Q: Как сбросить лицензию для тестирования?**  
A: Удалите файл `%LOCALAPPDATA%\Signer\license.token`

**Q: Где хранится токен?**  
A: `%LOCALAPPDATA%\Signer\license.token` (Windows)

**Q: Как изменить grace period?**  
A: В `configs/settings.py` измените `license_grace_period_days`

**Q: Можно ли работать без лицензии (для разработки)?**  
A: Установите `LICENSE_MOCK_MODE = True` в `licensing/license_client.py`

**Q: Как добавить страницу "Моя лицензия" в Settings?**  
A: Создайте `ui/widgets/license_status_page.py` и добавьте в `settings_page.py`

## Roadmap

- [ ] Серверная часть (FastAPI + PostgreSQL)
- [ ] Интеграция Stripe
- [ ] Деплой на Google Cloud Run
- [ ] Страница "Моя лицензия" в Settings
- [ ] Личный кабинет на сайте
- [ ] Email уведомления об истечении подписки
- [ ] Статистика использования (для админа)

## Документация

- **Серверная часть:** `docs/LICENSE_SERVER.md`
- **Архитектура:** см. промпт `prompts/PROMPT_LICENSING_SYSTEM.md`
- **API Reference:** `docs/LICENSE_SERVER.md#api-endpoints`

## Контакты

- **Issues:** GitHub Issues
- **Support:** support@signer-prime.com
