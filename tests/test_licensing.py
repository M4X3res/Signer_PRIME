"""
tests/test_licensing.py
Юнит-тесты системы лицензирования.
"""
import json
import os
import tempfile
import time
from pathlib import Path
from unittest.mock import Mock, patch
import unittest

# Мокаем requests перед импортом
import sys
sys.modules['requests'] = Mock()

from licensing.public_key import verify_token, generate_keypair
from licensing.device_fingerprint import get_device_fingerprint, get_device_label
from licensing.license_manager import LicenseManager, LicenseStatus
from licensing.license_client import LicenseClient, LicenseResponse


class TestPublicKey(unittest.TestCase):
    """Тесты верификации токенов (Ed25519)."""
    
    def setUp(self):
        """Генерируем тестовую пару ключей."""
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        
        # Генерируем ключи для тестов
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        
        # Сохраняем публичный ключ в формате PEM
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
    
    def _make_token(self, payload_dict: dict) -> str:
        """Создаёт подписанный токен."""
        import base64
        
        payload_json = json.dumps(payload_dict, sort_keys=True)
        payload_bytes = payload_json.encode()
        signature = self.private_key.sign(payload_bytes)
        
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip('=')
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        
        return f"{payload_b64}.{signature_b64}"
    
    def test_valid_token(self):
        """Валидный токен с будущей current_period_end."""
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,  # +30 дней
            "issued_at": int(time.time())
        }
        
        token = self._make_token(payload)
        
        # Подменяем публичный ключ
        with patch('licensing.public_key.LICENSE_PUBLIC_KEY_PEM', self.public_key_pem):
            valid, parsed_payload, error = verify_token(token)
        
        self.assertTrue(valid, f"Token should be valid, error: {error}")
        self.assertIsNone(error)
        self.assertEqual(parsed_payload["license_key"], "SGNR-TEST-TEST-TEST-TEST")
        self.assertEqual(parsed_payload["plan"], "monthly")
    
    def test_invalid_signature(self):
        """Токен с подделанной подписью."""
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,
            "issued_at": int(time.time())
        }
        
        token = self._make_token(payload)
        
        # Портим подпись (меняем один символ)
        parts = token.split(".")
        parts[1] = parts[1][:-1] + "X"
        tampered_token = ".".join(parts)
        
        # Подменяем публичный ключ
        with patch('licensing.public_key.LICENSE_PUBLIC_KEY_PEM', self.public_key_pem):
            valid, parsed_payload, error = verify_token(tampered_token)
        
        self.assertFalse(valid)
        self.assertIsNotNone(error)
        self.assertIn("signature", error.lower())
    
    def test_tampered_payload(self):
        """Токен с изменённым payload (но валидной подписью старого payload)."""
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,
            "issued_at": int(time.time())
        }
        
        token = self._make_token(payload)
        
        # Меняем payload (но оставляем подпись старую)
        import base64
        parts = token.split(".")
        
        tampered_payload = payload.copy()
        tampered_payload["plan"] = "yearly"  # Подделываем план
        tampered_json = json.dumps(tampered_payload, sort_keys=True)
        tampered_b64 = base64.urlsafe_b64encode(tampered_json.encode()).decode().rstrip('=')
        
        tampered_token = f"{tampered_b64}.{parts[1]}"
        
        # Подменяем публичный ключ
        with patch('licensing.public_key.LICENSE_PUBLIC_KEY_PEM', self.public_key_pem):
            valid, parsed_payload, error = verify_token(tampered_token)
        
        self.assertFalse(valid)
        self.assertIsNotNone(error)


class TestDeviceFingerprint(unittest.TestCase):
    """Тесты сбора fingerprint устройства."""
    
    def test_fingerprint_not_empty(self):
        """Fingerprint не должен быть пустым."""
        fp = get_device_fingerprint()
        self.assertIsInstance(fp, str)
        self.assertEqual(len(fp), 64)  # SHA-256 hex = 64 символа
    
    def test_fingerprint_stable(self):
        """Fingerprint должен быть стабильным (одинаковым при повторных вызовах)."""
        fp1 = get_device_fingerprint()
        fp2 = get_device_fingerprint()
        self.assertEqual(fp1, fp2)
    
    def test_device_label_not_empty(self):
        """Device label не должен быть пустым."""
        label = get_device_label()
        self.assertIsInstance(label, str)
        self.assertGreater(len(label), 0)


