"""
tests/test_stripe_webhook.py

Тест #10: Stripe webhook с неверной подписью не изменяет БД.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
import json

from app.models import License


def test_webhook_invalid_signature_does_not_modify_db(client: TestClient, db_session: Session):
    """
    Тест #10: Вебхук с неверной подписью возвращает 400 и не изменяет БД.
    """
    # Snapshot БД до запроса
    licenses_before = db_session.query(License).count()
    
    # Подделанный webhook payload
    fake_payload = json.dumps({
        "type": "checkout.session.completed",
        "data": {
            "object": {
                "customer": "cus_fake123",
                "subscription": "sub_fake123"
            }
        }
    })
    
    # Запрос с неверной подписью
    response = client.post(
        "/api/webhooks/stripe",
        content=fake_payload.encode(),
        headers={
            "stripe-signature": "t=123456,v1=fakesignature",
            "Content-Type": "application/json"
        }
    )
    
    # Должен вернуть 400
    assert response.status_code == 400
    data = response.json()
    assert "signature" in data["detail"].lower() or "payload" in data["detail"].lower()
    
    # БД не должна измениться
    licenses_after = db_session.query(License).count()
    assert licenses_after == licenses_before, "Database was modified despite invalid signature"


def test_webhook_missing_signature_header(client: TestClient):
    """Webhook без заголовка signature возвращает 400."""
    fake_payload = json.dumps({"type": "test"})
    
    response = client.post(
        "/api/webhooks/stripe",
        content=fake_payload.encode(),
        headers={"Content-Type": "application/json"}
    )
    
    assert response.status_code == 400
    data = response.json()
    assert "signature" in data["detail"].lower()
