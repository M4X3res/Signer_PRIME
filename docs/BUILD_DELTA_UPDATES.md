# Дельта-обновления Signer PRIME

Система дифференциальных обновлений для минимизации объёма скачиваемых данных при обновлении.

## Обзор

Вместо скачивания полного архива (3-5 ГБ) при каждом обновлении, пользователи теперь скачивают только изменившиеся файлы (обычно 10-200 МБ для небольших изменений).

### Типы обновлений

- **Дельта-обновление (быстрое)**: Скачиваются только изменённые/новые файлы
- **Полное обновление**: Весь архив `Signer.7z.*` (для первичной установки или если дельта недоступна)

## Архитектура

### Компоненты

1. **`scripts/build_release_manifest.py`** — генерирует манифест файлов и дельта-пакеты
2. **`manifest.json`** — список всех файлов с SHA-256 хешами
3. **`delta-from-X.Y.Z.zip`** — архив с изменёнными/новыми файлами
4. **`delta_manifest.json`** — метаданные дельта-пакета
5. **`updater.py`** — выбирает delta vs full при проверке обновлений
6. **`updater_main.py`** — применяет дельта-обновления с бэкапом/роллбеком

### Формат manifest.json

```json
{
  "version": "2.1.0",
  "generated_at": "2026-09-11T12:00:00Z",
  "files": {
    "Signer.exe": {
      "sha256": "abc123...",
      "size": 12345678
    },
    "_internal/PyQt6/QtCore.pyd": {
      "sha256": "def456...",
      "size": 98765
    }
  }
}
```

### Формат delta_manifest.json

```json
{
  "from_version": "2.0.0",
  "to_version": "2.1.0",
  "changed_or_added": ["Signer.exe", "_internal/core/detector.py"],
  "removed": ["small_models/old_model.pt"],
  "archive_sha256": "...",
  "archive_size": 12345678,
  "target_manifest_sha256": "..."
}
```

## Процесс сборки релиза

### 1. Сборка dist/Signer

```bash
# Обычная сборка через PyInstaller
build.bat
```

### 2. Генерация манифеста и дельта-пакета

```bash
python scripts/build_release_manifest.py \
    --dist-dir dist/Signer \
    --repo M4X3res/Signer_PRIME \
    --out-dir dist/release_assets \
    --current-version 2.1.0
```

Скрипт:
- Сканирует `dist/Signer` и вычисляет SHA-256 всех файлов
- Скачивает `manifest.json` из последнего релиза GitHub
- Вычисляет diff (added, changed, removed)
- Создаёт `delta-from-2.0.0.zip` с изменёнными файлами
- Генерирует `delta_manifest.json`

### 3. Публикация релиза

Загрузить на GitHub Release как ассеты:

1. **Полный архив** (для первичной установки):
   - `Signer.7z.001`, `Signer.7z.002`, ...
   - `checksum.sha256`

2. **Дельта-обновление** (для существующих пользователей):
   - `manifest.json`
   - `delta-from-2.0.0.zip`
   - `delta_manifest.json`

#### Через PowerShell (upload_release.ps1)

Обновите скрипт для загрузки дополнительных файлов:

```powershell
# Загрузка дельта-файлов (если существуют)
if (Test-Path "dist\release_assets\manifest.json") {
    gh release upload $TAG dist\release_assets\manifest.json --clobber
}

if (Test-Path "dist\release_assets\delta-from-*.zip") {
    gh release upload $TAG dist\release_assets\delta-from-*.zip --clobber
}

if (Test-Path "dist\release_assets\delta_manifest.json") {
    gh release upload $TAG dist\release_assets\delta_manifest.json --clobber
}
```

## Как работает обновление на клиенте

### Проверка обновлений

`updater.py::check_for_update()`:

1. Запрашивает `/repos/M4X3res/Signer_PRIME/releases/latest`
2. Ищет в ассетах:
   - `manifest.json`
   - `delta_manifest.json`
   - `delta-from-{APP_VERSION}.zip`
3. Если все три файла найдены и `delta_manifest.from_version == APP_VERSION`:
   - Возвращает `UpdateInfo(is_delta=True)` с размером дельта-архива
4. Иначе:
   - Возвращает `UpdateInfo(is_delta=False)` со списком `Signer.7z.*`

### Загрузка

`updater.py::download_assets()`:

- Поддерживает докачку (HTTP Range-запросы)
- Файлы сохраняются с расширением `.part` во время загрузки
- После успешной загрузки переименовываются в финальное имя

### Проверка целостности

`updater.py::verify_downloaded_assets()`:

- **Delta**: проверяет SHA-256 `delta-from-X.zip` по `delta_manifest.archive_sha256`
- **Full**: проверяет все `Signer.7z.*` по `checksum.sha256`

### Применение обновления

`updater_main.py` запускается после закрытия `Signer.exe`:

#### Дельта-режим (`--mode delta`)

1. Распаковывает `delta-from-X.zip` в `_delta_extracted/`
2. Читает `delta_manifest.json`
3. **Бэкап**: Копирует существующие файлы в `.update_backup/`
4. **Применение**: Для каждого файла из `changed_or_added`:
   - Копирует во временный файл `<file>.new`
   - Атомарно заменяет через `os.replace()`
5. **Удаление**: Удаляет файлы из списка `removed`
6. **Успех**: Удаляет `.update_backup/`
7. **Ошибка**: Восстанавливает файлы из `.update_backup/`

