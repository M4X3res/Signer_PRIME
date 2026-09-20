# Чек-лист подготовки релиза Signer PRIME

Пошаговый чек-лист для подготовки production релиза.

## Перед запуском сборки

### 1. Чистота git рабочего дерева ✅ АВТОМАТИЧЕСКИ

**Проверка:** `git status --porcelain` должен быть пустым

**Автоматизация:** `prepare_release.bat` автоматически проверяет в начале и конце сборки.

**Действия при ошибке:**
```bash
# Закоммитить изменения
git add -A
git commit -m "pre-release: your changes"

# Или сохранить во временный stash
git stash save "pre-release changes"
```

### 2. Конфигурация лицензионного сервера ✅ АВТОМАТИЧЕСКИ

**Файл:** `build_config.json`

**Проверка:**
- Файл существует
- Содержит реальный (не placeholder) URL
- URL соответствует развёрнутому Cloud Run сервису

**Автоматизация:** `prepare_release.bat` автоматически проверяет:
- Наличие файла
- Отсутствие `https://license.signer-prime.com` (placeholder)
- Отсутствие `https://your-license-server.run.app` (example)

**Текущий URL:** `https://signer-license-server-1047715133540.europe-west1.run.app`

**Действия при ошибке:**
```bash
# Скопировать из примера
copy build_config.json.example build_config.json

# Отредактировать вручную, указав реальный URL
```

### 3. Production Ed25519 ключ ⚠️ РУЧНАЯ ПРОВЕРКА

**Файл:** `licensing/public_key.py`

**Проверка:**
- `LICENSE_PUBLIC_KEY_PEM` содержит production ключ (не dev)
- Ключ соответствует приватному ключу на сервере

**Автоматизация:** Частичная - `_check_production_key()` роняет `RuntimeError` в frozen build при совпадении с `DEV_KEY_SHA256`.

**⚠️ ВАЖНО:** Это проверка что НЕ используется dev-ключ, но НЕ проверяет что используется ПРАВИЛЬНЫЙ prod-ключ!

**Действия:**
```bash
# Генерация новой пары ключей (если нужно)
python scripts/generate_ed25519_keys.py

# Скопировать публичный ключ в licensing/public_key.py
# Обновить приватный ключ на сервере в .env
```

### 4. Версия инкрементирована ⚠️ РУЧНАЯ ПРОВЕРКА

**Файлы:**
- `version.json` - версия клиента
- `installer/SignerInstaller.iss` - `AppVersion`

**Проверка:** Оба файла содержат одинаковую версию, больше предыдущего релиза

**Пример:**
```json
// version.json
{
  "version": "2.1.0"
}
```

```iss
; SignerInstaller.iss
#define AppVersion "2.1.0"
```

**Действия:**
- Обновить оба файла вручную
- Синхронизировать версии

### 5. Все тесты проходят ✅ АВТОМАТИЧЕСКИ (рекомендуется)

**Проверка:**
```bash
# Запустить все тесты
scripts\dev\run_all_tests.bat
```

**Что проверяется:**
- Тесты лицензирования (15 тестов)
- Ручные тесты (main import, client init, fixes)
- ⚠️ Серверные тесты НЕ проверяются (отдельный CI)

**Действия при падении:**
- Исправить проблемы
- Перезапустить тесты
- НЕ собирать релиз с падающими тестами

### 6. ML-модели присутствуют ⚠️ РУЧНАЯ ПРОВЕРКА

**Директории:**
- `CNN_side/` - модели классификации
- `lane_guidance_models/` - модели разметки
- `small_models/` - компактные модели

**Проверка:** Директории существуют и содержат `.onnx` файлы

**Автоматизация:** `signer.spec` печатает WARNING если директории нет, но НЕ прерывает сборку.

**⚠️ РЕКОМЕНДУЕТСЯ:** Добавить `sys.exit(1)` в `signer.spec` для критичных моделей.

**Действия:**
- Убедиться что модели экспортированы
- Проверить `.gitignore` (модели не в git)

### 7. Инструменты сборки присутствуют ✅ АВТОМАТИЧЕСКИ

**Проверка:**
- Python venv: `.venv/Scripts/python.exe`
- PyInstaller: `pip show pyinstaller`
- 7-Zip: `installer/7z.exe`, `installer/7z.dll`
- PyArmor: `pip show pyarmor` (>=9.0.0)

**Автоматизация:** `prepare_release.bat` автоматически проверяет все инструменты.

