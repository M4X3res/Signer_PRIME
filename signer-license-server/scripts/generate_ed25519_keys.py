#!/usr/bin/env python3
"""
generate_ed25519_keys.py

Генератор пары Ed25519 ключей для production деплоя сервера лицензий.

ВАЖНО:
- Приватный ключ → Secret Manager (ED25519_PRIVATE_KEY_PEM)
- Публичный ключ → licensing/public_key.py в клиентском коде

Usage:
    python scripts/generate_ed25519_keys.py
"""
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization


def generate_keypair():
    """Генерация новой пары Ed25519 ключей."""
    
    print("=" * 70)
    print(" Ed25519 Key Pair Generator")
    print(" Signer PRIME License Server")
    print("=" * 70)
    print()
    
    # Генерация ключей
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    # Сериализация в PEM
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode()
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    
    # Вывод приватного ключа
    print("┌" + "─" * 68 + "┐")
    print("│ ПРИВАТНЫЙ КЛЮЧ (ED25519_PRIVATE_KEY_PEM)                         │")
    print("│ ⚠️  СЕКРЕТ! Сохраните в Google Secret Manager                    │")
    print("├" + "─" * 68 + "┤")
    print(private_pem)
    print("└" + "─" * 68 + "┘")
    print()
    
    # Вывод публичного ключа
    print("┌" + "─" * 68 + "┐")
    print("│ ПУБЛИЧНЫЙ КЛЮЧ (licensing/public_key.py)                         │")
    print("│ ✅ Безопасно для коммита в репозиторий клиента                   │")
    print("├" + "─" * 68 + "┤")
    print(public_pem)
    print("└" + "─" * 68 + "┘")
    print()
    
    # Инструкции
    print("=" * 70)
    print(" Следующие шаги:")
    print("=" * 70)
    print()
    print("1. ПРИВАТНЫЙ КЛЮЧ:")
    print("   • Сохраните в Google Secret Manager:")
    print()
    print("     gcloud secrets create ed25519-private-key \\")
    print("       --data-file=<(echo \"$PRIVATE_KEY\") \\")
    print("       --project=YOUR_PROJECT")
    print()
    print("   • Дайте доступ Cloud Run сервису:")
    print()
    print("     gcloud secrets add-iam-policy-binding ed25519-private-key \\")
    print("       --member=serviceAccount:YOUR_SERVICE_ACCOUNT \\")
    print("       --role=roles/secretmanager.secretAccessor")
    print()
    print("2. ПУБЛИЧНЫЙ КЛЮЧ:")
    print("   • Замените содержимое файла licensing/public_key.py:")
    print()
    print('     LICENSE_PUBLIC_KEY_PEM = """')
    print(public_pem, end='')
    print('     """')
    print()
    print("=" * 70)
    print()
    print("⚠️  БЕЗОПАСНОСТЬ:")
    print("   • НЕ коммитьте приватный ключ в Git")
    print("   • НЕ храните в .env файлах в репозитории")
    print("   • Используйте только Secret Manager для production")
    print()


if __name__ == "__main__":
    generate_keypair()
