@echo off
chcp 65001 >nul
echo.
echo ================================================================
echo   Git Commit and Push - Production Bugfixes
echo ================================================================
echo.

echo [1/2] Creating commit...
git commit -m "fix: production bugfixes (tasks 1-5)" ^
-m "TASK 1: Fixed dev key check - corrected DEV_KEY_SHA256, added tests" ^
-m "TASK 2: Added build_config.json support for license_server_url" ^
-m "TASK 3: Added internal plan to license CLI" ^
-m "TASK 4: Stripe Price IDs via environment variables" ^
-m "TASK 5: Verified CORS warnings" ^
-m "" ^
-m "Changed: 12 files (6 client + 6 server)" ^
-m "Created: 10 files (config, tests, docs)" ^
-m "Status: Ready for production after configuration"

if errorlevel 1 (
    echo.
    echo ❌ ОШИБКА: Не удалось создать коммит
    pause
    exit /b 1
)

echo ✅ Коммит создан
echo.

echo [2/2] Pushing to remote...
git push

if errorlevel 1 (
    echo.
    echo ❌ ОШИБКА: Не удалось выполнить push
    echo.
    echo Возможные причины:
    echo - Нет доступа к удалённому репозиторию
    echo - Нужна авторизация
    echo - Конфликт с удалённой веткой
    echo.
    echo Попробуйте выполнить push вручную:
    echo   git push
    echo.
    pause
    exit /b 1
)

echo ✅ Push выполнен успешно
echo.
echo ================================================================
echo   Готово!
echo ================================================================
echo.
echo Изменения отправлены в удалённый репозиторий.
echo.

pause
