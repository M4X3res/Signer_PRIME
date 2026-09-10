# Инструкция по сборке Signer PRIME с автообновлением

## Предварительные требования

1. **7-Zip (7z.exe и 7z.dll)**
   - Уже имеются в `installer\7z.exe` и `installer\7z.dll`
   - Эти же файлы используются для Inno Setup инсталлятора
   - Если отсутствуют, установите 7-Zip с https://www.7-zip.org/
   - Скопируйте `7z.exe` и `7z.dll` из `C:\Program Files\7-Zip\` в `installer\`

2. **Python окружение**
   - Установите все зависимости: `pip install -r requirements.txt`
   - Установите PyInstaller: `pip install pyinstaller`

## Последовательность команд сборки

Выполняйте команды из корня проекта:

### Шаг 1: Сборка основного приложения (Signer.exe)

```cmd
pyinstaller signer.spec --noconfirm
```

Результат: `dist\Signer\Signer.exe` + папка `_internal` с зависимостями

### Шаг 2: Сборка Updater.exe

```cmd
pyinstaller updater.spec --noconfirm
```

Результат: `dist\Updater\Updater.exe` (один файл, без `_internal`)

### Шаг 3: Копирование Updater и 7z в финальную сборку

```cmd
copy dist\Updater\Updater.exe dist\Signer\Updater.exe
copy installer\7z.exe dist\Signer\7z.exe
copy installer\7z.dll dist\Signer\7z.dll
```

### Шаг 4: Проверка структуры dist\Signer\

Должна получиться следующая структура:

```
dist\Signer\
├── Signer.exe         ← Основное приложение
├── Updater.exe        ← Апплаер обновлений
├── 7z.exe             ← Утилита распаковки
├── 7z.dll             ← Библиотека 7-Zip
├── _internal\         ← Зависимости PyInstaller
├── assets\            ← Ресурсы приложения
├── CNN_side\          ← Модели YOLO
├── small_models\      ← Модели классификации
├── lane_guidance_models\
├── sings\
├── sings_text\
├── static\
├── templates\
└── signs.json
```

## Создание релиза для GitHub

### Шаг 5: Архивация dist\Signer\ в многотомный 7z

```cmd
cd dist
7z a -v100m -mx=5 Signer.7z Signer\*
```

Параметры:
- `-v100m` — размер тома 100 MB (можно изменить)
- `-mx=5` — уровень сжатия (5 = нормальный, 9 = максимальный, медленнее)

Результат: `Signer.7z.001`, `Signer.7z.002`, `Signer.7z.003`, ...

### Шаг 6: Вычисление чексумм SHA-256

```powershell
# В PowerShell, из директории dist\
Get-ChildItem -Filter "Signer.7z.*" | ForEach-Object {
    $hash = (Get-FileHash $_.Name -Algorithm SHA256).Hash
    "$hash  $($_.Name)"
} | Out-File -Encoding utf8 checksum.sha256
```

Или вручную для каждого файла:

```cmd
certutil -hashfile Signer.7z.001 SHA256 >> checksum.sha256
certutil -hashfile Signer.7z.002 SHA256 >> checksum.sha256
certutil -hashfile Signer.7z.003 SHA256 >> checksum.sha256
```

Формат `checksum.sha256` должен быть:

```
<hash>  Signer.7z.001
<hash>  Signer.7z.002
<hash>  Signer.7z.003
```

### Шаг 7: Создание релиза на GitHub

1. Перейдите в https://github.com/M4X3res/Signer_PRIME/releases/new
2. Создайте новый тег версии (например, `v2.0.0`)
3. Заполните release notes
4. Прикрепите файлы:
   - `Signer.7z.001`
   - `Signer.7z.002`
   - `Signer.7z.003`
   - ...
   - `checksum.sha256`
5. Опубликуйте релиз

## Тестирование автообновления

### Локальное тестирование диалога обновления

1. Временно измените версию в `version.py` на более старую:
   ```python
   APP_VERSION = "1.9.0"
   ```

2. Пересоберите приложение

3. Запустите `dist\Signer\Signer.exe`

4. При старте должен появиться диалог обновления (если на GitHub есть релиз с версией выше 1.9.0)

5. После теста верните реальную версию в `version.py`

### Полное тестирование апплая обновления

1. Создайте релиз на GitHub с версией выше текущей

2. Запустите установленный Signer.exe

3. Должен появиться диалог обновления

4. Нажмите "Обновить"

5. После загрузки:
   - Signer.exe закроется
   - Запустится Updater.exe (в фоне)
   - Updater распакует обновление
   - Запустится обновлённый Signer.exe

6. Проверьте версию в окне приложения и в статус-баре (должно появиться уведомление "Signer обновлён до версии X.X.X")

## Troubleshooting

### Проблема: "7z.exe не найден"

- Убедитесь, что `installer\7z.exe` и `installer\7z.dll` существуют ПЕРЕД сборкой
- Проверьте, что в `dist\Signer\7z.exe` и `dist\Signer\7z.dll` присутствуют после сборки
- Если нет - выполните `copy installer\7z.exe dist\Signer\7z.exe` и `copy installer\7z.dll dist\Signer\7z.dll` вручную

### Проблема: "Updater.exe не найден"

- Проверьте, что `dist\Signer\Updater.exe` существует
- Если нет - выполните `copy dist\Updater\Updater.exe dist\Signer\Updater.exe`

### Проблема: Ошибка при распаковке обновления

- Откройте `updater.log` (рядом с Signer.exe) для диагностики
- Проверьте, что чексуммы файлов совпадают
- Убедитесь, что все тома архива скачаны корректно

### Проблема: Обновление не предлагается

- Проверьте, что на GitHub есть релиз с версией выше текущей
- Убедитесь, что релиз опубликован (не draft)
- Проверьте логи в `roadscan.log` на предмет ошибок при проверке обновлений
- В dev-режиме установите переменную окружения: `set SIGNER_FORCE_UPDATE_CHECK=1`

## Автоматизация сборки (опционально)

Можно создать bat-скрипт для автоматизации шагов 1-3:

```batch
@echo off
echo === Сборка Signer PRIME ===

