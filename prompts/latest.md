# Задача: исправить TypeError при сравнении datetime в license_service.py

## Проблема

Сервер `signer-license-server` падает с ошибкой 500 при любом вызове
`POST /api/license/activate` (и потенциально при `/api/license/refresh`).

Полный traceback из логов Cloud Run:

File "/app/app/services/license_service.py", line 67, in activate_license
if license.current_period_end < now:
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
TypeError: can't compare offset-naive and offset-aware datetimes


## Причина

В `signer-license-server/app/models.py` поле `current_period_end` объявлено как:

```python
current_period_end: Mapped[datetime] = mapped_column(
    DateTime(timezone=True),
    nullable=False
)
```

То есть в базе (PostgreSQL) это **timezone-aware** значение.

Но в `signer-license-server/app/services/license_service.py` для сравнения
используется:

```python
now = datetime.utcnow()
```

`datetime.utcnow()` возвращает **naive** datetime (без информации о таймзоне).
Python не может сравнивать aware и naive datetime — отсюда `TypeError`.

Из-за этого ЛЮБАЯ активация лицензии падает с 500, а клиент
(`licensing/license_client.py`) получает пустое тело ответа и падает на
`response.json()` с `JSONDecodeError`.

## Что нужно исправить

Файл: `signer-license-server/app/services/license_service.py`

### 1. Импорт

В начале файла заменить:
```python
from datetime import datetime
```
на:
```python
from datetime import datetime, timezone
```

### 2. Заменить все вызовы `datetime.utcnow()` на timezone-aware вариант

Найти **все** места в этом файле, где `datetime.utcnow()` используется для:
- сравнения с полями модели типа `DateTime(timezone=True)` (`current_period_end`, `first_seen`, `last_seen`, `deactivated_at`, `created_at`, `updated_at`)
- записи значения в такие поля (`device.last_seen = datetime.utcnow()` и т.п.)

Заменить каждый такой вызов на:
```python
datetime.now(timezone.utc)
```

Известные места (минимум):
- `activate_license()` — строка ~67, сравнение `license.current_period_end < now`
- `activate_license()` — обновление `existing_device.last_seen`
- `refresh_license()` — обновление `device.last_seen`
- любые другие места в этом файле с `datetime.utcnow()`, использующиеся рядом с полями `DateTime(timezone=True)`

### 3. Проверить другие файлы сервера на ту же проблему

Проверить (grep по `datetime.utcnow()`):
- `signer-license-server/app/routes/admin.py` (создание лицензии, `current_period_end = datetime.utcnow() + timedelta(...)`)
- `signer-license-server/app/services/stripe_service.py`
- `signer-license-server/app/crypto.py` (если там есть работа с датами)

Везде, где `datetime.utcnow()` присваивается или сравнивается с полем модели
`DateTime(timezone=True)`, заменить на `datetime.now(timezone.utc)` для
консистентности (даже если сейчас там нет явного бага — избежать таких же
падений в будущем).

**Важно:** при простом присваивании нового значения в `DateTime(timezone=True)`
поле (например, `created_at=datetime.utcnow()`) явного `TypeError` не будет —
SQLAlchemy/psycopg может смолчать, но лучше сразу унифицировать на
`datetime.now(timezone.utc)` во всём сервере, чтобы не плодить путаницу
naive/aware дальше.

## Критерий приёмки

1. `grep -rn "datetime.utcnow()" signer-license-server/app/` — ноль совпадений
   (везде заменено на `datetime.now(timezone.utc)`).
2. Локальный запуск: `POST /api/license/activate` с валидным лицензионным
   ключом возвращает `200 OK` с телом вида
   `{"token": "...", "plan": "...", "current_period_end": ...}`,
   а не `500 Internal Server Error`.
3. Существующие тесты в `signer-license-server/tests/` (особенно
   `test_routes_activate.py`, `test_routes_refresh.py`, `test_license_service.py`)
   проходят без изменений в самих тестах.
4. После фикса пересобрать и задеплоить сервис:
```bash
   cd signer-license-server
   bash scripts/deploy_gcloud.sh
```
   (или соответствующий `gcloud builds submit` + `gcloud run deploy`).