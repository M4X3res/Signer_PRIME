"""
tests/test_admin_api.py

Тесты для admin API.
"""
import pytest
from fastapi.testclient import TestClient


def test_create_license_valid(client: TestClient, admin_headers: dict):
    """Создание лицензии с валидным admin key."""
    response = client.post(
        "/api/admin/licenses",
        json={
            "plan": "monthly",
            "duration_days": 30,
            "max_devices": 2
        },
        headers=admin_headers
    )
    
    assert response.status_code == 200
    data = response.json()
    assert data["license_key"].startswith("SGNR-")
    assert data["plan"] == "monthly"
    assert data["max_devices"] == 2
    assert "expires_at" in data


def test_create_license_invalid_admin_key(client: TestClient):
    """Попытка создать лицензию с неверным admin key возвращает 403."""
    response = client.post(
        "/api/admin/licenses",
        json={
            "plan": "monthly",
            "duration_days": 30,
            "max_devices": 2
        },
        headers={"X-Admin-Key": "wrong_key"}
    )
    
    assert response.status_code == 403


def test_create_license_missing_admin_key(client: TestClient):
    """Попытка создать лицензию без admin key возвращает 422."""
    response = client.post(
        "/api/admin/licenses",
        json={
            "plan": "monthly",
            "duration_days": 30,
            "max_devices": 2
        }
    )
    
    assert response.status_code == 422  # Missing required header


def test_create_license_invalid_plan(client: TestClient, admin_headers: dict):
    """Создание лицензии с невалидным планом возвращает 422."""
    response = client.post(
        "/api/admin/licenses",
        json={
            "plan": "invalid_plan",
            "duration_days": 30,
            "max_devices": 2
        },
        headers=admin_headers
    )
    
    assert response.status_code == 422  # Validation error