echo [1/3] Сборка Signer.exe...
pyinstaller signer.spec --noconfirm
if errorlevel 1 goto error

echo [2/3] Сборка Updater.exe...
pyinstaller updater.spec --noconfirm
if errorlevel 1 goto error

echo [3/3] Копирование файлов...
copy dist\Updater\Updater.exe dist\Signer\Updater.exe
copy assets\7za.exe dist\Signer\7za.exe

echo === Сборка завершена успешно ===
echo Результат в dist\Signer\
goto end

:error
echo === ОШИБКА СБОРКИ ===
exit /b 1

:end
```

Сохраните как `build.bat` и запускайте из корня проекта.


---

## Быстрое тестирование автообновлений

Благодаря использованию `version.json` можно тестировать систему обновлений БЕЗ пересборки!

### Способ 1: Тест диалога обновления (без реального обновления)

1. **Измените версию в собранном приложении:**
   
   Откройте `dist\Signer\version.json` и измените версию:
   ```json
   {
     "version": "1.9.0",
     "build_date": "2026-09-10"
   }
   ```

2. **Создайте тестовый релиз на GitHub:**
   - Перейдите на https://github.com/M4X3res/Signer_PRIME/releases/new
   - Создайте тег `v2.0.0` (выше чем 1.9.0)
   - Добавьте release notes
   - Опубликуйте (файлы можно не прикреплять для теста диалога)

3. **Запустите приложение:**
   ```cmd
   dist\Signer\Signer.exe
   ```
   
   Должен появиться диалог "Доступно обновление 2.0.0"

4. **Верните версию обратно:**
   
   Откройте `dist\Signer\version.json`:
   ```json
   {
     "version": "2.0.0",
     "build_date": "2026-09-10"
   }
   ```

### Способ 2: Полный тест с реальным обновлением

1. **Скопируйте собранное приложение в тестовую директорию:**
   ```cmd
   xcopy /E /I dist\Signer C:\TestSigner\
   ```

2. **Создайте релиз 2.0.0 на GitHub** (как описано выше, с реальными архивами)

3. **Измените версию в тестовой копии:**
   
   Откройте `C:\TestSigner\version.json`:
   ```json
   {
     "version": "1.9.0",
     "build_date": "2026-09-10"
   }
   ```

4. **Запустите тестовую копию:**
   ```cmd
   C:\TestSigner\Signer.exe
   ```

5. **Нажмите "Обновить"** и проверьте весь процесс

6. **После обновления** проверьте, что:
   - Версия изменилась на 2.0.0
   - Файлы обновились
   - В статус-баре появилось уведомление

### Проверка работы

**Должно работать:**
- ✅ Диалог появляется при наличии новой версии
- ✅ Release notes отображаются
- ✅ Прогресс загрузки работает
- ✅ Обновление применяется
- ✅ Приложение перезапускается

**Логи для диагностики:**
```cmd
# Логи приложения
type dist\Signer\roadscan.log | findstr /i "update version"

# Логи Updater
type C:\TestSigner\updater.log
```
