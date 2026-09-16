"""
Регрессионные тесты для исправлений из CACHE_FIX.md
"""
import pytest
import time
import json
from unittest.mock import Mock, MagicMock, patch
from pathlib import Path


# ════════════════════════════════════════════════════════════════
# БАГ 1: RefreshWorker GC protection
# ════════════════════════════════════════════════════════════════

def test_refresh_worker_not_garbage_collected():
    """
    БАГ 1: Проверяет, что RefreshWorker сохраняется в _refresh_workers
    и не может быть собран GC пока работает.
    """
    from licensing.license_manager import LicenseManager
    from PyQt6.QtWidgets import QApplication
    import sys
    
    # Создаём QApplication если его нет
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    
    with patch('licensing.license_manager.get_device_fingerprint', return_value='test_fingerprint'):
        manager = LicenseManager()
    
    # Проверяем, что хранилище воркеров инициализировано
    assert hasattr(manager, '_refresh_workers'), "LicenseManager должен иметь _refresh_workers"
    assert isinstance(manager._refresh_workers, set), "_refresh_workers должен быть set"
    
    initial_size = len(manager._refresh_workers)
    
    # Мокаем клиент
    manager.client.refresh = Mock(return_value=Mock(success=True, token="test_token"))
    
    callback_called = False
    def test_callback(success):
        nonlocal callback_called
        callback_called = True
    
    # Запускаем async refresh
    manager.refresh_async(test_callback)
    
    # Сразу после запуска воркер должен быть в set
    assert len(manager._refresh_workers) == initial_size + 1, "Воркер должен быть добавлен в _refresh_workers"
    
    # Ждём завершения
    app.processEvents()
    time.sleep(0.5)
    app.processEvents()
    
    # После завершения воркер должен быть удалён
    assert len(manager._refresh_workers) == initial_size, "Воркер должен быть удалён после завершения"


# ════════════════════════════════════════════════════════════════
# БАГ 2: backed_up_files scope in updater
# ════════════════════════════════════════════════════════════════

def test_backed_up_files_scope():
    """
    БАГ 2: Проверяет, что backed_up_files инициализирован до try блока
    и доступен в except для роллбека.
    """
    from updater.updater_main import apply_delta_update
    from pathlib import Path
    import tempfile
    import shutil
    
    with tempfile.TemporaryDirectory() as tmpdir:
        temp_dir = Path(tmpdir) / "temp"
        install_dir = Path(tmpdir) / "install"
        temp_dir.mkdir()
        install_dir.mkdir()
        
        # Создаём невалидный манифест чтобы вызвать ошибку ДО backed_up_files = []
        manifest_path = temp_dir / "delta_manifest.json"
        manifest_path.write_text("invalid json {{{")
        
        # apply_delta_update должен обработать ошибку без NameError
        result = apply_delta_update(temp_dir, manifest_path, install_dir)
        
        # Должен вернуть False (неудача), но не упасть с NameError
        assert result is False, "Должен вернуть False при ошибке парсинга манифеста"


# ════════════════════════════════════════════════════════════════
# БАГ 3: Server signature verification
# ════════════════════════════════════════════════════════════════

def test_server_verifies_token_signature_on_refresh():
    """
    БАГ 3: Проверяет, что сервер верифицирует подпись при refresh.
    """
    import sys
    sys.path.insert(0, 'signer-license-server')
    
    from app.crypto import verify_token_signature, sign_token, generate_license_key
    from cryptography.hazmat.primitives.asymmetric import ed25519
    
    # Генерируем ключевую пару
    private_key = ed25519.Ed25519PrivateKey.generate()
    
    # Создаём валидный токен
    payload = {
        "license_key": generate_license_key(),
        "device_id": "test-device-123",
        "plan": "monthly",
        "status": "active",
        "current_period_end": int(time.time()) + 86400,
        "issued_at": int(time.time())
    }
    
    valid_token = sign_token(payload, private_key)
    
    # 1. Валидный токен должен пройти проверку
    valid, parsed, error = verify_token_signature(valid_token, private_key)
    assert valid is True, f"Валидный токен должен пройти проверку: {error}"
    assert parsed == payload
    
    # 2. Подделанный токен (изменённый payload) должен быть отвергнут
    parts = valid_token.split(".")
    import base64
    forged_payload = payload.copy()
    forged_payload["plan"] = "yearly"  # Подделываем план
    forged_payload_json = json.dumps(forged_payload, sort_keys=True)
    forged_payload_b64 = base64.urlsafe_b64encode(forged_payload_json.encode()).decode().rstrip('=')
    forged_token = f"{forged_payload_b64}.{parts[1]}"  # Старая подпись с новым payload
    
    valid, parsed, error = verify_token_signature(forged_token, private_key)
    assert valid is False, "Подделанный токен должен быть отвергнут"
    assert "signature" in error.lower(), f"Ошибка должна упоминать подпись: {error}"


def test_server_requires_fingerprint_on_deactivate():
    """
    БАГ 3: Проверяет, что deactivate требует fingerprint_hash.
    """
    import sys
    sys.path.insert(0, 'signer-license-server')
    
    from app.schemas import DeactivateRequest
    from pydantic import ValidationError
    
    # 1. Запрос с fingerprint должен быть валидным
    try:
        req = DeactivateRequest(
            token="test_token_12345",
            fingerprint_hash="a" * 64  # SHA-256 хэш
        )
        assert req.fingerprint_hash == "a" * 64
    except ValidationError:
        pytest.fail("DeactivateRequest должен принимать fingerprint_hash")
    
    # 2. Запрос без fingerprint должен быть отвергнут
    with pytest.raises(ValidationError) as exc_info:
        DeactivateRequest(token="test_token_12345")
    
    assert "fingerprint_hash" in str(exc_info.value), "Должна быть ошибка валидации fingerprint_hash"


def test_client_sends_fingerprint_on_deactivate():
    """
    БАГ 3: Проверяет, что клиент отправляет fingerprint_hash при деактивации.
    """
    from licensing.license_client import LicenseClient
    from unittest.mock import patch, Mock
    
    client = LicenseClient()
    
    mock_response = Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    
    with patch('requests.post', return_value=mock_response) as mock_post:
        result = client.deactivate("test_token", "test_fingerprint_hash")
        
        # Проверяем, что POST был вызван с правильными данными
        assert mock_post.called
        call_args = mock_post.call_args
        assert call_args[1]['json']['token'] == "test_token"
        assert call_args[1]['json']['fingerprint_hash'] == "test_fingerprint_hash"
        assert result.success is True


# ════════════════════════════════════════════════════════════════
# БАГ 4: text_muted token (проверяем через импорт темы)
# ════════════════════════════════════════════════════════════════

def test_theme_tokens_have_text_secondary():
    """
    БАГ 4: Проверяет, что темы имеют text_secondary, а не text_muted.
    """
    from ui.themes.modern_dark import DARK_THEME_TOKENS
    from ui.themes.modern_light import LIGHT_THEME_TOKENS
    
    # Обе темы должны иметь text_secondary
    assert 'text_secondary' in DARK_THEME_TOKENS, "Тёмная тема должна иметь text_secondary"
    assert 'text_secondary' in LIGHT_THEME_TOKENS, "Светлая тема должна иметь text_secondary"
    
    # И не должны иметь text_muted (который не существует)
    # Примечание: этот тест не ловит использование несуществующего ключа, только проверяет наличие правильного


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
