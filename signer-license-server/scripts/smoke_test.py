#!/usr/bin/env python3
"""
Smoke test для проверки готовности сервера к деплою.
Проверяет, что все модули импортируются без ошибок.
"""
import sys
import importlib

print("=" * 60)
print(" Signer License Server - Smoke Test")
print("=" * 60)
print()

modules_to_test = [
    "app.main",
    "app.config",
    "app.models",
    "app.schemas",
    "app.crypto",
    "app.db",
    "app.routes.license",
    "app.routes.admin",
    "app.routes.stripe_webhook",
    "app.services.license_service",
    "app.services.stripe_service",
]

failed = []

for module_name in modules_to_test:
    try:
        importlib.import_module(module_name)
        print(f"✅ {module_name}")
    except Exception as e:
        print(f"❌ {module_name}: {e}")
        failed.append(module_name)

print()
print("=" * 60)

if failed:
    print(f"❌ {len(failed)} modules failed to import:")
    for module in failed:
        print(f"   - {module}")
    print()
    print("Fix import errors before deploying.")
    sys.exit(1)
else:
    print("✅ All modules imported successfully!")
    print()
    print("Next steps:")
    print("  1. docker-compose -f docker-compose.dev.yml up")
    print("  2. pytest tests/ -v")
    print("  3. bash scripts/deploy_gcloud.sh")
    sys.exit(0)
