"""
tests/test_license_service.py

Юнит-тесты LicenseService без HTTP-слоя (только db_session).
"""
import pytest
import uuid
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
from fastapi import HTTPException

from app.models import License, Device
from app.services.license_service import LicenseService


def test_activate_license_direct(db_session: Session, test_license: License):
    """Прямой тест активации через LicenseService без HTTP."""
    service = LicenseService(db_session)
    
    result = service.activate_license(
        license_key=test_license.license_key,
        fingerprint_hash="a" * 64,
        device_label="Test Device",
        app_version="1.0.0"
    )
    
    assert "token" in result
    assert result["plan"] == "monthly"
    assert "current_period_end" in result


def test_activate_license_device_limit(db_session: Session, test_license: License):
    """Проверка лимита устройств в LicenseService."""
    service = LicenseService(db_session)
    
    # Активируем max_devices устройств
    for i in range(test_license.max_devices):
        service.activate_license(
            license_key=test_license.license_key,
            fingerprint_hash=f"device_{i}" + "0" * 56,
            device_label=f"Device {i}",
            app_version="1.0.0"
        )
    
    # Попытка активации ещё одного устройства должна провалиться
    with pytest.raises(HTTPException) as exc_info:
        service.activate_license(
            license_key=test_license.license_key,
            fingerprint_hash="too_many" + "0" * 55,
            device_label="Too Many Devices",
            app_version="1.0.0"
        )
    
    assert exc_info.value.status_code == 409
    assert exc_info.value.detail["error_code"] == "DEVICE_LIMIT_REACHED"


def test_activate_same_device_idempotent(db_session: Session, test_license: License):
    """Повторная активация того же устройства идемпотентна."""
    service = LicenseService(db_session)
    fingerprint = "same_device" + "0" * 53
    
    # Первая активация
    result1 = service.activate_license(
        license_key=test_license.license_key,
        fingerprint_hash=fingerprint,
        device_label="Original Label",
        app_version="1.0.0"
    )
    
    # Вторая активация того же устройства
    result2 = service.activate_license(
        license_key=test_license.license_key,
        fingerprint_hash=fingerprint,
        device_label="Updated Label",
        app_version="1.0.1"
    )
    
    # Должны получить токен
    assert "token" in result2
    
    # Проверка что устройство не задублировалось
    devices_count = db_session.query(Device).filter(
        Device.license_id == test_license.id,
        Device.fingerprint_hash == fingerprint,
        Device.deactivated_at.is_(None)
    ).count()
    
    assert devices_count == 1


def test_refresh_with_invalid_device_id(db_session: Session, test_license: License):
    """Refresh с невалидным device_id (не-UUID) должен вернуть ошибку."""
    service = LicenseService(db_session)
    
    # Создаём токен с невалидным device_id
    from app.crypto import sign_token, load_private_key
    from app.config import get_settings
    
    settings = get_settings()
    private_key = load_private_key(settings.ed25519_private_key_pem)
    
    payload = {
        "license_key": test_license.license_key,
        "device_id": "not-a-uuid",  # Невалидный UUID
        "plan": "monthly",
        "status": "active",
        "current_period_end": int(datetime.utcnow().timestamp()),
        "issued_at": int(datetime.utcnow().timestamp())
    }
    
    token = sign_token(payload, private_key)
    
    # Попытка refresh должна провалиться
    with pytest.raises(HTTPException) as exc_info:
        service.refresh_license(token, "fingerprint" + "0" * 53)
    
    assert exc_info.value.status_code == 401
    assert exc_info.value.detail["error_code"] == "INVALID_TOKEN"
    assert "Invalid device_id" in exc_info.value.detail["error"]


def test_deactivate_device_idempotent(db_session: Session, test_license: License):
    """Деактивация несуществующего устройства идемпотентна."""
    service = LicenseService(db_session)
    
    # Создаём токен с несуществующим device_id
    from app.crypto import sign_token, load_private_key
    from app.config import get_settings
    
    settings = get_settings()
    private_key = load_private_key(settings.ed25519_private_key_pem)
    
    fake_device_id = str(uuid.uuid4())
    
    payload = {
        "license_key": test_license.license_key,
        "device_id": fake_device_id,
        "plan": "monthly",
        "status": "active",
        "current_period_end": int(datetime.utcnow().timestamp()),
        "issued_at": int(datetime.utcnow().timestamp())
    }
    
    token = sign_token(payload, private_key)
    
    # Деактивация несуществующего устройства должна вернуть success
    result = service.deactivate_device(token)
    
    assert result["success"] is True


