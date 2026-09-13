# Быстрый старт - Система лицензирования

## Для разработчиков (без сервера)

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

### 2. Запуск локального сервера лицензий

```bash
cd signer-license-server
bash scripts/local_dev_up.sh
```

Это поднимет локальный сервер на `http://localhost:8000` с PostgreSQL и Adminer.

### 3. Создание тестовой лицензии

```bash
cd signer-license-server
python scripts/create_license_manual.py
```

Скопируйте сгенерированный ключ (формат `SGNR-XXXX-XXXX-XXXX-XXXX`).

### 4. Тестирование

```bash
# В отдельном терминале, из корня Signer_PRIME:
export SIGNER_LICENSE_SERVER_URL=http://localhost:8000
python main.py
```

При первом запуске появится диалог активации. Введите ключ из шага 3.

**Для юнит-тестов:**
```bash
python -m unittest tests.test_licensing
```

## Для продакшна

### 1. Развернуть сервер лицензий

См. полную документацию: `docs/LICENSE_SERVER.md`

### 2. Сгенерировать ключи Ed25519

```bash
python scripts/generate_ed25519_keys.py
```

- Приватный ключ → Secret Manager на сервере
- Публичный ключ → `licensing/public_key.py` в клиенте

### 3. Обновить настройки клиента

В `configs/settings.py`:

```python
license_server_url: str = "https://your-license-server.run.app"
```

### 4. Протестировать
```

### 4. Протестировать

```bash
python main.py
```

## Структура файлов

```
licensing/
├── __init__.py              # Публичный API
├── license_manager.py       # Основная логика
├── license_client.py        # HTTP клиент
├── device_fingerprint.py    # Hardware fingerprint
└── public_key.py            # Ed25519 верификация

ui/widgets/
└── license_dialog.py        # UI диалог активации

tests/
└── test_licensing.py        # Юнит-тесты

docs/
├── LICENSING.md             # Клиентская документация
└── LICENSE_SERVER.md        # Серверная документация

scripts/
└── generate_ed25519_keys.py # Генератор ключей

examples/
└── example_licensing_mock.py # Пример использования
```

## FAQ

**Q: Как сбросить лицензию?**  
A: Удалите файл `%LOCALAPPDATA%\Signer\license.token`

**Q: Где хранится токен?**  
A: Windows: `C:\Users\<username>\AppData\Local\Signer\license.token`

**Q: Приложение не запускается после добавления лицензирования**  
A: Включите мок-режим или развёрните сервер лицензий

**Q: Как работает grace period?**  
A: Приложение работает без онлайн-проверки 10 дней. После этого требуется интернет.

## Документация

- **Клиент:** `docs/LICENSING.md`
- **Сервер:** `docs/LICENSE_SERVER.md`
- **Промпт:** `prompts/PROMPT_LICENSING_SYSTEM.md`
- **Чеклист:** `CHECKLIST.md`
