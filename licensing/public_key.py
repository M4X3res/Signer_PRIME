"""
licensing/public_key.py
Публичный Ed25519-ключ для верификации токенов лицензии.
Приватный ключ хранится ТОЛЬКО на сервере лицензий.
"""
import base64
import json
from typing import Tuple, Optional

try:
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    from cryptography.hazmat.primitives import serialization
    from cryptography.exceptions import InvalidSignature
    CRYPTO_AVAILABLE = True
except ImportError:
    CRYPTO_AVAILABLE = False


# ════════════════════════════════════════════════════════════════
# Публичный ключ Ed25519 (base64 PEM)
# ════════════════════════════════════════════════════════════════
# ВАЖНО: Этот ключ НЕ ЯВЛЯЕТСЯ СЕКРЕТОМ.
# Генерируется на сервере один раз, приватная часть остаётся на сервере.
# Это временный ключ для разработки. Для продакшна будет сгенерирован новый.
# ════════════════════════════════════════════════════════════════

LICENSE_PUBLIC_KEY_PEM = """-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAGb9ECWmEzf9RzJZTQwKMmCIl8q0QMCPZ3fVXwXf6Jxs=
-----END PUBLIC KEY-----"""


def verify_token(token_str: str) -> Tuple[bool, Optional[dict], Optional[str]]:
    """
    Верифицировать токен лицензии.
    
    Формат токена: base64url(payload) + "." + base64url(signature)
    где payload = JSON с полями {license_key, device_id, plan, status, current_period_end, issued_at}
    
    Args:
        token_str: токен в формате "payload.signature"
    
    Returns:
        Tuple[valid, payload_dict, error_message]
        - valid: True если подпись корректна
        - payload_dict: распакованный JSON payload (если валиден)
        - error_message: описание ошибки (если не валиден)
    """
    if not CRYPTO_AVAILABLE:
        return False, None, "cryptography library not installed"
    
    try:
        # Разделяем токен на payload и signature
        parts = token_str.split(".")
        if len(parts) != 2:
            return False, None, "Invalid token format (expected payload.signature)"
        
        payload_b64, signature_b64 = parts
        
        # Декодируем payload (base64url -> bytes)
        payload_bytes = _base64url_decode(payload_b64)
        signature_bytes = _base64url_decode(signature_b64)
        
        # Парсим payload как JSON
        try:
            payload_dict = json.loads(payload_bytes.decode('utf-8'))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            return False, None, f"Invalid payload JSON: {e}"
        
        # Загружаем публичный ключ
        public_key = serialization.load_pem_public_key(LICENSE_PUBLIC_KEY_PEM.encode())
        if not isinstance(public_key, Ed25519PublicKey):
            return False, None, "Invalid public key type (expected Ed25519)"
        
        # Верифицируем подпись
        try:
            public_key.verify(signature_bytes, payload_bytes)
            return True, payload_dict, None
        except InvalidSignature:
            return False, None, "Invalid signature"
    
    except Exception as e:
        return False, None, f"Token verification error: {e}"


def _base64url_decode(data: str) -> bytes:
    """Декодирует base64url (без padding) в bytes."""
    # Добавляем padding если нужен
    padding = 4 - (len(data) % 4)
    if padding != 4:
        data += '=' * padding
    
    # base64url использует - и _ вместо + и /
    data = data.replace('-', '+').replace('_', '/')
    return base64.b64decode(data)


def generate_keypair() -> Tuple[str, str]:
    """
    Генерирует пару ключей Ed25519 (для сервера).
    
    Эта функция НЕ используется клиентом, только для справки.
    Реальная генерация ключей происходит на сервере лицензий.
    
    Returns:
        Tuple[private_key_pem, public_key_pem]
    """
    if not CRYPTO_AVAILABLE:
        raise ImportError("cryptography library not installed")
    
    from cryptography.hazmat.primitives.asymmetric import ed25519
    
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ).decode('utf-8')
    
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode('utf-8')
    
    return private_pem, public_pem


if __name__ == "__main__":
    # Тест: генерация и верификация
    print("[Test] Generating Ed25519 keypair...")
    private_pem, public_pem = generate_keypair()
    print("Private key (KEEP SECRET ON SERVER):")
    print(private_pem)
    print("\nPublic key (EMBED IN CLIENT):")
    print(public_pem)
    
    # Тест подписи
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    test_payload = json.dumps({
        "license_key": "SGNR-TEST-TEST-TEST-TEST",
        "device_id": "test-device-123",
        "plan": "monthly",
        "status": "active",
        "current_period_end": 1735689600,
        "issued_at": 1735603200
    }, sort_keys=True).encode()
    
    private_key = serialization.load_pem_private_key(private_pem.encode(), password=None)
    signature = private_key.sign(test_payload)
    
    payload_b64 = base64.urlsafe_b64encode(test_payload).decode().rstrip('=')
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    test_token = f"{payload_b64}.{signature_b64}"
    
    print(f"\n[Test] Token: {test_token[:80]}...")
    
    # Подменяем публичный ключ для теста
    import licensing.public_key
    licensing.public_key.LICENSE_PUBLIC_KEY_PEM = public_pem
    
    valid, payload, error = verify_token(test_token)
    print(f"\n[Test] Verification result: valid={valid}, payload={payload}, error={error}")
