# Отчёт о выполнении исправлений перед production-релизом

Дата: 2026-09-13
Проект: Signer PRIME (RoadScanner)

## Выполненные задачи

### ✅ ЗАДАЧА 1 (КРИТИЧНО): Исправление фиктивной проверки dev-ключа

**Проблема:** Константа `DEV_KEY_SHA256` не соответствовала реальному хэшу текущего PEM-значения, поэтому проверка никогда не срабатывала.

**Исправления:**

1. **licensing/public_key.py**
   - Пересчитан и обновлён `DEV_KEY_SHA256` на правильное значение: `499ac7ed9b140bb3da49c0a7a429ac9bf1b7dd25154260a0810c5d89aa69d276`
   - Теперь проверка реально ловит случай "забыли заменить ключ перед сборкой прод-релиза"

2. **tests/test_licensing.py**
   - Добавлен класс `TestProductionKeyCheck` с двумя тестами:
     - `test_dev_key_detection_in_frozen_build()` — проверяет, что с dev-ключом в frozen-сборке выбрасывается RuntimeError
     - `test_non_dev_key_allowed_in_frozen_build()` — проверяет, что с новым ключом ошибки нет

**Проверка:**
```bash
python -m pytest tests/test_licensing.py::TestProductionKeyCheck -v
```

---

### ✅ ЗАДАЧА 2 (КРИТИЧНО): license_server_url должен доходить до реального клиента

**Проблема:** Default URL — это заглушка, а override идёт только через переменную окружения, которой не будет у конечного пользователя после установки .exe.

**Исправления:**

1. **configs/settings.py**
   - Добавлено чтение `license_server_url` из файла `build_config.json`
   - Приоритет источников: 1) SIGNER_LICENSE_SERVER_URL (env) → 2) build_config.json → 3) dataclass default
   - В frozen-сборке проверяется, что URL не является заглушкой — если да, выбрасывается RuntimeError

2. **build_config.json.example**
   - Создан пример файла конфигурации с комментариями

