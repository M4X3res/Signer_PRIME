@echo off
REM Скрипт для коммита всех исправлений CACHE_FIX.md

echo === CACHE_FIX.md - Все исправления ===
echo.

REM Проверяем статус
git status

echo.
echo === Добавляем изменённые файлы ===

REM БАГ 1: RefreshWorker GC
git add licensing/license_manager.py

REM БАГ 2: backed_up_files scope
git add updater/updater_main.py

REM БАГ 3: Server signature verification
git add signer-license-server/app/crypto.py
git add signer-license-server/app/services/license_service.py
git add signer-license-server/app/routes/license.py
git add signer-license-server/app/schemas.py
git add licensing/license_client.py

REM БАГ 4: text_muted token
git add ui/widgets/settings_page.py

REM БАГ 5: PyArmor runtime glob
git add signer.spec

REM БАГ 6: Duplicate signal connections
git add main.py

REM Тесты и документация
git add tests/test_cache_fix_regressions.py
git add docs/CACHE_FIX_REPORT.md
git add docs/CACHE_FIX_FILES.txt
git add commit_cache_fix.sh
git add commit_cache_fix.bat

echo.
echo === Коммитим изменения ===
git commit -m "Fix: CACHE_FIX.md - 6 критических багов исправлены" -m "" -m "БАГ 1: RefreshWorker GC protection" -m "- Добавлено хранилище _refresh_workers для предотвращения GC QThread" -m "" -m "БАГ 2: backed_up_files scope в updater" -m "- Перемещена инициализация перед try блоком для корректного роллбека" -m "" -m "БАГ 3: Server signature verification (SECURITY)" -m "- Добавлена verify_token_signature() для проверки Ed25519 подписей" -m "- deactivate_device теперь требует fingerprint_hash" -m "- Клиент обновлён для передачи fingerprint" -m "" -m "БАГ 4: text_muted token" -m "- Заменены ссылки на несуществующий text_muted на text_secondary" -m "" -m "БАГ 5: PyArmor runtime glob" -m "- Рекурсивный поиск pyarmor_runtime_* с дедупликацией" -m "" -m "БАГ 6: Duplicate signal connections" -m "- Использован Qt.ConnectionType.UniqueConnection в main.py" -m "" -m "Добавлены регрессионные тесты: tests/test_cache_fix_regressions.py"

echo.
echo === Готово! ===
pause
