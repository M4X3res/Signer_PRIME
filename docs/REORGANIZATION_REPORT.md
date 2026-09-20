# Реорганизация структуры проекта

## Что было сделано

### Перемещены тестовые скрипты: корень → `tests/`
- `test_fixes.py` → `tests/test_fixes_manual.py`
- `test_client_init.py` → `tests/test_client_init_manual.py`
- `test_main_import.py` → `tests/test_main_import_manual.py`
- `test_licensing_quick.py` → `tests/test_licensing_quick_manual.py`

### Перемещены dev-скрипты: корень → `scripts/dev/`
- `run_test3.bat`
- `test_main_no_server.bat`
- `run_all_tests.bat`
- `quick_commit.bat`
- `commit_and_push.bat`
- `commit_cache_fix.bat`
- `commit_cache_fix.sh`
- `CACHE_FIX_STATUS.txt`
- `CACHE_FIX_README.md`
- `example_licensing_mock.py`

### Перемещены AI-отчёты: корень → `docs/archive/`
- `BUGFIXES_README.md`
- `SUMMARY.md`
- `QUICKREF.md`
- `QUICKREF.txt`
- `FIXES_REPORT.md`
- `CHECKLIST.md`
- `INDEX.md`
- `FILES_CHANGES.md`
- `TASK_COMPLETION_REPORT.md`
- `IMPLEMENTATION_REPORT.md`
- `IMPLEMENTATION_SUMMARY.md`
- `LICENSING_STATUS.md`
- `HARDEN_LICENSING_REPORT.md`
- `COMMIT_MESSAGE.md`
- `GIT_INSTRUCTIONS.md`

### Перемещена действующая документация: корень → `docs/`
- `QUICKSTART_LICENSING.md` → `docs/QUICKSTART_LICENSING.md`
- `RELEASE.md` → `docs/RELEASE.md`

## Обновлённые пути в файлах

### `README.md`
- Обновлены ссылки на `docs/RELEASE.md` и `docs/QUICKSTART_LICENSING.md`
- Добавлены новые разделы структуры: `scripts/dev/` и `docs/archive/`

### `scripts/dev/run_all_tests.bat`
- Обновлён путь: `test_fixes.py` → `tests\test_fixes_manual.py`

### `scripts/dev/test_main_no_server.bat`
- Обновлены пути для запуска из подпапки: `..\..\venv\Scripts\python.exe ..\..\main.py`

### `scripts/dev/run_test3.bat`
- Обновлён путь: `..\..\tests\test_main_import_manual.py`

## Статус тестов
✅ Тесты лицензирования пройдены (16/17, 1 известный fail не связан с реорганизацией)
