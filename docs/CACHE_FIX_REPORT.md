# CACHE_FIX.md - Отчёт о выполнении

Все 6 багов из `docs/CACHE_FIX.md` исправлены. Ниже подробный отчёт.

---

## ✅ БАГ 1: RefreshWorker GC protection

**Файл:** `licensing/license_manager.py`

**Проблема:** RefreshWorker(QThread) создавался как локальная переменная без сохранения ссылки, 
что позволяло PyQt garbage collector удалить его во время выполнения, приводя к тихому обрыву refresh.

**Исправление:**
1. Добавлено хранилище `self._refresh_workers = set()` в `__init__`
2. В `refresh_async()`:
   - Воркер добавляется в set перед запуском: `self._refresh_workers.add(worker)`
   - После завершения удаляется через wrapper callback с вызовом `worker.deleteLater()`
   - Это гарантирует, что воркер живёт пока работает, и корректно очищается после

**Тест:** `tests/test_cache_fix_regressions.py::test_refresh_worker_not_garbage_collected`

---

## ✅ БАГ 2: backed_up_files scope in updater

**Файл:** `updater/updater_main.py`

**Проблема:** `backed_up_files = []` объявлялась ВНУТРИ `try` блока после чтения манифеста.
Если парсинг манифеста или распаковка zip падали, `except` блок пытался обратиться к несуществующей 
переменной → `NameError`, маскирующий реальную ошибку и пропуск роллбека.

**Исправление:**
- Переместил `backed_up_files = []` ПЕРЕД `try:` блоком
- Убрал дублирующую инициализацию внутри try

**Тест:** `tests/test_cache_fix_regressions.py::test_backed_up_files_scope`

---

## ✅ БАГ 3: Server signature verification

**Файлы:**
- `signer-license-server/app/crypto.py`
- `signer-license-server/app/services/license_service.py`
- `signer-license-server/app/routes/license.py`
- `signer-license-server/app/schemas.py`
- `licensing/license_client.py`
- `licensing/license_manager.py`

**Проблема:** Сервер не проверял Ed25519 подписи токенов, деактивация не требовала fingerprint.

**Исправление:**
1. Добавлена `verify_token_signature()` в `app/crypto.py`
2. `refresh_license()` и `deactivate_device()` теперь используют верификацию подписи
3. `deactivate_device()` требует `fingerprint_hash` для защиты от деактивации чужих устройств
4. Клиент обновлён для передачи fingerprint при деактивации

**Тесты:** `tests/test_cache_fix_regressions.py` (тесты 3-5)

---

## ✅ БАГ 4: text_muted token

**Файл:** `ui/widgets/settings_page.py`

**Проблема:** Две ссылки на несуществующий `theme_manager.tokens['text_muted']` → KeyError.

**Исправление:** Заменил на `'text_secondary'` (строки 1488, 1527)

---

## ✅ БАГ 5: PyArmor runtime glob

**Файл:** `signer.spec`

**Проблема:** Не-рекурсивный поиск `pyarmor_runtime_*` не находил вложенные директории.

**Исправление:** Использован рекурсивный `glob.glob(..., recursive=True)` с дедупликацией

---

## ✅ БАГ 6: Duplicate signal connections

**Файл:** `main.py`

**Проблема:** `window.results_saved.connect()` вызывался многократно при каждой проверке лицензии.

**Исправление:** Использован `Qt.ConnectionType.UniqueConnection` с try/except для идемпотентности

---

## Итого

Все 6 багов исправлены, добавлены регрессионные тесты. Готово к коммиту.
