"""
tests/test_stripe_webhook.py

Тест #10: Stripe webhook с неверной подписью не изменяет БД.
ЗАДАЧА 7: Тесты отправки email после успешного checkout.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session
from unittest.mock import patch, MagicMock
from datetime import datetime, timedelta
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


@patch("app.services.stripe_service.stripe.Subscription.retrieve")
@patch("app.services.email_service.EmailService.send_license_key")
def test_checkout_completed_sends_email(mock_send_email, mock_stripe_subscription, db_session: Session):
    """
    ЗАДАЧА 7: Тест успешной отправки email при checkout.session.completed.
    """
    from app.services.stripe_service import StripeService
    
    # Мокируем Stripe Subscription
    mock_subscription = {
        "id": "sub_test123",
        "items": {
            "data": [
                {"price": {"id": "price_monthly_test"}}
            ]
        },
        "current_period_end": int((datetime.now() + timedelta(days=30)).timestamp())
    }
    mock_stripe_subscription.return_value = mock_subscription
    
    # Мокируем успешную отправку email
    mock_send_email.return_value = True
    
    # Создаём checkout session
    session = {
        "id": "cs_test123",
        "customer": "cus_test123",
        "subscription": "sub_test123",
        "customer_details": {
            "email": "customer@example.com"
        }
    }
    
    # Обрабатываем webhook
    service = StripeService(db_session)
    license_obj = service.handle_checkout_completed(session)
    
    assert license_obj is not None
    assert license_obj.license_key.startswith("SGNR-")
    
    # Проверяем, что email был отправлен
    mock_send_email.assert_called_once()
    call_args = mock_send_email.call_args
    assert call_args[1]["to_email"] == "customer@example.com"
    assert call_args[1]["license_key"] == license_obj.license_key
    assert call_args[1]["plan"] == "monthly"


@patch("app.services.stripe_service.stripe.Subscription.retrieve")
@patch("app.services.email_service.EmailService.send_license_key")
def test_checkout_completed_no_email_in_session(mock_send_email, mock_stripe_subscription, db_session: Session):
    """
    ЗАДАЧА 7: Тест обработки checkout без email в session - лицензия создаётся, email не отправляется.
    """
    from app.services.stripe_service import StripeService
    
    # Мокируем Stripe Subscription
    mock_subscription = {
        "id": "sub_test456",
        "items": {
            "data": [
                {"price": {"id": "price_yearly_test"}}
            ]
        },
        "current_period_end": int((datetime.now() + timedelta(days=365)).timestamp())
    }
    mock_stripe_subscription.return_value = mock_subscription
    
    # Создаём checkout session БЕЗ customer_details
    session = {
        "id": "cs_test456",
        "customer": "cus_test456",
        "subscription": "sub_test456"
        # Нет customer_details/email
    }
    
    # Обрабатываем webhook
    service = StripeService(db_session)
    license_obj = service.handle_checkout_completed(session)
    
    # Лицензия должна быть создана
    assert license_obj is not None
    assert license_obj.license_key.startswith("SGNR-")
    
    # Email НЕ должен быть отправлен
    mock_send_email.assert_not_called()


@patch("app.services.stripe_service.stripe.Subscription.retrieve")
@patch("app.services.email_service.EmailService.send_license_key")
def test_checkout_completed_email_failure_does_not_rollback_license(
    mock_send_email,
    mock_stripe_subscription,
    db_session: Session
):
    """
    ЗАДАЧА 7: Тест, что ошибка отправки email не откатывает создание лицензии.
    """
    from app.services.stripe_service import StripeService
    
    # Мокируем Stripe Subscription
    mock_subscription = {
        "id": "sub_test789",
        "items": {
            "data": [
                {"price": {"id": "price_quarterly_test"}}
            ]
        },
        "current_period_end": int((datetime.now() + timedelta(days=90)).timestamp())
    }
    mock_stripe_subscription.return_value = mock_subscription
    
    # Мокируем ОШИБКУ при отправке email
    mock_send_email.side_effect = Exception("SendGrid API unavailable")
    
    # Создаём checkout session с email
    session = {
        "id": "cs_test789",
        "customer": "cus_test789",
        "subscription": "sub_test789",
        "customer_details": {
            "email": "customer@example.com"
        }
    }
    
    # Обрабатываем webhook
    service = StripeService(db_session)
    license_obj = service.handle_checkout_completed(session)
    
    # Лицензия ДОЛЖНА быть создана несмотря на ошибку email
    assert license_obj is not None
    assert license_obj.license_key.startswith("SGNR-")
    
    # Проверяем, что лицензия сохранена в БД
    saved_license = db_session.query(License).filter(
        License.stripe_subscription_id == "sub_test789"
    ).first()
    assert saved_license is not None
    assert saved_license.license_key == license_obj.license_key