#### Полный режим (`--mode full`)

1. Распаковывает `Signer.7z.001` через `7z.exe`
2. Перезаписывает `install_dir` поверх

### Ретраи и надёжность

- **Сетевые запросы**: 3 попытки с экспоненциальной задержкой
- **Файловые операции**: 5 попыток с задержкой (для борьбы с блокировкой антивирусом)
- **Роллбек**: Автоматическое восстановление при любой ошибке применения

## Настройки пользователя

### UI (Настройки → Обновления)

- **Автопроверка обновлений**: Проверять при запуске (по умолчанию: включено)
- **Канал обновлений**: Стабильный / Бета (по умолчанию: стабильный)
- **Проверить сейчас**: Ручная проверка обновлений
- **Последняя проверка**: Timestamp последней проверки

### QSettings (сохраняются автоматически)

```python
auto_check_updates: bool = True
update_channel: Literal["stable", "beta"] = "stable"
last_update_check_ts: float = 0.0
```

## Отладка

### Логи

- **Клиент** (проверка и загрузка): `Signer.log` (секция `[updater]`)
- **Updater** (применение): `updater.log` (рядом с `Updater.exe`)

### Тестирование локально

1. Создать два "релиза" в разных папках:
   ```
   dist/Signer_v2.0/
   dist/Signer_v2.1/
   ```

2. Сгенерировать манифесты:
   ```bash
   python scripts/build_release_manifest.py --dist-dir dist/Signer_v2.0 --current-version 2.0.0 --out-dir dist/release_v2.0
   python scripts/build_release_manifest.py --dist-dir dist/Signer_v2.1 --current-version 2.1.0 --out-dir dist/release_v2.1
   ```

3. Вручную вычислить дельту:
   ```python
   import json
   with open("dist/release_v2.0/manifest.json") as f:
       old_manifest = json.load(f)
   with open("dist/release_v2.1/manifest.json") as f:
       new_manifest = json.load(f)
   
   # Используйте compute_delta() из build_release_manifest.py
   ```

4. Протестировать `updater_main.py`:
   ```bash
   Updater.exe --pid 12345 --temp "C:\path\to\delta" --install "C:\path\to\install" --exe "C:\path\to\Signer.exe" --7z "C:\path\to\7z.exe" --mode delta --delta-manifest "C:\path\to\delta_manifest.json"
   ```

## Ограничения и особенности

### Когда дельта недоступна

- Первичная установка (нет предыдущей версии)
- Пропущено несколько версий (нет `delta-from-1.5.0.zip` для пользователя на 1.5.0, если последний релиз 2.1.0 содержит только `delta-from-2.0.0.zip`)
- Манифест предыдущей версии отсутствует

В этих случаях клиент автоматически fallback на полное обновление.

### Не поддерживается

- **Цепочки дельт**: Нельзя применить `1.5→2.0→2.1` одним обновлением (каждая дельта только для одной версии)
- **Downgrade**: Только обновление вперёд
- **Patch файлов**: Бинарный diff не используется — заменяется весь файл

### Безопасность

- Проверка SHA-256 всех скачанных файлов
- Атомарная замена файлов (`os.replace()`)
- Бэкап + роллбек при ошибке применения
- Очистка старых временных файлов при старте (`cleanup_stale_update_temp()`)

## Частые проблемы

### "Дельта-архив не найден"

**Причина**: Пользователь на версии, для которой нет дельты.

**Решение**: Автоматический fallback на full-обновление. Пользователю не нужно ничего делать.

### "delta apply failed at file X"

**Причина**: Файл отсутствует в дельта-архиве или ошибка распаковки.

**Решение**: 
- Проверить `delta_manifest.json` — файл должен быть в списке `changed_or_added`
- Проверить целостность `delta-from-X.zip`
- Откат произойдёт автоматически, файлы восстановятся из бэкапа

### "Updater.exe не может заменить файл (Permission Denied)"

**Причина**: Антивирус или File Explorer держат файл открытым.

**Решение**: Встроены ретраи (5 попыток с экспоненциальной задержкой). Если не помогло — логируется ошибка, выполняется роллбек.

## Производительность

### Типичные размеры

| Изменение                          | Delta размер | Full размер | Экономия  |
|------------------------------------|--------------|-------------|-----------|
| Исправление бага (1-2 .py файла)   | 5-10 MB      | 3.5 GB      | **99.7%** |
| Обновление модели (1 .pt файл)     | 50-100 MB    | 3.5 GB      | **97%**   |
| Обновление PyTorch/PyQt (dll)      | 200-500 MB   | 3.5 GB      | **85%**   |
| Полная смена архитектуры           | ~3 GB        | 3.5 GB      | ~15%      |

### Время генерации

- Сканирование `dist/Signer` (2000+ файлов): ~10-30 сек
- Вычисление дельты: < 1 сек
- Создание `delta-from-X.zip`: 5-60 сек (зависит от числа изменений)

## Roadmap

Возможные улучшения (не реализованы):

- [ ] Цепочки дельт для пропуска версий
- [ ] Бинарный diff файлов (bsdiff, xdelta) для дополнительного сжатия
- [ ] Параллельная загрузка нескольких ассетов
- [ ] Прогресс-бар применения обновления (сейчас только для загрузки)
- [ ] P2P распространение обновлений (torrent)
- [ ] Инкрементальная верификация (проверка хешей во время apply, а не после)
