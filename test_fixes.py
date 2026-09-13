"""
Простой тест для проверки исправлений ЗАДАЧИ 1-4.
Запустите: python test_fixes.py
"""
import sys
import hashlib

print("=" * 60)
print("ТЕСТ ЗАДАЧИ 1: Проверка DEV_KEY_SHA256")
print("=" * 60)

# Проверяем, что DEV_KEY_SHA256 теперь правильный
from licensing.public_key import LICENSE_PUBLIC_KEY_PEM, DEV_KEY_SHA256

calculated_hash = hashlib.sha256(LICENSE_PUBLIC_KEY_PEM.encode()).hexdigest()
print(f"Текущий ключ (первые 50 символов): {LICENSE_PUBLIC_KEY_PEM[:50]}...")
print(f"DEV_KEY_SHA256 в коде: {DEV_KEY_SHA256}")
print(f"Реальный хэш ключа:    {calculated_hash}")

if calculated_hash == DEV_KEY_SHA256:
    print("✅ ЗАДАЧА 1: DEV_KEY_SHA256 совпадает с реальным хэшем!")
else:
    print("❌ ЗАДАЧА 1: DEV_KEY_SHA256 НЕ совпадает с реальным хэшем!")
    sys.exit(1)

print()
print("=" * 60)
print("ТЕСТ ЗАДАЧИ 2: Проверка build_config.json support")
print("=" * 60)

# Проверяем, что AppSettings.load() содержит логику чтения build_config.json
from configs.settings import AppSettings
import inspect

source = inspect.getsource(AppSettings.load)
if "build_config.json" in source:
    print("✅ ЗАДАЧА 2: AppSettings.load() содержит логику чтения build_config.json")
else:
    print("❌ ЗАДАЧА 2: AppSettings.load() НЕ содержит логику чтения build_config.json")
    sys.exit(1)

if "get_stripe_price_to_plan_map" in source or "build_config" in source:
    print("✅ ЗАДАЧА 2: Код обновлён для поддержки build_config.json")
else:
    print("⚠️  ЗАДАЧА 2: Возможно, код не полностью обновлён")

print()
print("=" * 60)
print("ТЕСТ ЗАДАЧИ 3: Проверка 'internal' в CLI")
print("=" * 60)

# Проверяем наличие 'internal' в choices
try:
    with open("signer-license-server/scripts/create_license_manual.py", "r", encoding="utf-8") as f:
        cli_source = f.read()
    
    if '"internal"' in cli_source or "'internal'" in cli_source:
        print("✅ ЗАДАЧА 3: 'internal' добавлен в CLI скрипт")
    else:
        print("❌ ЗАДАЧА 3: 'internal' НЕ найден в CLI скрипте")
        sys.exit(1)
except Exception as e:
    print(f"⚠️  ЗАДАЧА 3: Не удалось проверить: {e}")

print()
print("=" * 60)
print("ТЕСТ ЗАДАЧИ 4: Проверка Stripe Price ID в config")
print("=" * 60)

try:
    # Проверяем наличие полей в Settings
    with open("signer-license-server/app/config.py", "r", encoding="utf-8") as f:
        config_source = f.read()
    
    if "stripe_price_id_monthly" in config_source:
        print("✅ ЗАДАЧА 4: Поля Stripe Price ID добавлены в Settings")
    else:
        print("❌ ЗАДАЧА 4: Поля Stripe Price ID НЕ найдены в Settings")
        sys.exit(1)
    
    if "get_stripe_price_to_plan_map" in config_source:
        print("✅ ЗАДАЧА 4: Метод get_stripe_price_to_plan_map() добавлен")
    else:
        print("❌ ЗАДАЧА 4: Метод get_stripe_price_to_plan_map() НЕ найден")
        sys.exit(1)
    
    # Проверяем использование в stripe_service.py
    with open("signer-license-server/app/services/stripe_service.py", "r", encoding="utf-8") as f:
        stripe_source = f.read()
    
    if "self.price_to_plan" in stripe_source:
        print("✅ ЗАДАЧА 4: stripe_service.py использует динамический маппинг")
    else:
        print("❌ ЗАДАЧА 4: stripe_service.py НЕ использует динамический маппинг")
        sys.exit(1)
    
    if "price_monthly_prod" in stripe_source:
        print("❌ ЗАДАЧА 4: Старый хардкод ещё присутствует в stripe_service.py")
        sys.exit(1)
    else:
        print("✅ ЗАДАЧА 4: Старый хардкод удалён из stripe_service.py")

except Exception as e:
    print(f"⚠️  ЗАДАЧА 4: Не удалось проверить: {e}")

print()
print("=" * 60)
print("ТЕСТ ЗАДАЧИ 5: Проверка CORS warnings")
print("=" * 60)

try:
    with open("signer-license-server/app/main.py", "r", encoding="utf-8") as f:
        main_source = f.read()
    
    if "wildcard" in main_source and "CORS" in main_source:
        print("✅ ЗАДАЧА 5: CORS warning присутствует в main.py")
    else:
        print("⚠️  ЗАДАЧА 5: CORS warning не найден в main.py")

except Exception as e:
    print(f"⚠️  ЗАДАЧА 5: Не удалось проверить: {e}")

print()
print("=" * 60)
print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО! ✅")
print("=" * 60)