def test_deactivate_device_twice(db_session: Session, test_license: License):
    """Двойная деактивация устройства идемпотентна."""
    service = LicenseService(db_session)
    
    # Активируем устройство
    result = service.activate_license(
        license_key=test_license.license_key,
        fingerprint_hash="device" + "0" * 58,
        device_label="Test Device",
        app_version="1.0.0"
    )
    
    token = result["token"]
    
    # Первая деактивация
    result1 = service.deactivate_device(token)
    assert result1["success"] is True
    
    # Вторая деактивация того же устройства
    result2 = service.deactivate_device(token)
    assert result2["success"] is True


def test_refresh_after_license_revoked(db_session: Session, test_license: License):
    """Refresh после отзыва лицензии возвращает токен с новым статусом."""
    service = LicenseService(db_session)
    
    # Активируем устройство
    result = service.activate_license(
        license_key=test_license.license_key,
        fingerprint_hash="device" + "0" * 58,
        device_label="Test Device",
        app_version="1.0.0"
    )
    
    token = result["token"]
    
    # Отзываем лицензию
    test_license.status = "revoked"
    db_session.commit()
    
    # Refresh должен вернуть токен с новым статусом (механизм отзыва)
    refreshed = service.refresh_license(token, "device" + "0" * 58)
    
    assert "token" in refreshed
    
    # Парсим новый токен и проверяем статус
    from app.crypto import parse_token
    success, payload, _ = parse_token(refreshed["token"])
    
    assert success is True
    assert payload["status"] == "revoked"


def test_refresh_fingerprint_mismatch(db_session: Session, test_license: License):
    """Refresh с неправильным fingerprint должен провалиться."""
    service = LicenseService(db_session)
    
    # Активируем устройство
    original_fingerprint = "device" + "0" * 58
    result = service.activate_license(
        license_key=test_license.license_key,
        fingerprint_hash=original_fingerprint,
        device_label="Test Device",
        app_version="1.0.0"
    )
    
    token = result["token"]
    
    # Попытка refresh с другим fingerprint (защита от кражи токена)
    different_fingerprint = "hacker" + "0" * 58
    
    with pytest.raises(HTTPException) as exc_info:
        service.refresh_license(token, different_fingerprint)
    
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error_code"] == "FINGERPRINT_MISMATCH"


def test_activate_expired_license(db_session: Session):
    """Активация истёкшей лицензии должна провалиться."""
    # Создаём просроченную лицензию
    expired_license = License(
        license_key="SGNR-EXPI-EXPI-EXPI-EXPI",
        plan="monthly",
        status="active",
        max_devices=2,
        current_period_end=datetime.utcnow() - timedelta(days=1)  # Истекла вчера
    )
    db_session.add(expired_license)
    db_session.commit()
    
    service = LicenseService(db_session)
    
    with pytest.raises(HTTPException) as exc_info:
        service.activate_license(
            license_key=expired_license.license_key,
            fingerprint_hash="device" + "0" * 58,
            device_label="Test Device",
            app_version="1.0.0"
        )
    
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error_code"] == "LICENSE_EXPIRED"


def test_activate_revoked_license(db_session: Session):
    """Активация отозванной лицензии должна провалиться."""
    # Создаём отозванную лицензию
    revoked_license = License(
        license_key="SGNR-REVO-REVO-REVO-REVO",
        plan="monthly",
        status="revoked",
        max_devices=2,
        current_period_end=datetime.utcnow() + timedelta(days=30)
    )
    db_session.add(revoked_license)
    db_session.commit()
    
    service = LicenseService(db_session)
    
    with pytest.raises(HTTPException) as exc_info:
        service.activate_license(
            license_key=revoked_license.license_key,
            fingerprint_hash="device" + "0" * 58,
            device_label="Test Device",
            app_version="1.0.0"
        )
    
    assert exc_info.value.status_code == 403
    assert exc_info.value.detail["error_code"] == "LICENSE_REVOKED"
