# Быстрый старт License Server

## Минимальный MVP сервер для тестирования клиента

Этот сервер использует mock-данные в памяти и подходит ТОЛЬКО для разработки/тестирования клиента.

### 1. Установка зависимостей

```bash
cd signer-license-server
pip install fastapi uvicorn[standard]
```

### 2. Запуск сервера

```bash
# Из папки signer-license-server
uvicorn app.main:app --reload --port 8000
```

Или напрямую:

```bash
python app/main.py
```

Сервер запустится на `http://localhost:8000`

### 3. Проверка работы

Откройте в браузере:
- API Docs: http://localhost:8000/docs
- Health: http://localhost:8000/health

### 4. Интеграция с клиентом

#### В клиенте Signer PRIME обновите `configs/settings.py`:

```python
license_server_url: str = "http://localhost:8000"
```

#### Отключите мок-режим в `licensing/license_client.py`:

```python
LICENSE_MOCK_MODE = False
```

### 5. Тестирование

1. Запустите клиент: `python main.py`
2. Появится диалог активации
3. Введите любой ключ в формате `SGNR-TEST-LOCAL-SERV-MVP1`
4. Нажмите "Активировать"
5. Сервер автоматически создаст mock-лицензию и выдаст токен
6. Клиент запустится!

### Особенности MVP сервера

✅ **Работает:**
- Активация лицензии
- Обновление токена (refresh)
- Деактивация устройства
- Лимит устройств (2 по умолчанию)
- Переактивация того же устройства

⚠️ **НЕ реализовано (для продакшна):**
- Настоящие Ed25519 подписи (используется mock-подпись)
- База данных (данные в памяти, теряются при рестарте)
- Secret Manager
- Cloud SQL
- Stripe интеграция
- Rate limiting
- Серьёзная валидация

### Для продакшна

Реализуйте полный стек согласно `prompts/PROMPT_LICENSE_SERVER_CLOUD_RUN.md`:

1. PostgreSQL + SQLAlchemy + Alembic
2. Настоящие Ed25519 ключи
3. Cloud SQL + Secret Manager
4. Cloud Run деплой
5. Stripe webhooks
6. Тесты (pytest)
7. Rate limiting
8. Логирование и мониторинг

Или наймите backend-разработчика (оценка: $500-1500, 30-40 часов работы).

## Troubleshooting

### Ошибка "ModuleNotFoundError: No module named 'fastapi'"

```bash
pip install fastapi uvicorn[standard]
```

### Порт 8000 занят

Измените порт:
```bash
uvicorn app.main:app --port 8001
```

И обновите в клиенте:
```python
license_server_url: str = "http://localhost:8001"
```

### Клиент не подключается

Проверьте:
1. Сервер запущен: http://localhost:8000/health
2. В клиенте `LICENSE_MOCK_MODE = False`
3. URL правильный: `license_server_url = "http://localhost:8000"`

### Токен не валидируется

⚠️ **Важно:** MVP сервер использует mock-подписи!

Клиент попытается верифицировать токен своим публичным ключом и ПРОВАЛИТ проверку.

**Решение:** В `licensing/license_manager.py` временно закомментируйте строгую проверку подписи в методе `check_local_status()` для тестирования MVP сервера:

```python
# Временно для тестирования с MVP сервером
valid, payload, error = verify_token(token_str)
# if not valid:
#     logger.warning(f"[LicenseManager] Token signature invalid: {error}")
#     self._delete_token()
#     return LicenseStatus.NOT_ACTIVATED
# Просто парсим payload без проверки подписи
if not valid:
    logger.warning(f"[LicenseManager] MVP mode: skipping signature check")
    # Попробуем распарсить payload напрямую
    import base64, json
    try:
        payload_b64 = token_str.split(".")[0]
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += '=' * padding
        payload_json = base64.urlsafe_b64decode(payload_b64.replace('-', '+').replace('_', '/')).decode()
        payload = json.loads(payload_json)
    except:
        self._delete_token()
        return LicenseStatus.NOT_ACTIVATED
```

**Для продакшна верните строгую проверку обратно!**

## Статус

✅ MVP сервер готов к использованию для тестирования клиента  
⚠️ НЕ для продакшна  
🚧 Требуется полная реализация для production use
