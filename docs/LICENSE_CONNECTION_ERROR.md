# Решение проблемы "Не удалось подключиться к серверу лицензий"

## Проблема

При запуске `main.py` появляется ошибка:
```
Не удалось подключиться к серверу лицензий.
Проверьте интернет-соединение.
Ошибка: UNKNOWN: Unknown error
Попробовать снова?
```

## Причина

Это **нормальное поведение** после выполнения ЗАДАЧИ 2 из `PROMPT_FOR_AI_AGENT_RELEASE_PREP.md`. 

Система лицензирования настроена на **строгую онлайн-проверку** при каждом запуске и **блокирует** запуск приложения если сервер недоступен.

Ошибка `UNKNOWN: Unknown error` означает что:
1. Сервер лицензий не запущен/не развёрнут
2. URL в `build_config.json` неправильный
3. Нет интернет-соединения
4. Или другая непредвиденная ошибка (например, requests не установлен)

## Решение 1: Запустить локальный dev-сервер

Для разработки/тестирования клиента запустите локальный сервер лицензий:

### Шаг 1: Запустить сервер

```bash
cd signer-license-server

# Создать venv если ещё не создан
python -m venv venv

# Активировать venv
venv\Scripts\activate  # Windows
# или
source venv/bin/activate  # Linux/Mac

# Установить зависимости
pip install -r requirements.txt

# Запустить сервер
uvicorn app.main:app --reload --port 8000
```

Сервер запустится на `http://localhost:8000`

### Шаг 2: Изменить build_config.json

```json
{
  "license_server_url": "http://localhost:8000"
}
```

### Шаг 3: Запустить клиент

```bash
python main.py
```

## Решение 2: Проверить production сервер

Если вы используете production сервер на Google Cloud Run:

### Шаг 1: Проверить что сервис запущен

```bash
# Проверить доступность
curl -I https://signer-license-server-1047715133540.europe-west1.run.app

# Должен вернуть HTTP 200 или 404 (но не connection refused)
```

### Шаг 2: Проверить логи

```bash
# В Google Cloud Console
gcloud logging read "resource.type=cloud_run_revision" --limit 50 --format json
```

### Шаг 3: Проверить URL в build_config.json

```json
{
  "license_server_url": "https://signer-license-server-1047715133540.europe-west1.run.app"
}
```

**Убедитесь что:**
- URL корректный (без лишних слэшей)
- Сервер реально развёрнут на этом URL
- У вас есть интернет-соединение

## Решение 3: Создать тестовую лицензию

Если локальный сервер запущен, создайте тестовую лицензию:

```bash
cd signer-license-server
python scripts/create_license_manual.py \
    --email test@example.com \
    --plan monthly \
    --stripe-customer test_cus_123
```

Сохраните выведенный лицензионный ключ (формат: `SGNR-XXXX-XXXX-XXXX-XXXX`).

Затем в клиенте введите этот ключ при активации.

## Решение 4: Проверить requests установлен

```bash
pip show requests
```

Если не установлен:

```bash
pip install requests
```

## Отключение лицензирования (НЕ рекомендуется)

⚠️ **ВНИМАНИЕ:** Это обход системы защиты, использовать ТОЛЬКО для разработки UI!

Если нужно временно обойти лицензирование для тестирования других компонентов:

1. Закомментировать весь блок проверки лицензии в `main.py` (строки ~200-340)
2. Установить `license_manager = None`
3. Проверить что код дальше обрабатывает `license_manager is None`

**НЕ КОММИТИТЬ** эти изменения!

## Что дальше?

После решения проблемы подключения, система лицензирования будет работать по правилам ЗАДАЧИ 2:

- ✅ Обязательная онлайн-проверка при каждом запуске
- ✅ `NETWORK_ERROR` блокирует запуск (с возможностью повтора)
- ✅ Нет офлайн grace period
- ✅ Runtime checks каждые 6 часов (мягкий режим - не рвёт активную обработку)

## Дополнительная информация

- **Документация сервера:** `signer-license-server/README.md`
- **Документация клиента:** `docs/LICENSING.md`
- **Быстрый старт:** `docs/QUICKSTART_LICENSING.md`
- **Чек-лист релиза:** `docs/RELEASE_CHECKLIST.md`
