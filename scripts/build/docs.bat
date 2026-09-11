@echo off
chcp 65001 >nul
REM ============================================================================
REM Просмотр документации по сборке Signer PRIME
REM ============================================================================

:menu
cls
echo.
echo ════════════════════════════════════════════════════════════════
echo   📚 Документация по сборке Signer PRIME
echo ════════════════════════════════════════════════════════════════
echo.
echo   Выберите документ для просмотра:
echo.
echo   [1] 📄 Шпаргалка (CHEATSHEET.txt)
echo       └─ Быстрая справка по командам
echo.
echo   [2] 🚀 Краткое руководство (QUICK_RELEASE_GUIDE.md)
echo       └─ Пошаговые инструкции по релизу
echo.
echo   [3] 📖 Полная документация (SCRIPTS_README.md)
echo       └─ Детальное описание всех скриптов
echo.
echo   [4] 🔄 Workflow диаграмма (WORKFLOW_DIAGRAM.md)
echo       └─ Визуальная схема процесса сборки
echo.
echo   [5] ✅ Инструкция по установке (SETUP_COMPLETE.txt)
echo       └─ Что установлено и как использовать
echo.
echo   [6] 📋 Основной README (README.md)
echo       └─ Общая информация о проекте
echo.
echo   [0] ❌ Выход
echo.
echo ════════════════════════════════════════════════════════════════
echo.

set /p choice="Ваш выбор (0-6): "

if "%choice%"=="1" goto cheatsheet
if "%choice%"=="2" goto quick_guide
if "%choice%"=="3" goto full_docs
if "%choice%"=="4" goto workflow
if "%choice%"=="5" goto setup
if "%choice%"=="6" goto readme
if "%choice%"=="0" goto end

echo.
echo ❌ Неверный выбор. Попробуйте еще раз.
timeout /t 2 >nul
goto menu

:cheatsheet
cls
type CHEATSHEET.txt
echo.
echo.
pause
goto menu

:quick_guide
cls
echo Открытие в браузере/редакторе...
start QUICK_RELEASE_GUIDE.md
timeout /t 1 >nul
goto menu

:full_docs
cls
echo Открытие в браузере/редакторе...
start SCRIPTS_README.md
timeout /t 1 >nul
goto menu

:workflow
cls
echo Открытие в браузере/редакторе...
start WORKFLOW_DIAGRAM.md
timeout /t 1 >nul
goto menu

:setup
cls
type SETUP_COMPLETE.txt
echo.
echo.
pause
goto menu

:readme
cls
echo Открытие в браузере/редакторе...
start README.md
timeout /t 1 >nul
goto menu

:end
echo.
echo 👋 До встречи!
echo.
timeout /t 1 >nul
