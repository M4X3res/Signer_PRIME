"""
app/services/stripe_service.py

Обработка Stripe вебхуков для автоматического управления лицензиями.
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
import uuid

from sqlalchemy.orm import Session
import stripe

from app.models import License
from app.crypto import generate_license_key
from app.config import get_settings

logger = logging.getLogger(__name__)

# Маппинг Stripe Price ID на планы подписки
# TODO: Заполните реальными Price ID из Stripe Dashboard после создания продуктов
STRIPE_PRICE_TO_PLAN = {
    "price_monthly_prod": "monthly",      # Замените на реальный Price ID
    "price_quarterly_prod": "quarterly",  # Замените на реальный Price ID
    "price_yearly_prod": "yearly",        # Замените на реальный Price ID
    # Test mode цены
    "price_monthly_test": "monthly",
    "price_quarterly_test": "quarterly",
    "price_yearly_test": "yearly",
}

PLAN_TO_DEVICES = {
    "monthly": 2,
    "quarterly": 3,
    "yearly": 5,
}

PLAN_TO_DAYS = {
    "monthly": 30,
    "quarterly": 90,
    "yearly": 365,
}


class StripeService:
    """Сервис для обработки Stripe событий."""
    
    def __init__(self, db: Session):
        self.db = db
        settings = get_settings()
        stripe.api_key = settings.stripe_secret_key
    
    def handle_checkout_completed(self, session: dict) -> Optional[License]:
        """
        Обработка checkout.session.completed - создание лицензии при оплате.
        
        Args:
            session: Stripe Session объект
        
        Returns:
            Созданная лицензия или None при ошибке
        """
        customer_id = session.get("customer")
        subscription_id = session.get("subscription")
        
        if not customer_id or not subscription_id:
            logger.warning(f"Checkout session missing customer or subscription: {session.get('id')}")
            return None
        
        # Получение подписки для определения плана
        try:
            subscription = stripe.Subscription.retrieve(subscription_id)
            price_id = subscription["items"]["data"][0]["price"]["id"]
            plan = STRIPE_PRICE_TO_PLAN.get(price_id)
            
            if not plan:
                logger.error(f"Unknown Stripe Price ID: {price_id}")
                return None
            
            # Дата окончания текущего периода
            current_period_end = datetime.fromtimestamp(subscription["current_period_end"])
            
            # Проверка, существует ли уже лицензия для этого subscription
            existing = self.db.query(License).filter(
                License.stripe_subscription_id == subscription_id
            ).first()
            
            if existing:
                logger.info(f"License already exists for subscription {subscription_id}")
                return existing
            
            # Создание новой лицензии
            license_key = generate_license_key()
            license_obj = License(
                id=uuid.uuid4(),
                license_key=license_key,
                stripe_customer_id=customer_id,
                stripe_subscription_id=subscription_id,
                plan=plan,
                status="active",
                current_period_end=current_period_end,
                max_devices=PLAN_TO_DEVICES.get(plan, 2),
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            self.db.add(license_obj)
            self.db.commit()
            self.db.refresh(license_obj)
            
            logger.info(f"✅ License created from Stripe: {license_key} (subscription: {subscription_id})")
            
            # TODO: Отправить email с ключом лицензии клиенту
            # Получите email через session["customer_details"]["email"]
            
            return license_obj
            
        except stripe.error.StripeError as e:
            logger.error(f"Stripe API error: {e}")
            self.db.rollback()
            return None
        except Exception as e:
            logger.error(f"Failed to create license from checkout: {e}", exc_info=True)
            self.db.rollback()
            return None
    
    def handle_subscription_updated(self, subscription: dict) -> bool:
        """
        Обработка customer.subscription.updated - обновление статуса лицензии.
        
        Args:
            subscription: Stripe Subscription объект
        
        Returns:
            True если обработка успешна
        """
        subscription_id = subscription.get("id")
        status = subscription.get("status")
        current_period_end = subscription.get("current_period_end")
        
        license_obj = self.db.query(License).filter(
            License.stripe_subscription_id == subscription_id
        ).first()
        
        if not license_obj:
            logger.warning(f"License not found for subscription {subscription_id}")
            return False
        
        # Маппинг Stripe статусов на наши
        status_map = {
            "active": "active",
            "past_due": "past_due",
            "canceled": "canceled",
            "unpaid": "canceled",
            "incomplete": "past_due",
            "incomplete_expired": "expired",
            "trialing": "active",
        }
        
        new_status = status_map.get(status, "canceled")
        
        # Обновление лицензии
        license_obj.status = new_status
        license_obj.current_period_end = datetime.fromtimestamp(current_period_end)
        license_obj.updated_at = datetime.utcnow()
        
        self.db.commit()
        
        logger.info(f"✅ License {license_obj.license_key} updated: status={new_status}")
        
        return True
    
    def handle_subscription_deleted(self, subscription: dict) -> bool:
        """
        Обработка customer.subscription.deleted - отмена лицензии.
        
        Args:
            subscription: Stripe Subscription объект
        
        Returns:
            True если обработка успешна
        """
        subscription_id = subscription.get("id")
        
        license_obj = self.db.query(License).filter(
            License.stripe_subscription_id == subscription_id
        ).first()
        
        if not license_obj:
            logger.warning(f"License not found for subscription {subscription_id}")
            return False
        
        # Отмена лицензии
        license_obj.status = "canceled"
        license_obj.updated_at = datetime.utcnow()
        
        self.db.commit()
        
        logger.info(f"✅ License {license_obj.license_key} canceled (subscription deleted)")
        
        return True
