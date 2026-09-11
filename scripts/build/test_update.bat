@echo off
REM Тестовый запуск с проверкой обновлений в dev-режиме

echo ================================================
echo   Тест автообновлений (dev-режим)
echo ================================================
echo.
echo Текущая версия в version.json:
type version.json
echo.
echo.
echo Для теста измените version.json на более старую версию (например 1.9.0)
echo Затем убедитесь что на GitHub есть релиз с более новой версией
echo.
pause

set SIGNER_FORCE_UPDATE_CHECK=1
.venv\Scripts\python.exe main.py

pause
