@echo off
chcp 65001 >nul
REM ============================================================================
REM Подготовка релиза Signer PRIME
REM Собирает приложение и создаёт архив для GitHub Release
REM ============================================================================

setlocal enabledelayedexpansion

echo.
echo ════════════════════════════════════════════════════════════════
echo   📦 Подготовка релиза Signer PRIME
echo ════════════════════════════════════════════════════════════════
echo.

REM Получение версии
for /f "tokens=2 delims=:, " %%a in ('type version.json ^| findstr "version"') do (
    set VERSION=%%~a
)
echo Версия: %VERSION%
echo.

REM ============================================================================
REM Проверка зависимостей
REM ============================================================================

echo [1/5] Проверка зависимостей...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ Python не найден
    pause
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ❌ PyInstaller не установлен (pip install pyinstaller)
    pause
    exit /b 1
)

if not exist "installer\7z.exe" (
    echo ❌ 7z.exe не найден в installer\
    echo    Скачайте: https://www.7-zip.org/
    pause
    exit /b 1
)

echo ✅ Все зависимости в порядке
echo.

REM ============================================================================
REM Очистка
REM ============================================================================

echo [2/5] Очистка старых сборок...
rmdir /s /q "dist\Signer" 2>nul
rmdir /s /q "dist\Updater" 2>nul
rmdir /s /q "build" 2>nul
rmdir /s /q "release" 2>nul
echo ✅ Очистка завершена
echo.

REM ============================================================================
REM Сборка
REM ============================================================================

echo [3/5] Сборка приложения...
echo.

echo    - Сборка Signer.exe...
pyinstaller signer.spec --noconfirm
if errorlevel 1 (
    echo ❌ Ошибка сборки Signer.exe
    pause
    exit /b 1
)

echo    - Сборка Updater.exe...
pyinstaller updater.spec --noconfirm
if errorlevel 1 (
    echo ❌ Ошибка сборки Updater.exe
    pause
    exit /b 1
)

echo    - Копирование файлов...
copy /Y "dist\Updater\Updater.exe" "dist\Signer\Updater.exe" >nul
copy /Y "installer\7z.exe" "dist\Signer\7z.exe" >nul
copy /Y "installer\7z.dll" "dist\Signer\7z.dll" >nul
copy /Y "version.json" "dist\Signer\version.json" >nul

echo ✅ Сборка завершена
echo.

REM ============================================================================
REM Создание архива
REM ============================================================================

echo [4/5] Создание архива...
echo.

mkdir release 2>nul
cd dist

REM Удаляем старые архивы
del /q Signer.7z.* 2>nul

REM Создаём многотомный архив (100MB части)
..\installer\7z.exe a -v100m -mx=5 Signer.7z Signer\* -xr!*.pyc -xr!__pycache__
if errorlevel 1 (
    echo ❌ Ошибка создания архива
    cd ..
    pause
    exit /b 1
)

echo ✅ Архив создан
echo.

REM ============================================================================
REM Вычисление чексумм
REM ============================================================================

echo [5/5] Вычисление SHA-256 чексумм...
echo.

del /q checksum.sha256 2>nul

for %%f in (Signer.7z.*) do (
    echo    %%f...
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

REM ============================================================================
REM Подготовка release/
REM ============================================================================

echo Перемещение файлов в release\...
move /Y Signer.7z.* ..\release\ >nul
move /Y checksum.sha256 ..\release\ >nul

cd ..

REM Копируем дополнительные файлы
copy /Y "README.md" "release\README.md" >nul
copy /Y "docs\BUILD_AUTOUPDATE.md" "release\BUILD_AUTOUPDATE.md" >nul

REM Создаём release notes если их нет
if not exist "docs\release_notes.txt" (
    echo Signer PRIME v%VERSION% > docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo Изменения в этой версии: >> docs\release_notes.txt
    echo - Оптимизирована структура проекта >> docs\release_notes.txt
    echo - Упрощены скрипты сборки >> docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo Системные требования: >> docs\release_notes.txt
    echo - Windows 10/11 ^(64-bit^) >> docs\release_notes.txt
    echo - 8+ GB RAM >> docs\release_notes.txt
    echo - 5+ GB свободного места на диске >> docs\release_notes.txt
)
copy /Y "docs\release_notes.txt" "release\release_notes.txt" >nul

echo ✅ Файлы подготовлены
echo.

REM ============================================================================
REM Финальная информация
REM ============================================================================

echo ════════════════════════════════════════════════════════════════
echo   ✅ Релиз готов!
echo ════════════════════════════════════════════════════════════════
echo.
echo 📦 Версия: %VERSION%
echo 📁 Файлы в: release\
echo.
echo Содержимое:
dir /b release\
echo.
echo ════════════════════════════════════════════════════════════════
echo   Следующие шаги:
echo ════════════════════════════════════════════════════════════════
echo.
echo 1. Проверьте файлы в release\
echo.
echo 2. Загрузите на GitHub:
echo    .\scripts\build\upload_release.ps1
echo.
echo    Или вручную:
echo    https://github.com/YOUR_REPO/releases/new
echo    - Тег: v%VERSION%
echo    - Загрузите ВСЕ файлы из release\
echo.
echo ════════════════════════════════════════════════════════════════
echo.

pause
