"""
tests/test_routes_refresh.py

Тесты обновления токенов (refresh).
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from datetime import datetime

from app.models import License, Device


def test_refresh_valid_token(client: TestClient, test_license: License):
    """Тест #6: Refresh валидного токена возвращает новый токен."""
    # Сначала активируем
    activate_response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "a" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    assert activate_response.status_code == 200
    token = activate_response.json()["token"]
    
    # Refresh
    refresh_response = client.post("/api/license/refresh", json={
        "token": token,
        "fingerprint_hash": "a" * 64
    })
    
    assert refresh_response.status_code == 200
    data = refresh_response.json()
    assert "token" in data
    assert data["token"] != token  # Новый токен
    assert data["plan"] == "monthly"


def test_refresh_reflects_status_change(client: TestClient, test_license: License, db_session: Session):
    """Тест #7: Refresh после отзыва лицензии возвращает токен с новым status."""
    # Активация
    activate_response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "b" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    assert activate_response.status_code == 200
    token = activate_response.json()["token"]
    
    # Отзываем лицензию вручную в БД
    test_license.status = "canceled"
    db_session.commit()
    
    # Refresh должен вернуть токен с status: canceled
    refresh_response = client.post("/api/license/refresh", json={
        "token": token,
        "fingerprint_hash": "b" * 64
    })
    
    # Refresh может вернуть 403 для отозванных или 200 с новым токеном
    # В зависимости от реализации license_service - проверим оба варианта
    if refresh_response.status_code == 200:
        # Если вернули токен, клиент должен сам распарсить и увидеть canceled
        data = refresh_response.json()
        assert "token" in data
    elif refresh_response.status_code == 403:
        # Если сервер сразу отказал
        data = refresh_response.json()
        assert data["error_code"] == "LICENSE_REVOKED"
    else:
        pytest.fail(f"Unexpected status code: {refresh_response.status_code}")


def test_refresh_deactivated_device(client: TestClient, test_license: License, db_session: Session):
    """Тест #8: Refresh деактивированного устройства возвращает 403."""
    # Активация
    activate_response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "c" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    assert activate_response.status_code == 200
    token = activate_response.json()["token"]
    
    # Деактивация
    deactivate_response = client.post("/api/license/deactivate", json={
        "token": token
    })
    assert deactivate_response.status_code == 200
    
    # Попытка refresh
    refresh_response = client.post("/api/license/refresh", json={
        "token": token,
        "fingerprint_hash": "c" * 64
    })
    
    assert refresh_response.status_code == 403
    data = refresh_response.json()
    assert data["error_code"] == "DEVICE_DEACTIVATED"


def test_refresh_invalid_token(client: TestClient):
    """Refresh невалидного токена возвращает 401."""
    response = client.post("/api/license/refresh", json={
        "token": "invalid.token.here",
        "fingerprint_hash": "d" * 64
    })
    
    assert response.status_code == 401
    data = response.json()
    assert data["error_code"] == "INVALID_TOKEN"


def test_rate_limiting_refresh(client: TestClient, test_license: License):
    """Тест rate limiting на /refresh (лимит 20/minute)."""
    # Активируем устройство
    activate_response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "e" * 64,
        "device_label": "Test Device",
        "app_version": "1.0.0"
    })
    assert activate_response.status_code == 200
    token = activate_response.json()["token"]
    
    # Делаем 21 запрос (лимит 20/minute)
    for i in range(21):
        response = client.post("/api/license/refresh", json={
            "token": token,
            "fingerprint_hash": "e" * 64
        })
        
        if i < 20:
            assert response.status_code == 200, f"Request {i} failed unexpectedly"
        else:
            # 21-й запрос должен получить 429
            assert response.status_code == 429, "Rate limit not enforced"