3. **scripts/build/prepare_release.bat**
   - Добавлена проверка наличия `build_config.json` перед сборкой (шаг [0/5])
   - Автоматическая проверка, что URL не является placeholder-значением
   - При обнаружении заглушки сборка прерывается с явной ошибкой
   - Добавлено копирование `build_config.json` в `dist\Signer\`

4. **RELEASE.md**
   - Добавлен новый обязательный шаг "Настройте URL сервера лицензий" (шаг 2)
   - Подробная инструкция по созданию и заполнению `build_config.json`

**Проверка:**
- Попытка запустить `prepare_release.bat` без `build_config.json` → ошибка
- Попытка запустить с placeholder URL → ошибка
- С реальным URL → сборка проходит успешно

---

### ✅ ЗАДАЧА 3: CLI для создания internal-лицензий

**Проблема:** В скрипте `create_license_manual.py` отсутствовал план "internal" в choices.

**Исправления:**

1. **signer-license-server/scripts/create_license_manual.py**
   - Добавлен `"internal"` в `choices=["monthly", "quarterly", "yearly", "internal"]`
   - Добавлен пример создания internal-лицензии в справку (epilog):
     ```bash
     python scripts/create_license_manual.py --plan internal --days 3650 --devices 50
     ```

**Проверка:**
```bash
python signer-license-server/scripts/create_license_manual.py --help
```

---

### ✅ ЗАДАЧА 4: Реальные Stripe Price ID

**Проблема:** `STRIPE_PRICE_TO_PLAN` содержал placeholder-значения, которые никогда не совпадут с реальным Stripe Price ID.

**Исправления:**

1. **signer-license-server/app/config.py**
   - Добавлены поля в `Settings`:
     - `stripe_price_id_monthly: str = ""`
     - `stripe_price_id_quarterly: str = ""`
     - `stripe_price_id_yearly: str = ""`
   - Добавлен метод `get_stripe_price_to_plan_map()`, который:
     - Строит словарь маппинга в рантайме из переменных окружения
     - Логирует явный warning при старте, если переменная не задана

2. **signer-license-server/app/services/stripe_service.py**
   - Удалён хардкод `STRIPE_PRICE_TO_PLAN`
   - В `__init__()` добавлено: `self.price_to_plan = self.settings.get_stripe_price_to_plan_map()`
   - Обновлён `handle_checkout_completed()` для использования `self.price_to_plan`

3. **signer-license-server/app/main.py**
   - Добавлена проверка Stripe Price ID при старте приложения
   - Логирование: "✅ Stripe Price IDs configured" или "⚠️ No Stripe Price IDs configured"

4. **signer-license-server/.env.example**
   - Добавлены поля с комментариями:
     ```bash
     STRIPE_PRICE_ID_MONTHLY=price_...
     STRIPE_PRICE_ID_QUARTERLY=price_...
     STRIPE_PRICE_ID_YEARLY=price_...
     ```

5. **signer-license-server/README.md**
   - Добавлен новый раздел "Настройка Stripe Price ID" с подробной инструкцией:
     - Где взять Price ID (Stripe Dashboard → Products → Price ID)
     - Как их задать через переменные окружения
     - Как проверить конфигурацию через логи Cloud Run

**Проверка:**
- При старте без STRIPE_PRICE_ID_* → warning в логах
- При старте с заданными переменными → "✅ Stripe Price IDs configured for plans: ['monthly', 'quarterly', 'yearly']"

---

### ✅ ЗАДАЧА 5: CORS по умолчанию

**Проблема:** Убедиться, что в production-деплое требуется явно задать `CORS_ALLOWED_ORIGINS`.

**Проверка:**

1. **signer-license-server/app/config.py**
   - `cors_allowed_origins: str = "*"` — дефолт для локальной разработки (без изменений)

2. **signer-license-server/app/main.py**
   - Уже есть warning: "⚠️ CORS configured with wildcard (*) - not recommended for production"

3. **signer-license-server/scripts/deploy_gcloud.sh**
   - Уже есть warning при деплое без `CORS_ALLOWED_ORIGINS`

**Итог:** Всё уже реализовано корректно, дополнительные изменения не требуются.

---

## Файлы для проверки

### Изменённые файлы:

1. `licensing/public_key.py` — исправлен DEV_KEY_SHA256
2. `tests/test_licensing.py` — добавлены тесты для ЗАДАЧИ 1
3. `configs/settings.py` — поддержка build_config.json
4. `build_config.json.example` — пример конфигурации (новый файл)
5. `scripts/build/prepare_release.bat` — проверка build_config.json
6. `RELEASE.md` — обновлена документация по релизу
7. `signer-license-server/scripts/create_license_manual.py` — добавлен "internal"
8. `signer-license-server/app/config.py` — добавлены Stripe Price ID поля
9. `signer-license-server/app/services/stripe_service.py` — динамический маппинг
10. `signer-license-server/app/main.py` — проверка Stripe Price ID при старте
11. `signer-license-server/.env.example` — добавлены Stripe Price ID
12. `signer-license-server/README.md` — раздел о настройке Stripe Price ID

### Созданные файлы:

- `test_fixes.py` — быстрая проверка всех исправлений
- `FIXES_REPORT.md` — этот отчёт

---

## Запуск тестов

### Клиентские тесты (лицензирование)

```bash
# Все тесты лицензирования
python -m pytest tests/test_licensing.py -v

# Только новые тесты проверки dev-ключа
python -m pytest tests/test_licensing.py::TestProductionKeyCheck -v
```

### Быстрая проверка исправлений

```bash
python test_fixes.py
```

### Серверные тесты

```bash
cd signer-license-server
pytest tests/ -v
```

---

## Следующие шаги перед релизом

1. **Запустить все тесты:**
   ```bash
   python -m pytest tests/test_licensing.py -v
   cd signer-license-server && pytest tests/ -v
   ```

2. **Настроить build_config.json:**
   ```bash
   copy build_config.json.example build_config.json
   # Отредактировать и указать реальный URL сервера лицензий
   ```

3. **Настроить Stripe Price IDs** (на сервере):
   - Создать продукты в Stripe Dashboard
   - Скопировать Price ID
   - Добавить в переменные окружения Cloud Run

4. **Сгенерировать production Ed25519 ключи:**
   ```bash
   python signer-license-server/scripts/generate_ed25519_keys.py
   ```

5. **Заменить публичный ключ в клиенте:**
   - Обновить `licensing/public_key.py::LICENSE_PUBLIC_KEY_PEM`
   - Пересчитать и обновить `DEV_KEY_SHA256` для нового ключа (если это dev-ключ для тестов)

6. **Запустить сборку релиза:**
   ```bash
   scripts\build\prepare_release.bat
   ```

---

## Итог

✅ Все 4 критичные задачи выполнены  
✅ ЗАДАЧА 5 проверена (уже реализована)  
✅ Добавлены юнит-тесты  
✅ Обновлена документация  
✅ Добавлены runtime-проверки  

**Система готова к production-релизу после:**
- Настройки `build_config.json`
- Генерации production-ключей
- Настройки Stripe Price IDs на сервере
