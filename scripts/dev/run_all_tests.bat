@echo off
chcp 65001 >nul
echo.
echo ================================================================
echo   Проверка исправлений перед релизом
echo ================================================================
echo.

echo [1/3] Быстрая проверка синтаксиса и логики...
python tests\test_fixes_manual.py
if errorlevel 1 (
    echo.
    echo ❌ ОШИБКА: Быстрая проверка не прошла
    pause
    exit /b 1
)

echo.
echo [2/3] Запуск клиентских тестов (tests/test_licensing.py)...
python -m pytest tests/test_licensing.py -v
if errorlevel 1 (
    echo.
    echo ❌ ОШИБКА: Клиентские тесты не прошли
    pause
    exit /b 1
)

echo.
echo [3/3] Запуск серверных тестов (signer-license-server/tests/)...
cd signer-license-server
python -m pytest tests/ -v
if errorlevel 1 (
    echo.
    echo ❌ ОШИБКА: Серверные тесты не прошли
    cd ..
    pause
    exit /b 1
)
cd ..

echo.
echo ================================================================
echo   ✅ ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!
echo ================================================================
echo.
echo Можно приступать к сборке релиза:
echo   1. Настроить build_config.json
echo   2. Запустить scripts\build\prepare_release.bat
echo.
pause
