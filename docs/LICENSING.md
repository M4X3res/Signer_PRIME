# Система лицензирования Signer PRIME

## Обзор

Система подписок (месяц / 3 месяца / год) с онлайн-активацией и обязательной проверкой при каждом запуске.

**ВАЖНО (обновлено):** Приложение требует активного подключения к серверу лицензий при каждом запуске. Офлайн-работа на протяжении нескольких дней больше не поддерживается.

- **Клиентская часть:** интегрирована в основной проект (модуль `licensing/`)
- **Серверная часть:** отдельный сервис (см. `docs/LICENSE_SERVER.md`)

## Архитектура

```
┌─────────────────────┐
│  Signer PRIME       │
│  (PyQt6 Desktop)    │
│                     │
│  licensing/         │
│  ├─ license_manager │  ◄── Проверка токена (локально + онлайн)
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
license_startup_retry_timeout_sec: int = 30  # Таймаут на повторные попытки подключения при старте
license_server_url: str = "https://signer-license-server-1047715133540.europe-west1.run.app"
```

### Статусы лицензии

- **VALID** - токен валиден, подписка активна (проверено с сервером)
- **EXPIRED** - подписка истекла
- **REVOKED** - лицензия отозвана
- **NOT_ACTIVATED** - токен отсутствует (первый запуск)
- **NETWORK_ERROR** - ошибка подключения к серверу (блокирует запуск)

### Логика при запуске (main.py)

1. **Обязательная онлайн-проверка** с сервером (`verify_access_async`)
2. Если токена нет → диалог активации
3. Если токен локально валиден → **обращение к серверу для подтверждения**
4. Если сервер недоступен → **блокировка запуска** с предложением повторить попытку
5. Только после успешного подтверждения сервером → запуск приложения

### Runtime мониторинг

После запуска приложение периодически (каждые 6 часов) проверяет лицензию в фоне. Если подписка истекла/отозвана во время работы:
- **Grace period:** 3 дня без онлайн-проверки (сокращено для безопасности)
- Если активна обработка видео → дожидается сохранения результатов (до 5 минут)
- Затем показывает критический диалог и закрывает приложение

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
- **Grace period:** 3 дня без онлайн-проверки (сокращено для безопасности)
- **Refresh interval:** 1 день (сокращено для безопасности)
- **Runtime monitoring:** проверка каждые 6 часов работы приложения
- **Защита от отката часов:** форсированная онлайн-проверка

## Runtime Monitoring

Начиная с усиления защиты (Задача 2), приложение проверяет статус лицензии не только при запуске, но и периодически во время работы:

- **Интервал проверки:** каждые 6 часов работы приложения
- **Что проверяется:** обновление токена (refresh) и локальная верификация
- **При обнаружении REVOKED/EXPIRED:**
  - Если идёт обработка видео → даёт завершить и сохранить результаты
  - После завершения → показывает критический диалог и закрывает приложение
  - Если обработки нет → немедленно показывает диалог и закрывается

Это гарантирует, что отзыв лицензии на сервере будет обнаружен максимум через 6 часов (плюс grace period), даже если пользователь не перезапускал приложение.

## Разработка

### Тестирование клиентской части

```bash
# Юнит-тесты (без сети)
pytest tests/test_licensing.py -v

# Локальный dev-сервер (вместо продакшн-сервера)
cd signer-license-server
bash scripts/local_dev_up.sh

# В отдельном терминале, из корня проекта:
export SIGNER_LICENSE_SERVER_URL=http://localhost:8000
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
cd signer-license-server
bash scripts/local_dev_up.sh
# Сервер запустится на http://localhost:8000
```

### 2. Установить URL через переменную окружения

```bash
export SIGNER_LICENSE_SERVER_URL=http://localhost:8000
```

Или обновить в настройках:
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

### Ошибка "Не удалось подключиться к серверу лицензий"

- Проверьте интернет-соединение
- Убедитесь, что `license_server_url` корректен в `configs/settings.py`
- Проверьте, что сервер доступен (откройте URL в браузере)
- Временно отключите антивирус/файрвол для проверки

## FAQ

**Q: Как сбросить лицензию для тестирования?**  
A: Удалите файл `%LOCALAPPDATA%\Signer\license.token`

**Q: Где хранится токен?**  
A: `%LOCALAPPDATA%\Signer\license.token` (Windows)

**Q: Можно ли работать без интернета?**  
A: Нет. Приложение требует подключение к серверу лицензий при каждом запуске. Во время самой обработки видео кратковременные обрывы сети не прерывают работу.

**Q: Что делать при длительном отсутствии интернета?**  
A: Приложение не запустится без подключения к серверу. Необходимо обеспечить доступ в интернет для проверки лицензии.

**Q: Можно ли работать без лицензии (для разработки)?**  
A: Запустите локальный dev-сервер из `signer-license-server/` через `bash scripts/local_dev_up.sh` и установите `export SIGNER_LICENSE_SERVER_URL=http://localhost:8000`

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
