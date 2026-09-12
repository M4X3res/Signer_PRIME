"""
tests/test_race_condition.py

Тест #9: Защита от гонки при активации устройств (SELECT FOR UPDATE).
"""
import pytest
from concurrent.futures import ThreadPoolExecutor, as_completed
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models import License


def test_concurrent_activation_race_condition(client: TestClient, test_license: License, db_session: Session):
    """
    Тест #9: Два параллельных activate с новыми fingerprint при лимите 1 свободный слот.
    
    Сценарий:
    - max_devices = 2
    - Активируем 1 устройство (остаётся 1 слот)
    - Параллельно пытаемся активировать 2 новых устройства
    - Ожидание: ровно один получит 200, второй 409
    """
    # Установим max_devices = 2 для теста
    test_license.max_devices = 2
    db_session.commit()
    
    # Активируем первое устройство
    response = client.post("/api/license/activate", json={
        "license_key": test_license.license_key,
        "fingerprint_hash": "x" * 64,
        "device_label": "Device 0",
        "app_version": "1.0.0"
    })
    assert response.status_code == 200
    
    # Теперь остался 1 слот
    
    # Параллельная активация двух НОВЫХ устройств
    def activate_device(fingerprint: str, device_num: int):
        """Активация устройства в отдельном потоке."""
        # Создаём новый TestClient для каждого потока
        with TestClient(client.app) as thread_client:
            response = thread_client.post("/api/license/activate", json={
                "license_key": test_license.license_key,
                "fingerprint_hash": fingerprint,
                "device_label": f"Device {device_num}",
                "app_version": "1.0.0"
            })
            return response.status_code, response.json()
    
    # Запуск двух параллельных запросов
    with ThreadPoolExecutor(max_workers=2) as executor:
        future1 = executor.submit(activate_device, "y" * 64, 1)
        future2 = executor.submit(activate_device, "z" * 64, 2)
        
        results = [future.result() for future in as_completed([future1, future2])]
    
    # Проверка результатов
    status_codes = [r[0] for r in results]
    
    # Ровно один должен получить 200, второй 409
    assert sorted(status_codes) == [200, 409], \
        f"Expected one 200 and one 409, got: {status_codes}"
    
    # Проверка, что 409 содержит правильный error_code
    for status_code, data in results:
        if status_code == 409:
            assert data["error_code"] == "DEVICE_LIMIT_REACHED"
