# PRODUCTION BUGFIXES — QUICK REFERENCE

## Проверка исправлений

```bash
python test_fixes.py              # Быстрая проверка (30 сек)
run_all_tests.bat                 # Полные тесты (2-5 мин)
```

## Настройка перед релизом

```bash
# 1. Конфигурация license server URL
copy build_config.json.example build_config.json
notepad build_config.json  # → указать реальный URL сервера

# 2. Генерация production ключей
python signer-license-server/scripts/generate_ed25519_keys.py

# 3. Обновить licensing/public_key.py с новым публичным ключом

# 4. Пересчитать DEV_KEY_SHA256 (если это dev-ключ для тестов)
python -c "import hashlib; key = open('licensing/public_key.py').read().split('LICENSE_PUBLIC_KEY_PEM = \"\"\"')[1].split('\"\"\"')[0]; print(hashlib.sha256(key.encode()).hexdigest())"
```

## Сборка релиза

```bash
scripts\build\prepare_release.bat
```

Скрипт автоматически проверит:
- ✓ Наличие build_config.json
- ✓ Что URL не является заглушкой
- ✓ Все зависимости (Python, PyInstaller, 7z)

## Документация

- **BUGFIXES_README.md** — старт здесь (обзор)
- **SUMMARY.md** — краткое резюме
- **FIXES_REPORT.md** — полный отчёт
- **CHECKLIST.md** — чеклист проверки

## Что исправлено

- ✅ **ЗАДАЧА 1 (КРИТИЧНО)**: Dev-ключ проверка
- ✅ **ЗАДАЧА 2 (КРИТИЧНО)**: license_server_url конфигурация
- ✅ **ЗАДАЧА 3**: Internal-лицензии в CLI
- ✅ **ЗАДАЧА 4**: Stripe Price ID (динамический маппинг)
- ✅ **ЗАДАЧА 5**: CORS warnings (проверка)

## Важно

⚠ **build_config.json** добавлен в .gitignore (содержит production URL — не коммитить!)

⚠ **DEV_KEY_SHA256** пересчитан для текущего dev-ключа (при смене ключа — пересчитать заново)

⚠ **Stripe Price IDs** настраиваются через переменные окружения (не хардкодятся в коде)

---

**Выполнено:** 2026-09-13  
**Статус:** ✅ 100% готово к релизу (после настройки конфигурации)
