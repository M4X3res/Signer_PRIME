@echo off
chcp 65001 >nul
REM ============================================================================
REM Автоматическая сборка и подготовка релиза Signer PRIME
REM Версия: 2.0
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ════════════════════════════════════════════════════════════════
echo   🚀 Автоматическая сборка релиза Signer PRIME
echo ════════════════════════════════════════════════════════════════
echo.

REM Получение версии из version.json
for /f "tokens=2 delims=:, " %%a in ('type version.json ^| findstr "version"') do (
    set VERSION=%%~a
)
echo 📦 Версия: %VERSION%
echo.

REM ============================================================================
REM Шаг 0: Проверка зависимостей
REM ============================================================================

echo [0/7] ⚙️  Проверка зависимостей...
echo.

REM Проверка Python
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден в PATH
    pause
    exit /b 1
)
echo ✅ Python найден

REM Проверка PyInstaller
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ❌ PyInstaller не установлен
    echo    Установите: pip install pyinstaller
    pause
    exit /b 1
)
echo ✅ PyInstaller установлен

REM Проверка 7-Zip
if not exist "installer\7z.exe" (
    echo ❌ 7z.exe не найден в installer\
    echo    Скачайте: https://www.7-zip.org/download.html
    pause
    exit /b 1
)
if not exist "installer\7z.dll" (
    echo ❌ 7z.dll не найден в installer\
    pause
    exit /b 1
)
echo ✅ 7-Zip найден
echo.

REM ============================================================================
REM Шаг 1: Очистка старых сборок
REM ============================================================================

echo [1/7] 🧹 Очистка старых сборок...
if exist "dist\Signer" (
    echo    Удаление dist\Signer...
    rmdir /s /q "dist\Signer" 2>nul
)
if exist "dist\Updater" (
    echo    Удаление dist\Updater...
    rmdir /s /q "dist\Updater" 2>nul
)
if exist "build" (
    echo    Удаление build...
    rmdir /s /q "build" 2>nul
)
if exist "release" (
    echo    Удаление старого release...
    rmdir /s /q "release" 2>nul
)
echo ✅ Очистка завершена
echo.

REM ============================================================================
REM Шаг 2: Сборка основного приложения (Signer.exe)
REM ============================================================================

echo [2/7] 🔨 Сборка Signer.exe...
pyinstaller signer.spec --noconfirm
if errorlevel 1 (
    echo ❌ Ошибка сборки Signer.exe
    pause
    exit /b 1
)
echo ✅ Signer.exe собран
echo.

REM ============================================================================
REM Шаг 3: Сборка Updater.exe
REM ============================================================================

echo [3/7] 🔨 Сборка Updater.exe...
pyinstaller updater.spec --noconfirm
if errorlevel 1 (
    echo ❌ Ошибка сборки Updater.exe
    pause
    exit /b 1
)
echo ✅ Updater.exe собран
echo.

REM ============================================================================
REM Шаг 4: Копирование файлов
REM ============================================================================

echo [4/7] 📋 Копирование необходимых файлов...

copy /Y "dist\Updater\Updater.exe" "dist\Signer\Updater.exe" >nul
if errorlevel 1 (
    echo ❌ Не удалось скопировать Updater.exe
    pause
    exit /b 1
)
echo    ✅ Updater.exe скопирован

copy /Y "installer\7z.exe" "dist\Signer\7z.exe" >nul
if errorlevel 1 (
    echo ❌ Не удалось скопировать 7z.exe
    pause
    exit /b 1
)
echo    ✅ 7z.exe скопирован

copy /Y "installer\7z.dll" "dist\Signer\7z.dll" >nul
if errorlevel 1 (
    echo ❌ Не удалось скопировать 7z.dll
    pause
    exit /b 1
)
echo    ✅ 7z.dll скопирован

REM Копирование version.json для автообновления
copy /Y "version.json" "dist\Signer\version.json" >nul
echo    ✅ version.json скопирован

echo ✅ Все файлы скопированы
echo.

REM ============================================================================
REM Шаг 5: Создание архива для GitHub Release
REM ============================================================================

echo [5/7] 📦 Создание многотомного архива...
echo.

REM Создаем папку release
mkdir release 2>nul

REM Переходим в dist и создаем архив
cd dist

