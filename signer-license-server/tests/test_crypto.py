"""
tests/test_crypto.py

Юнит-тесты криптографических функций без HTTP-слоя.
"""
import re
import json
import base64
import pytest
from cryptography.hazmat.primitives.asymmetric import ed25519
from cryptography.hazmat.primitives import serialization

from app.crypto import sign_token, generate_license_key, parse_token


def test_generate_license_key_format():
    """Проверка формата генерируемых ключей."""
    key = generate_license_key()
    
    # Формат: SGNR-XXXX-XXXX-XXXX-XXXX
    assert re.match(r'^SGNR-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}-[A-Z2-9]{4}$', key)
    
    # Длина должна быть 24 символа (включая дефисы)
    assert len(key) == 24


def test_generate_license_key_no_confusing_chars():
    """Проверка отсутствия похожих символов O/0/I/1/L."""
    confusing_chars = set('OI1L0')
    
    for _ in range(100):
        key = generate_license_key()
        key_chars = set(key.replace('SGNR-', '').replace('-', ''))
        
        # Не должно быть пересечений с запрещёнными символами
        assert len(key_chars & confusing_chars) == 0


def test_generate_license_key_uniqueness():
    """Проверка уникальности генерируемых ключей."""
    keys = set()
    
    for _ in range(1000):
        key = generate_license_key()
        assert key not in keys
        keys.add(key)


def test_sign_token_format():
    """Проверка формата подписанного токена."""
    # Генерация тестового ключа
    private_key = ed25519.Ed25519PrivateKey.generate()
    
    payload = {
        "license_key": "SGNR-TEST-TEST-TEST-TEST",
        "device_id": "123e4567-e89b-12d3-a456-426614174000",
        "plan": "monthly"
    }
    
    token = sign_token(payload, private_key)
    
    # Формат: base64url(payload).base64url(signature)
    parts = token.split('.')
    assert len(parts) == 2
    
    # Обе части должны быть валидным base64url (без padding)
    assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in parts[0])
    assert all(c in 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_' for c in parts[1])


def test_sign_token_signature_verification():
    """Проверка корректности подписи токена."""
    # Генерация тестового ключа
    private_key = ed25519.Ed25519PrivateKey.generate()
    public_key = private_key.public_key()
    
    payload = {
        "license_key": "SGNR-TEST-TEST-TEST-TEST",
        "device_id": "123e4567-e89b-12d3-a456-426614174000",
        "plan": "monthly"
    }
    
    token = sign_token(payload, private_key)
    
    # Распарсить токен
    parts = token.split('.')
    payload_b64 = parts[0]
    signature_b64 = parts[1]
    
    # Декодировать
    padding = 4 - (len(payload_b64) % 4)
    if padding != 4:
        payload_b64 += '=' * padding
    payload_bytes = base64.urlsafe_b64decode(payload_b64)
    
    padding = 4 - (len(signature_b64) % 4)
    if padding != 4:
        signature_b64 += '=' * padding
    signature_bytes = base64.urlsafe_b64decode(signature_b64)
    
    # Проверить подпись
    try:
        public_key.verify(signature_bytes, payload_bytes)
    except Exception as e:
        pytest.fail(f"Signature verification failed: {e}")


def test_sign_token_payload_stability():
    """Проверка стабильности сериализации payload (sort_keys)."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    
    # Два payload с одинаковыми данными, но в разном порядке
    payload1 = {"a": 1, "b": 2, "c": 3}
    payload2 = {"c": 3, "a": 1, "b": 2}
    
    token1 = sign_token(payload1, private_key)
    token2 = sign_token(payload2, private_key)
    
    # Payload части должны быть идентичны (благодаря sort_keys)
    payload1_b64 = token1.split('.')[0]
    payload2_b64 = token2.split('.')[0]
    
    assert payload1_b64 == payload2_b64


def test_parse_token_valid():
    """Проверка парсинга валидного токена."""
    private_key = ed25519.Ed25519PrivateKey.generate()
    
    payload = {
        "license_key": "SGNR-TEST-TEST-TEST-TEST",
        "device_id": "123e4567-e89b-12d3-a456-426614174000",
        "plan": "monthly"
    }
    
    token = sign_token(payload, private_key)
    
    success, parsed_payload, error = parse_token(token)
    
    assert success is True
    assert error is None
    assert parsed_payload == payload


def test_parse_token_invalid_format_no_dot():
    """Проверка обработки токена без точки."""
    success, parsed_payload, error = parse_token("invalid_token_no_dot")
    
    assert success is False
    assert parsed_payload is None
    assert "Invalid token format" in error


def test_parse_token_invalid_format_too_many_parts():
    """Проверка обработки токена с лишними частями."""
    success, parsed_payload, error = parse_token("part1.part2.part3")
    
    assert success is False
    assert parsed_payload is None
    assert "Invalid token format" in error


def test_parse_token_invalid_base64():
    """Проверка обработки битого base64."""
    success, parsed_payload, error = parse_token("!!!invalid_base64!!!.abc123")
    
    assert success is False
    assert parsed_payload is None
    assert "Token parse error" in error


def test_parse_token_invalid_json():
    """Проверка обработки битого JSON в payload."""
    # Создаём валидный base64, но с невалидным JSON внутри
    invalid_json = b"not a json"
    payload_b64 = base64.urlsafe_b64encode(invalid_json).decode().rstrip('=')
    
    token = f"{payload_b64}.fake_signature"
    
    success, parsed_payload, error = parse_token(token)
    
    assert success is False
    assert parsed_payload is None
    assert "Token parse error" in error


def test_parse_token_empty_string():
    """Проверка обработки пустой строки."""
    success, parsed_payload, error = parse_token("")
    
    assert success is False
    assert parsed_payload is None
    assert error is not None
