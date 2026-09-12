#!/usr/bin/env python3
"""
validate_structure.py
Финальная проверка, что все файлы из промпта созданы.
"""
import os
from pathlib import Path

# Ожидаемая структура из промпта
EXPECTED_FILES = {
    "app/main.py": "FastAPI app без MVP fallback",
    "app/config.py": "Pydantic Settings",
    "app/models.py": "SQLAlchemy модели",
    "app/schemas.py": "Pydantic схемы",
    "app/crypto.py": "Ed25519 подписи",
    "app/db.py": "Database setup",
    "app/routes/license.py": "License endpoints с rate limiting",
    "app/routes/admin.py": "Admin API",
    "app/routes/stripe_webhook.py": "Stripe webhook",
    "app/services/license_service.py": "SELECT FOR UPDATE",
    "app/services/stripe_service.py": "Stripe обработка",
    "migrations/env.py": "Alembic environment",
    "migrations/versions/001_initial_schema.py": "Начальная миграция + partial index",
    "tests/conftest.py": "Testcontainers фикстуры",
    "tests/test_routes_activate.py": "Тесты #1-5, #12",
    "tests/test_routes_refresh.py": "Тесты #6-8",
    "tests/test_race_condition.py": "Тест #9 (SELECT FOR UPDATE)",
    "tests/test_stripe_webhook.py": "Тест #10 (signature verification)",
    "tests/test_admin_api.py": "Admin API тесты",
    "tests/test_crypto.py": "Юнит-тесты криптографии",
    "tests/test_license_service.py": "Юнит-тесты LicenseService",
    "scripts/deploy_gcloud.sh": "GCP деплой (идемпотентный)",
    "scripts/create_license_manual.py": "CLI создание лицензий",
    "scripts/generate_ed25519_keys.py": "Генератор ключей",
    "scripts/local_dev_up.sh": "Dev startup",
    "scripts/validate_structure.py": "Валидация структуры",
    "docker/Dockerfile": "Multi-stage build",
    "docker/.dockerignore": "Исключение секретов",
    "docker-compose.dev.yml": "Dev окружение",
    "alembic.ini": "Alembic config",
    "requirements.txt": "Python зависимости",
    ".env.example": "Шаблон переменных",
    "README.md": "Полная документация",
    "STATUS.md": "Критерии приёмки",
    "CLIENT_INTEGRATION.md": "Инструкции интеграции с клиентом",
}

# Файлы, которые должны быть УДАЛЕНЫ
DELETED_FILES = [
    "100_PERCENT_DONE.md",
    "PROMPT_EXECUTION_REPORT.md",
    "TODO_FOR_AI.md",
    "FINAL_STATUS.md",
    "IMPLEMENTATION_REPORT.md",
    "IMPLEMENTATION_STATUS.md",
    "QUICKSTART.md",
    "COMPLETION_SUMMARY.md",
    "EXECUTION_COMPLETE.md",
    "CHANGELOG.md",
    "PRE_DEPLOYMENT_CHECKLIST.md",
    "ARCHITECTURE.md",
]

def main():
    print("=" * 70)
    print(" Signer License Server - Structure Validation")
    print("=" * 70)
    print()
    
    root = Path(".")
    if not (root / "app" / "main.py").exists():
        # Может быть запущен из родительской директории
        root = Path("signer-license-server")
    
    missing = []
    present = []
    
    print("Проверка обязательных файлов:")
    for file_path, description in EXPECTED_FILES.items():
        full_path = root / file_path
        if full_path.exists():
            print(f"✅ {file_path}")
            present.append(file_path)
        else:
            print(f"❌ {file_path} — отсутствует")
            missing.append(file_path)
    
    print()
    print("Проверка удалённых файлов:")
    still_present = []
    for file_path in DELETED_FILES:
        full_path = root / file_path
        if not full_path.exists():
            print(f"✅ {file_path} — удалён")
        else:
            print(f"❌ {file_path} — всё ещё существует")
            still_present.append(file_path)
    
    print()
    print("=" * 70)
    print(" Результаты:")
    print("=" * 70)
    print(f"Обязательных файлов: {len(present)}/{len(EXPECTED_FILES)}")
    print(f"Удалённых файлов: {len(DELETED_FILES) - len(still_present)}/{len(DELETED_FILES)}")
    print()
    
    if missing:
        print(f"❌ Отсутствуют {len(missing)} файлов:")
        for f in missing:
            print(f"   - {f}")
        print()
    
    if still_present:
        print(f"⚠️  {len(still_present)} устаревших файлов не удалены:")
        for f in still_present:
            print(f"   - {f}")
        print()
    
    if not missing and not still_present:
        print("✅ Структура проекта соответствует промпту!")
        print()
        print("Готово к:")
        print("  • docker-compose -f docker-compose.dev.yml up")
        print("  • pytest tests/ -v")
        print("  • bash scripts/deploy_gcloud.sh")
        return 0
    else:
        print("❌ Структура не полная. Завершите недостающие файлы.")
        return 1

if __name__ == "__main__":
    exit(main())
