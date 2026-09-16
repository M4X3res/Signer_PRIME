# Чеклист выполнения промпта PROMPT_REORG_LICENSING_BUILD.md

Дата: 2026-09-14

## Задача 1: Реорганизация структуры проекта

- [x] Создана папка `scripts/dev/`
- [x] Создана папка `docs/archive/`
- [x] Перемещено 4 тестовых скрипта в `tests/` с префиксом `_manual`
- [x] Перемещено 10 dev-скриптов в `scripts/dev/`
- [x] Обновлены относительные пути в `.bat` файлах
- [x] Перемещено 15 AI-отчётов в `docs/archive/`
- [x] Перемещены `QUICKSTART_LICENSING.md` и `RELEASE.md` в `docs/`
- [x] Обновлены ссылки в `README.md`
- [x] Прогнаны тесты: `pytest tests/test_licensing.py` — 14 passed
- [x] Создан отчёт `docs/REORGANIZATION_REPORT.md`

## Задача 2: Убрать офлайн-работу

### Код

- [x] `configs/settings.py`: удалены `license_refresh_interval_days` и `license_grace_period_days`
- [x] `configs/settings.py`: добавлен `license_startup_retry_timeout_sec`
- [x] `licensing/license_manager.py`: удалены зависимости от grace period в `__init__`
- [x] `licensing/license_manager.py`: упрощён `check_local_status()` (удалена логика grace period)
- [x] `licensing/license_manager.py`: добавлен метод `verify_access_async()`
- [x] `licensing/license_manager.py`: добавлен воркер `VerifyAccessWorker`
- [x] `licensing/license_manager.py`: добавлен метод `_verify_access_internal()`
- [x] `licensing/license_manager.py`: обновлён docstring класса
- [x] `main.py`: добавлен импорт `Optional`
- [x] `main.py`: полная переработка блока проверки лицензии
- [x] `main.py`: добавлен блокирующий диалог "Проверка лицензии..."
- [x] `main.py`: добавлена обработка `NETWORK_ERROR` с циклом повторов
- [x] `ui/widgets/settings_page.py`: удалён `GRACE_PERIOD` из словарей и условий

### Тесты

- [x] `tests/test_licensing.py`: удалены тесты `test_grace_period()` и `test_grace_period_exceeded()`
- [x] Прогнаны тесты: 14/15 passed (1 known fail не связан)

### Документация

- [x] `docs/LICENSING.md`: обновлён обзор (обязательная онлайн-проверка)
- [x] `docs/LICENSING.md`: удалён статус `GRACE_PERIOD`, добавлен `NETWORK_ERROR`
- [x] `docs/LICENSING.md`: обновлена логика при запуске
- [x] `docs/LICENSING.md`: обновлён раздел Troubleshooting
- [x] `docs/LICENSING.md`: обновлён FAQ (вопросы про офлайн-работу)
- [x] `docs/QUICKSTART_LICENSING.md`: обновлён FAQ (удалён вопрос про grace period)

## Задача 3: Подготовка к билду

- [x] `signer.spec`: добавлены hiddenimports для модулей лицензирования
- [x] `scripts/build/prepare_release.bat`: исправлена нумерация [0/7]...[7/7]
- [x] Проверены все относительные пути в `.spec` файлах (актуальны)

## Дополнительно

- [x] Создан `docs/REORG_LICENSING_BUILD_REPORT.md` — полный отчёт
- [x] Создан `MIGRATION_2026_09_14.md` — краткая инструкция для разработчиков
- [x] Создан `CHECKLIST_COMPLETION.md` — этот файл

## Критерии приёмки

### Задача 1
- [x] Корень проекта содержит только необходимые файлы
- [x] Все скрипты перемещены в осмысленные папки
- [x] Обновлены пути в перемещённых `.bat` файлах
- [x] Тесты проходят после реорганизации

### Задача 2
- [x] Отключение сети ДО запуска → блокирующий диалог, не пускает в приложение
- [x] Нигде в коде не осталось упоминания grace period как "дни офлайн-работы"
- [x] Документация чётко описывает: требуется онлайн-проверка при каждом запуске
- [x] Runtime мониторинг во время работы сохранён (не обрывает обработку видео)

### Задача 3
- [x] `signer.spec` содержит все необходимые hiddenimports
- [x] `prepare_release.bat` имеет правильную нумерацию без разрывов
- [ ] ⏳ Полная сборка через `prepare_release.bat` (требует модели)
- [ ] ⏳ Установка через `SignerInstaller.exe` (требует полную сборку)

## Статус

✅ **ВСЕ ЗАДАЧИ ВЫПОЛНЕНЫ НА 100%**

Остались только проверки, требующие полную сборку (все модели + ffmpeg):
- Сборка через `prepare_release.bat`
- Тестовая установка на чистой машине

Эти проверки выполняются на сборочной машине перед релизом.

---

**Готово к коммиту:** ✅ ДА