**Действия при ошибке:**
```bash
# Установить зависимости
pip install -r requirements-dev.txt

# Скачать 7-Zip standalone
# https://www.7-zip.org/
# Распаковать 7z.exe и 7z.dll в installer/
```

### 8. Режим лицензии - production ✅ АВТОМАТИЧЕСКИ

**Проверка:** Нет флагов mock/dev режима в коде

**Статус:** `LICENSE_MOCK_MODE` был удалён в предыдущих итерациях.

**Автоматизация:** Не требуется, функциональность отсутствует.

## Запуск сборки

### 9. Выполнить prepare_release.bat ✅

```bash
scripts\build\prepare_release.bat
```

**Что происходит:**
1. ✅ Проверка зависимостей
2. ✅ Очистка старых сборок (`build/`, `dist/`, `release/`)
3. ✅ Обфускация licensing/ через PyArmor (→ `build/obfuscated/`)
4. ✅ Сборка Signer.exe и Updater.exe
5. ✅ Восстановление оригинальных файлов
6. ✅ Проверка git diff (НЕ должны остаться обфусцированные файлы!)
7. ✅ Создание многотомного архива (100MB части)
8. ✅ Вычисление SHA-256 checksums
9. ✅ Подготовка файлов в `release/`

**Длительность:** ~10-15 минут (зависит от размера моделей)

### 10. Проверка после сборки ✅ АВТОМАТИЧЕСКИ

**Автоматическая верификация в prepare_release.bat:**
- `git diff --quiet licensing/ main.py` - НЕ должно быть изменений
- Наличие всех файлов в `release/`

**Ручная проверка:**
```bash
# Проверить git status
git status --porcelain

# Должно быть пусто (кроме untracked release/)
```

**Содержимое `release/`:**
- `Signer.7z.001` ... `Signer.7z.NNN` - многотомный архив
- `checksum.sha256` - контрольные суммы
- `README.md` - инструкции
- `release_notes.txt` - changelog

## Публикация релиза

### 11. Загрузка на GitHub ✅

```powershell
# Автоматическая публикация (требует GitHub CLI)
.\scripts\build\upload_release.ps1

# Или вручную
# 1. https://github.com/YOUR_REPO/releases/new
# 2. Создать tag: v{version} (например: v2.1.0)
# 3. Загрузить ВСЕ файлы из release/
# 4. Вставить release_notes.txt в описание
```

### 12. Финальные проверки

- [ ] Релиз опубликован на GitHub
- [ ] Архивы доступны для скачивания
- [ ] Checksums совпадают
- [ ] Updater.exe работает (автообновление)
- [ ] Инсталлер создаётся корректно (опционально)

## Rollback процедура

Если что-то пошло не так:

### При ошибке обфускации

```bash
# Восстановить оригинальные файлы
python scripts/build/restore_originals.py

# Проверить git diff
git diff licensing/ main.py

# Откатить если нужно
git checkout -- licensing/ main.py
```

### При ошибке сборки

```bash
# Очистить build артефакты
rmdir /s /q build dist release

# Проверить git status
git status --porcelain

# Исправить проблемы и повторить
```

### При ошибке публикации

```bash
# Удалить draft релиз на GitHub
# Исправить проблемы
# Повторить upload_release.ps1
```

## Troubleshooting

### "PyArmor изменил исходные файлы"

**Причина:** `obfuscate_licensing.py` обнаружил что `licensing/` или `main.py` изменились после обфускации.

**Решение:**
1. Скрипт автоматически откатывает через `git checkout`
2. Проверить конфигурацию PyArmor в `obfuscate_licensing.py`
3. Убедиться что используется `-O build/obfuscated/` флаг

### "Git working tree не чистый"

**Причина:** Есть uncommitted changes.

**Решение:**
```bash
git status
git add -A && git commit -m "pre-release"
# Или
git stash
```

### "7z.exe не найден"

**Причина:** Отсутствуют файлы 7-Zip.

**Решение:**
1. Скачать 7-Zip standalone: https://www.7-zip.org/
2. Распаковать `7z.exe` и `7z.dll` в `installer/`

### "Модели не найдены"

**Причина:** ML-модели не экспортированы или не на диске.

**Решение:**
1. Проверить наличие директорий `CNN_side/`, `lane_guidance_models/`, `small_models/`
2. Экспортировать модели если нужно
3. Убедиться что пути в `signer.spec` корректны

## Notes

- ✅ = Автоматическая проверка в `prepare_release.bat`
- ⚠️ = Ручная проверка обязательна
- 📝 = Рекомендуемая проверка

**Последнее обновление:** 2026-09-14
