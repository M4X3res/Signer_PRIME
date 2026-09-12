"""
app/crypto.py
Ed25519 криптография и генерация лицензионных ключей.
"""
import json
import base64
import secrets
import logging
from typing import Tuple
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

logger = logging.getLogger(__name__)

# Кэш для приватного ключа (загружается один раз при старте)
_private_key_cache: ed25519.Ed25519PrivateKey | None = None


def load_private_key(pem_data: str) -> ed25519.Ed25519PrivateKey:
    """Загрузить приватный ключ Ed25519 из PEM."""
    global _private_key_cache
    
    if _private_key_cache is None:
        _private_key_cache = serialization.load_pem_private_key(
            pem_data.encode(),
            password=None
        )
        if not isinstance(_private_key_cache, ed25519.Ed25519PrivateKey):
            raise ValueError("Invalid Ed25519 private key")
        logger.info("Ed25519 private key loaded")
    
    return _private_key_cache


def sign_token(payload: dict, private_key: ed25519.Ed25519PrivateKey) -> str:
    """
    Подписать payload и вернуть токен.
    
    Формат: base64url(payload).base64url(signature)
    """
    # Сериализуем payload (sort_keys для стабильности)
    payload_json = json.dumps(payload, sort_keys=True)
    payload_bytes = payload_json.encode()
    
    # Подписываем
    signature = private_key.sign(payload_bytes)
    
    # Кодируем в base64url без padding
    payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip('=')
    signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
    
    return f"{payload_b64}.{signature_b64}"


def generate_license_key() -> str:
    """
    Генерировать уникальный лицензионный ключ.
    
    Формат: SGNR-XXXX-XXXX-XXXX-XXXX
    Использует Crockford base32 без похожих символов (O/0/I/1/L).
    """
    # Алфавит base32 без похожих символов
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    
    # 16 байт случайных данных
    random_bytes = secrets.token_bytes(16)
    
    # Конвертируем в base32
    result = []
    for byte in random_bytes:
        result.append(alphabet[byte % len(alphabet)])
    
    # Форматируем: SGNR-XXXX-XXXX-XXXX-XXXX
    key_body = ''.join(result[:16])
    formatted = f"SGNR-{key_body[0:4]}-{key_body[4:8]}-{key_body[8:12]}-{key_body[12:16]}"
    
    return formatted


def parse_token(token_str: str) -> Tuple[bool, dict | None, str | None]:
    """
    Распарсить токен (без проверки подписи, только извлечь payload).
    
    Returns:
        (success, payload_dict, error_message)
    """
    try:
        parts = token_str.split(".")
        if len(parts) != 2:
            return False, None, "Invalid token format"
        
        payload_b64 = parts[0]
        
        # Добавляем padding если нужен
        padding = 4 - (len(payload_b64) % 4)
        if padding != 4:
            payload_b64 += '=' * padding
        
        # Декодируем
        payload_b64 = payload_b64.replace('-', '+').replace('_', '/')
        payload_bytes = base64.urlsafe_b64decode(payload_b64)
        
        # Парсим JSON
        payload_dict = json.loads(payload_bytes.decode('utf-8'))
        
        return True, payload_dict, None
    
    except Exception as e:
        return False, None, f"Token parse error: {e}"
