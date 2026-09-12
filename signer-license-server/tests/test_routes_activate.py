"""
tests/test_routes_activate.py

Тесты активации лицензий.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import License, Device


def test_activate_valid_license(client: TestClient, test_license: License):
    """Тест #1: Активация валидной лицензии."""
    response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "a" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    
    assert response.status_code == 200
    data = response.json()
    assert "token" in data
    assert data["plan"] == "monthly"
    assert "current_period_end" in data


def test_activate_same_device_twice(client: TestClient, test_license: License, db_session: Session):
    """Тест #2: Повторная активация того же устройства не создаёт дублей."""
    fingerprint = "b" * 64
    
    # Первая активация
    response1 = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": fingerprint,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    assert response1.status_code == 200
    
    # Вторая активация того же устройства
    response2 = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": fingerprint,
        "device_label": "Test Device Updated",
        "app_version": "1.0.1"
    })
    assert response2.status_code == 200
    
    # Проверка, что устройство одно
    devices = db_session.query(Device).filter(
        Device.license_id == test_license.id,
        Device.fingerprint_hash == fingerprint,
        Device.deactivated_at.is_(None)
    ).all()
    
    assert len(devices) == 1, "Должно быть ровно одно активное устройство"


def test_activate_exceeds_device_limit(client: TestClient, test_license: License):
    """Тест #3: Активация сверх лимита устройств возвращает 409."""
    # Активация max_devices устройств
    for i in range(test_license.max_devices):
        response = client.post("/api/license/activate", json={
            "license_key": test_license.license_key,
            "fingerprint_hash": f"{'c' * 63}{i}",
            "device_label": f"Device {i}",
            "app_version": "1.0.0"
        })
        assert response.status_code == 200
    
    # Попытка активировать ещё одно устройство
    response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "d" * 64,
        "device_label": "Device Overflow",
        "app_version": "1.0.0"
    })
    
    assert response.status_code == 409
    data = response.json()
    assert data["error_code"] == "DEVICE_LIMIT_REACHED"


def test_activate_invalid_license(client: TestClient):
    """Тест #4: Активация несуществующего ключа возвращает 404."""
    response = client.post("/api/license/activate", json={
        "license_key": "SGNR-FAKE-FAKE-FAKE-FAKE",
        "fingerprint_hash": "e" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    
    assert response.status_code == 404
    data = response.json()
    assert data["error_code"] == "INVALID_LICENSE"


def test_activate_revoked_license(client: TestClient, test_license: License, db_session: Session):
    """Тест #5: Активация отозванной лицензии возвращает 403."""
    # Отзываем лицензию
    test_license.status = "canceled"
    db_session.commit()
    
    response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "f" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    
    assert response.status_code == 403
    data = response.json()
    assert data["error_code"] == "LICENSE_REVOKED"


def test_rate_limiting_activate(client: TestClient, test_license: License):
    """Тест #12: Rate limiting на /activate возвращает 429 при превышении."""
    # Делаем 11 запросов (лимит 10/minute)
    for i in range(11):
        response = client.post("/api/license/activate", json={
            "license_key": test_license.license_key,
            "fingerprint_hash": f"{'g' * 63}{i % 10}",
            "device_label": f"Device {i}",
            "app_version": "1.0.0"
        })
        
        if i < 10:
            assert response.status_code in [200, 409], f"Request {i} failed unexpectedly"
        else:
            # 11-й запрос должен получить 429
            assert response.status_code == 429, "Rate limit not enforced"
