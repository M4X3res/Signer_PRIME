@echo off
REM ============================================================================
REM Скрипт автоматической сборки Signer PRIME с системой автообновлений
REM ============================================================================

echo.
echo ===============================================
echo   Сборка Signer PRIME с автообновлением
echo ===============================================
echo.

REM Проверка наличия 7z.exe и 7z.dll
if not exist "installer\7z.exe" (
    echo [ОШИБКА] 7z.exe не найден в installer\
    echo.
    echo Скачайте 7-Zip:
    echo https://www.7-zip.org/download.html
    echo.
    echo Поместите 7z.exe и 7z.dll из установки 7-Zip в installer\ и повторите сборку.
    pause
    exit /b 1
)

if not exist "installer\7z.dll" (
    echo [ОШИБКА] 7z.dll не найден в installer\
    echo.
    echo Скачайте 7-Zip:
    echo https://www.7-zip.org/download.html
    echo.
    echo Поместите 7z.exe и 7z.dll из установки 7-Zip в installer\ и повторите сборку.
    pause
    exit /b 1
)

echo [OK] 7z.exe и 7z.dll найдены
echo.

REM Шаг 1: Сборка основного приложения
echo ===============================================
echo [1/3] Сборка Signer.exe...
echo ===============================================
pyinstaller signer.spec --noconfirm
if errorlevel 1 (
    echo [ОШИБКА] Сборка Signer.exe провалена
    pause
    exit /b 1
)
echo [OK] Signer.exe собран
echo.

REM Шаг 2: Сборка Updater
echo ===============================================
echo [2/3] Сборка Updater.exe...
echo ===============================================
pyinstaller updater.spec --noconfirm
if errorlevel 1 (
    echo [ОШИБКА] Сборка Updater.exe провалена
    pause
    exit /b 1
)
echo [OK] Updater.exe собран
echo.

REM Шаг 3: Копирование файлов
echo ===============================================
echo [3/3] Копирование файлов...
echo ===============================================

copy /Y "dist\Updater\Updater.exe" "dist\Signer\Updater.exe"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось скопировать Updater.exe
    pause
    exit /b 1
)
echo [OK] Updater.exe скопирован

copy /Y "installer\7z.exe" "dist\Signer\7z.exe"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось скопировать 7z.exe
    pause
    exit /b 1
)
echo [OK] 7z.exe скопирован

copy /Y "installer\7z.dll" "dist\Signer\7z.dll"
if errorlevel 1 (
    echo [ОШИБКА] Не удалось скопировать 7z.dll
    pause
    exit /b 1
)
echo [OK] 7z.dll скопирован
echo.

REM Финальное сообщение
echo ===============================================
echo   Сборка завершена успешно!
echo ===============================================
echo.
echo Результат: dist\Signer\
echo.
echo Для создания релиза:
echo   1. cd dist
echo   2. 7z a -v100m -mx=5 Signer.7z Signer\*
echo   3. Вычислите чексуммы (см. BUILD_AUTOUPDATE.md)
echo   4. Загрузите на GitHub Releases
echo.
pause
