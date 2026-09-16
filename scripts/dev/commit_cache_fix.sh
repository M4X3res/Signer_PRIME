#!/bin/bash
# Скрипт для коммита всех исправлений CACHE_FIX.md

echo "=== CACHE_FIX.md - Все исправления ==="
echo ""

# Проверяем статус
git status

echo ""
echo "=== Добавляем изменённые файлы ==="

# БАГ 1: RefreshWorker GC
git add licensing/license_manager.py

# БАГ 2: backed_up_files scope
git add updater/updater_main.py

# БАГ 3: Server signature verification
git add signer-license-server/app/crypto.py
git add signer-license-server/app/services/license_service.py
git add signer-license-server/app/routes/license.py
git add signer-license-server/app/schemas.py
git add licensing/license_client.py

# БАГ 4: text_muted token
git add ui/widgets/settings_page.py

# БАГ 5: PyArmor runtime glob
git add signer.spec

# БАГ 6: Duplicate signal connections
git add main.py

# Тесты и документация
git add tests/test_cache_fix_regressions.py
git add docs/CACHE_FIX_REPORT.md
git add docs/CACHE_FIX_FILES.txt

echo ""
echo "=== Коммитим изменения ==="
git commit -m "Fix: CACHE_FIX.md - 6 критических багов исправлены

БАГ 1: RefreshWorker GC protection
- Добавлено хранилище _refresh_workers для предотвращения GC QThread

БАГ 2: backed_up_files scope в updater
- Перемещена инициализация перед try блоком для корректного роллбека

БАГ 3: Server signature verification (SECURITY)
- Добавлена verify_token_signature() для проверки Ed25519 подписей
- deactivate_device теперь требует fingerprint_hash
- Клиент обновлён для передачи fingerprint

БАГ 4: text_muted token
- Заменены ссылки на несуществующий text_muted → text_secondary

БАГ 5: PyArmor runtime glob
- Рекурсивный поиск pyarmor_runtime_* с дедупликацией

БАГ 6: Duplicate signal connections
- Использован Qt.ConnectionType.UniqueConnection в main.py

Добавлены регрессионные тесты: tests/test_cache_fix_regressions.py"

echo ""
echo "=== Готово! ==="