class TestLicenseManager(unittest.TestCase):
    """Тесты LicenseManager."""
    
    def setUp(self):
        """Создаём временную директорию для токена."""
        self.temp_dir = tempfile.mkdtemp()
        self.token_path = Path(self.temp_dir) / "license.token"
        
        # Генерируем тестовую пару ключей
        from cryptography.hazmat.primitives.asymmetric import ed25519
        from cryptography.hazmat.primitives import serialization
        
        self.private_key = ed25519.Ed25519PrivateKey.generate()
        self.public_key = self.private_key.public_key()
        
        self.public_key_pem = self.public_key.public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo
        ).decode('utf-8')
        
        # Патчим путь к токену и публичный ключ
        self.patcher_path = patch.object(LicenseManager, '_get_token_path', return_value=self.token_path)
        self.patcher_key = patch('licensing.public_key.LICENSE_PUBLIC_KEY_PEM', self.public_key_pem)
        
        self.patcher_path.start()
        self.patcher_key.start()
        
        self.manager = LicenseManager()
    
    def tearDown(self):
        """Удаляем временную директорию."""
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)
        
        self.patcher_path.stop()
        self.patcher_key.stop()
    
    def _make_token(self, payload_dict: dict) -> str:
        """Создаёт подписанный токен."""
        import base64
        
        payload_json = json.dumps(payload_dict, sort_keys=True)
        payload_bytes = payload_json.encode()
        signature = self.private_key.sign(payload_bytes)
        
        payload_b64 = base64.urlsafe_b64encode(payload_bytes).decode().rstrip('=')
        signature_b64 = base64.urlsafe_b64encode(signature).decode().rstrip('=')
        
        return f"{payload_b64}.{signature_b64}"
    
    def test_not_activated(self):
        """Отсутствие токена → NOT_ACTIVATED."""
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.NOT_ACTIVATED)
    
    def test_valid_token(self):
        """Валидный токен → VALID."""
        now = int(time.time())
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": now + 30 * 86400,  # +30 дней
            "issued_at": now
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.VALID)
    
    def test_expired_token(self):
        """Токен с current_period_end в прошлом → EXPIRED."""
        now = int(time.time())
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": now - 86400,  # -1 день (в прошлом)
            "issued_at": now - 35 * 86400  # -35 дней
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.EXPIRED)
    
    def test_revoked_status(self):
        """Токен с status != active → REVOKED."""
        now = int(time.time())
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "canceled",  # Отозван
            "current_period_end": now + 30 * 86400,
            "issued_at": now
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.REVOKED)
    
    def test_grace_period(self):
        """Токен просрочен для refresh, но в grace period → GRACE_PERIOD."""
        now = int(time.time())
        
        # issued_at = 5 дней назад (больше refresh_interval_days=3, но меньше grace_period_days=10)
        issued_at = now - 5 * 86400
        
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": now + 25 * 86400,  # Подписка активна
            "issued_at": issued_at
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.GRACE_PERIOD)
    
    def test_grace_period_exceeded(self):
        """Токен вне grace period → EXPIRED."""
        now = int(time.time())
        
        # issued_at = 15 дней назад (больше grace_period_days=10)
        issued_at = now - 15 * 86400
        
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": now + 15 * 86400,  # Подписка активна, но grace period истёк
            "issued_at": issued_at
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.EXPIRED)
    
    def test_clock_rollback_detection(self):
        """Откат часов (issued_at > now) → EXPIRED."""
        now = int(time.time())
        
        # issued_at в будущем (откат часов)
        issued_at = now + 86400  # +1 день
        
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "monthly",
            "status": "active",
            "current_period_end": now + 30 * 86400,
            "issued_at": issued_at
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        status = self.manager.check_local_status()
        self.assertEqual(status, LicenseStatus.EXPIRED)
    
    def test_get_plan_info(self):
        """get_plan_info() возвращает корректные данные."""
        now = int(time.time())
        payload = {
            "license_key": "SGNR-TEST-TEST-TEST-TEST",
            "device_id": "test-device-123",
            "plan": "yearly",
            "status": "active",
            "current_period_end": now + 365 * 86400,
            "issued_at": now
        }
        
        token = self._make_token(payload)
        self.manager._save_token(token)
        
        plan_info = self.manager.get_plan_info()
        
        self.assertIsNotNone(plan_info)
        self.assertEqual(plan_info["plan"], "yearly")
        self.assertEqual(plan_info["license_key"], "SGNR-TEST-TEST-TEST-TEST")
        self.assertEqual(plan_info["current_period_end"], payload["current_period_end"])


if __name__ == "__main__":
    unittest.main()
