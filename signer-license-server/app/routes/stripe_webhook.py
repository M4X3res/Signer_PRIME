"""
app/routes/stripe_webhook.py

Stripe webhook endpoint для обработки событий подписок.
"""
import logging
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
import stripe

from app.config import get_settings
from app.db import get_db
from app.services.stripe_service import StripeService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.post("/stripe")
async def stripe_webhook(
    request: Request,
    db: Session = Depends(get_db)
):
    """
    Stripe webhook endpoint.
    
    **ВАЖНО:** Проверяет подпись вебхука для защиты от подделки.
    
    Обрабатываемые события:
    - checkout.session.completed - создание лицензии при оплате
    - customer.subscription.updated - обновление статуса лицензии
    - customer.subscription.deleted - отмена лицензии
    
    Конфигурация в Stripe Dashboard:
    1. Developers → Webhooks → Add endpoint
    2. URL: https://your-domain.com/api/webhooks/stripe
    3. Events: checkout.session.completed, customer.subscription.*
    4. Signing secret → STRIPE_WEBHOOK_SECRET env var
    """
    settings = get_settings()
    
    if not settings.stripe_webhook_secret:
        logger.error("STRIPE_WEBHOOK_SECRET not configured")
        raise HTTPException(status_code=500, detail="Webhook not configured")
    
    # Получение payload и signature
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")
    
    if not sig_header:
        logger.warning("Missing stripe-signature header")
        raise HTTPException(status_code=400, detail="Missing signature")
    
    # Проверка подписи
    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.stripe_webhook_secret
        )
    except ValueError as e:
        logger.error(f"Invalid payload: {e}")
        raise HTTPException(status_code=400, detail="Invalid payload")
    except stripe.error.SignatureVerificationError as e:
        logger.error(f"Invalid signature: {e}")
        raise HTTPException(status_code=400, detail="Invalid signature")
    
    # Обработка события
    event_type = event["type"]
    event_data = event["data"]["object"]
    
    logger.info(f"Received Stripe event: {event_type} (id: {event['id']})")
    
    service = StripeService(db)
    
    try:
        if event_type == "checkout.session.completed":
            # Создание лицензии при успешной оплате
            license_obj = service.handle_checkout_completed(event_data)
            if license_obj:
                logger.info(f"✅ Checkout processed: license {license_obj.license_key}")
            else:
                logger.warning(f"⚠️  Checkout processing failed or skipped")
        
        elif event_type == "customer.subscription.updated":
            # Обновление статуса лицензии
            success = service.handle_subscription_updated(event_data)
            if success:
                logger.info(f"✅ Subscription updated")
            else:
                logger.warning(f"⚠️  Subscription update failed or skipped")
        
        elif event_type == "customer.subscription.deleted":
            # Отмена лицензии
            success = service.handle_subscription_deleted(event_data)
            if success:
                logger.info(f"✅ Subscription deleted")
            else:
                logger.warning(f"⚠️  Subscription deletion failed or skipped")
        
        else:
            logger.info(f"Unhandled event type: {event_type}")
    
    except Exception as e:
        logger.error(f"Error processing webhook: {e}", exc_info=True)
        # Возвращаем 500 чтобы Stripe повторил попытку
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    
    return {"status": "success"}