REM Удаляем старые архивы если есть
del /q Signer.7z.* 2>nul

REM Создаем многотомный архив (100MB части)
echo    Архивирование dist\Signer...
echo    (Это может занять несколько минут)
echo.
..\installer\7z.exe a -v100m -mx=5 Signer.7z Signer\* -xr!*.pyc -xr!__pycache__
if errorlevel 1 (
    echo ❌ Ошибка при создании архива
    cd ..
    pause
    exit /b 1
)

echo.
echo ✅ Архив создан
echo.

REM Показываем созданные части
echo    Созданные части архива:
for %%f in (Signer.7z.*) do (
    echo       - %%f ^(%%~zf байт^)
)
echo.

REM ============================================================================
REM Шаг 6: Вычисление SHA-256 чексумм
REM ============================================================================

echo [6/7] 🔐 Вычисление SHA-256 чексумм...
echo.

REM Удаляем старый файл чексумм
del /q checksum.sha256 2>nul

REM Вычисляем чексуммы для всех частей архива
for %%f in (Signer.7z.*) do (
    echo    Обработка %%f...
    for /f "skip=1 tokens=*" %%h in ('certutil -hashfile "%%f" SHA256') do (
        if not "%%h"=="" (
            if not "%%h"=="CertUtil: -hashfile команда успешно выполнена." (
                echo %%h  %%f >> checksum.sha256
                goto :next_file
            )
        )
    )
    :next_file
)

echo ✅ Чексуммы вычислены
echo.

REM Показываем содержимое checksum.sha256
echo    Содержимое checksum.sha256:
type checksum.sha256
echo.

REM ============================================================================
REM Шаг 7: Перемещение в папку release
REM ============================================================================

echo [7/7] 📁 Подготовка папки release...
echo.

REM Перемещаем все части архива и чексуммы в release
move /Y Signer.7z.* ..\release\ >nul
move /Y checksum.sha256 ..\release\ >nul

cd ..

REM Копируем дополнительные файлы для релиза
copy /Y "README.md" "release\README.md" >nul
copy /Y "docs\BUILD_AUTOUPDATE.md" "release\BUILD_AUTOUPDATE.md" >nul

REM Создаем release notes если их нет
if not exist "docs\release_notes.txt" (
    echo Signer PRIME v%VERSION% > docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo Изменения в этой версии: >> docs\release_notes.txt
    echo - Реорганизована структура проекта >> docs\release_notes.txt
    echo - Улучшена стабильность приложения >> docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo Системные требования: >> docs\release_notes.txt
    echo - Windows 10/11 ^(64-bit^) >> docs\release_notes.txt
    echo - 8+ GB RAM >> docs\release_notes.txt
    echo - 5+ GB свободного места на диске >> docs\release_notes.txt
)
copy /Y "docs\release_notes.txt" "release\release_notes.txt" >nul

echo ✅ Все файлы подготовлены в папке release\
echo.

REM ============================================================================
REM Финальная информация
REM ============================================================================

echo ════════════════════════════════════════════════════════════════
echo   ✅ Сборка релиза завершена успешно!
echo ════════════════════════════════════════════════════════════════
echo.
echo 📦 Версия: %VERSION%
echo.
echo 📁 Файлы для загрузки на GitHub Release находятся в:
echo    release\
echo.
echo 📋 Содержимое:
dir /b release\
echo.
echo ═══════════════════════════════════════════════════════════════
echo   Следующие шаги:
echo ═══════════════════════════════════════════════════════════════
echo.
echo 1. Создайте новый релиз на GitHub:
echo    https://github.com/YOUR_USERNAME/YOUR_REPO/releases/new
echo.
echo 2. Укажите тег версии: v%VERSION%
echo.
echo 3. Загрузите ВСЕ файлы из папки release\:
echo    - Signer.7z.001, Signer.7z.002, ... (все части)
echo    - checksum.sha256
echo    - README.md
echo    - BUILD_AUTOUPDATE.md
echo    - release_notes.txt
echo.
echo 4. Опубликуйте release
echo.
echo 💡 Для автоматической загрузки используйте:
echo    upload_release.ps1 (PowerShell скрипт с GitHub CLI)
echo.
echo ════════════════════════════════════════════════════════════════
echo.

pause
