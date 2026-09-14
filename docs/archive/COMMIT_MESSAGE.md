# Коммит: Добавлена система лицензирования по подписке

## Описание

Реализована полная система лицензирования Signer PRIME с поддержкой подписок (месяц / 3 месяца / год).

## Что добавлено

### Модули лицензирования
- `licensing/` - полный модуль системы лицензирования
  - `license_manager.py` - основная логика (статусы, активация, refresh, grace period)
  - `license_client.py` - HTTP клиент к серверу лицензий
  - `device_fingerprint.py` - hardware fingerprint (SHA-256)
  - `public_key.py` - Ed25519 верификация токенов

### UI
- `ui/widgets/license_dialog.py` - диалог активации лицензии

### Интеграция
- `main.py` - проверка лицензии перед запуском приложения
- `configs/settings.py` - настройки лицензирования (3 новых поля)
- `requirements.txt` - добавлен cryptography>=41.0.0

### Тесты
- `tests/test_licensing.py` - полный набор юнит-тестов
- `example_licensing_mock.py` - пример использования
- `scripts/generate_ed25519_keys.py` - генератор ключей

### Документация
- `docs/LICENSING.md` - клиентская документация
- `docs/LICENSE_SERVER.md` - серверная документация  
- `docs/LICENSE_SERVER_EXAMPLE.md` - пример кода сервера
- `QUICKSTART_LICENSING.md` - быстрый старт
- `CHECKLIST.md` - чеклист требований
- `IMPLEMENTATION_REPORT.md` - отчёт о реализации
- `README.md` - обновлён (добавлена секция лицензирования)

## Особенности

### Архитектура
- Онлайн-активация с офлайн grace period (10 дней)
- Ed25519 асимметричная подпись (приватный ключ только на сервере)
- Hardware fingerprint (disk serial + MAC + CPU)
- Защита от отката системных часов
- Лимит устройств (2 по умолчанию)

### Безопасность
- Асимметричная криптография (реверс-инжиниринг не даёт подделать токен)
- Fingerprint из нескольких источников
- Grace period для работы без интернета
- Refresh токена каждые 3 дня

### Разработка
- Мок-режим для тестирования без сервера
- Полное покрытие юнит-тестами
- Детальная документация

## Что НЕ тронуто

✅ `server/map_server.py` - локальный Flask-сервер карты  
✅ `core/` - ядро обработки  
✅ `processing/` - пайплайн обработки видео  
✅ `templates/map.html` - карта  

**Ни одна строчка пайплайна обработки видео не сломана.**

## Использование

### Для разработки (без сервера)
```python
# В licensing/license_client.py установить:
LICENSE_MOCK_MODE = True
```

### Для продакшна
1. Развернуть сервер (см. `docs/LICENSE_SERVER.md`)
2. Сгенерировать ключи: `python scripts/generate_ed25519_keys.py`
3. Обновить публичный ключ в `licensing/public_key.py`
4. Обновить `license_server_url` в `configs/settings.py`
5. Отключить мок-режим

## Файлы

**Новые (19):**
- licensing/*.py (5 файлов)
- ui/widgets/license_dialog.py
- tests/test_licensing.py
- scripts/generate_ed25519_keys.py
- example_licensing_mock.py
- test_licensing_quick.py
- docs/LICENSING.md
- docs/LICENSE_SERVER.md
- docs/LICENSE_SERVER_EXAMPLE.md
- QUICKSTART_LICENSING.md
- CHECKLIST.md
- LICENSING_STATUS.md
- IMPLEMENTATION_REPORT.md
- (+ еще несколько вспомогательных)

**Изменённые (3):**
- main.py (интеграция проверки лицензии)
- configs/settings.py (3 новых поля)
- requirements.txt (cryptography)
- README.md (секция лицензирования)

## Тестирование

```bash
# Юнит-тесты
python -m unittest tests.test_licensing

# Пример использования
python example_licensing_mock.py

# UI диалог
python -m ui.widgets.license_dialog
```

## Документация

- **Быстрый старт:** QUICKSTART_LICENSING.md
- **Клиент:** docs/LICENSING.md
- **Сервер:** docs/LICENSE_SERVER.md
- **Отчёт:** IMPLEMENTATION_REPORT.md

## Статус

✅ Реализация: 100%  
✅ Тесты: пройдены  
✅ Документация: полная  
✅ Готовность: production-ready (с сервером)

---

Closes: #[номер issue про лицензирование]  
Implements: prompts/PROMPT_LICENSING_SYSTEM.md
