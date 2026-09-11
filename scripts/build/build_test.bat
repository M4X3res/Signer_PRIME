@echo off
chcp 65001 >nul
REM ============================================================================
REM Быстрая тестовая сборка без архивации (для локального тестирования)
REM ============================================================================

echo.
echo ════════════════════════════════════════════════════════════════
echo   ⚡ Быстрая тестовая сборка Signer PRIME
echo ════════════════════════════════════════════════════════════════
echo.

REM Получение версии
for /f "tokens=2 delims=:, " %%a in ('type version.json ^| findstr "version"') do (
    set VERSION=%%~a
)
echo 📦 Версия: %VERSION%
echo.

REM ============================================================================
REM Шаг 1: Сборка основного приложения
REM ============================================================================

echo [1/3] 🔨 Сборка Signer.exe...
pyinstaller signer.spec --noconfirm
if errorlevel 1 (
    echo ❌ Ошибка сборки Signer.exe
    pause
    exit /b 1
)
echo ✅ Signer.exe собран
echo.

REM ============================================================================
REM Шаг 2: Сборка Updater.exe
REM ============================================================================

echo [2/3] 🔨 Сборка Updater.exe...
pyinstaller updater.spec --noconfirm
if errorlevel 1 (
    echo ❌ Ошибка сборки Updater.exe
    pause
    exit /b 1
)
echo ✅ Updater.exe собран
echo.

REM ============================================================================
REM Шаг 3: Копирование файлов
REM ============================================================================

echo [3/3] 📋 Копирование файлов...

copy /Y "dist\Updater\Updater.exe" "dist\Signer\Updater.exe" >nul
echo    ✅ Updater.exe скопирован

copy /Y "installer\7z.exe" "dist\Signer\7z.exe" >nul
echo    ✅ 7z.exe скопирован

copy /Y "installer\7z.dll" "dist\Signer\7z.dll" >nul
echo    ✅ 7z.dll скопирован

copy /Y "version.json" "dist\Signer\version.json" >nul
echo    ✅ version.json скопирован

echo.
echo ════════════════════════════════════════════════════════════════
echo   ✅ Тестовая сборка завершена!
echo ════════════════════════════════════════════════════════════════
echo.
echo 📁 Результат: dist\Signer\Signer.exe
echo.
echo 🚀 Запуск приложения...
echo.

REM Запускаем приложение
cd dist\Signer
start Signer.exe
cd ..\..

echo.
echo 💡 Для полной сборки релиза используйте: build_release.bat
echo.
pause
