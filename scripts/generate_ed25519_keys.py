"""
Скрипт для генерации пары ключей Ed25519 для сервера лицензий.

Использование:
    python scripts/generate_ed25519_keys.py

Результат:
    - Приватный ключ (хранить в Secret Manager, НИКОГДА в коде)
    - Публичный ключ (вставить в licensing/public_key.py)
"""
import sys
import os

# Проверяем наличие cryptography
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    from cryptography.hazmat.primitives import serialization
except ImportError:
    print("ERROR: cryptography library not installed")
    print("Install: pip install cryptography>=41.0.0")
    sys.exit(1)


def generate_keypair():
    """Генерирует пару ключей Ed25519."""
    print("=" * 70)
    print("Генерация пары ключей Ed25519 для сервера лицензий")
    print("=" * 70)
    print()
    
    # Генерация
    print("[1/3] Генерация ключей...")
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    print("      ✓ Ключи сгенерированы")
    
    # Экспорт приватного ключа
    print("\n[2/3] Экспорт приватного ключа...")
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    print("      ✓ Приватный ключ экспортирован")
    
    # Экспорт публичного ключа
    print("\n[3/3] Экспорт публичного ключа...")
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    print("      ✓ Публичный ключ экспортирован")
    
    # Вывод результатов
    print("\n" + "=" * 70)
    print("ПРИВАТНЫЙ КЛЮЧ (Secret Manager / переменная окружения сервера)")
    print("=" * 70)
    print("⚠️  КРИТИЧНО: НЕ КОММИТИТЬ В GIT, НЕ ПУБЛИКОВАТЬ!")
    print()
    print(private_pem)
    
    print("\n" + "=" * 70)
    print("ПУБЛИЧНЫЙ КЛЮЧ (licensing/public_key.py)")
    print("=" * 70)
    print("✓ Безопасно хранить в клиентском коде")
    print()
    print("Замените содержимое LICENSE_PUBLIC_KEY_PEM в licensing/public_key.py:")
    print()
    print('LICENSE_PUBLIC_KEY_PEM = """' + public_pem + '"""')
    
    print("\n" + "=" * 70)
    print("ИНСТРУКЦИИ")
    print("=" * 70)
    print()
    print("1. ПРИВАТНЫЙ КЛЮЧ:")
    print("   - Сохраните в Google Cloud Secret Manager")
    print("   - Или в переменной окружения ED25519_PRIVATE_KEY на сервере")
    print("   - НИКОГДА не храните в коде или репозитории")
    print()
    print("2. ПУБЛИЧНЫЙ КЛЮЧ:")
    print("   - Откройте файл: licensing/public_key.py")
    print("   - Найдите константу LICENSE_PUBLIC_KEY_PEM")
    print("   - Замените её содержимое на публичный ключ выше")
    print("   - Закоммитьте изменения")
    print()
    print("3. СЕРВЕР:")
    print("   - Используйте приватный ключ для подписи токенов")
    print("   - См. docs/LICENSE_SERVER.md для примеров кода")
    print()
    print("=" * 70)


if __name__ == "__main__":
    try:
        generate_keypair()
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
