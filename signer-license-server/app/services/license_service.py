"""
app/services/license_service.py
Бизнес-логика управления лицензиями.
"""
import logging
import time
from datetime import datetime
from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import and_, select
from fastapi import HTTPException

from app.models import License, Device
from app.crypto import sign_token, parse_token, load_private_key
from app.config import get_settings

logger = logging.getLogger(__name__)


class LicenseService:
    """Сервис управления лицензиями."""
    
    def __init__(self, db: Session):
        self.db = db
        self.settings = get_settings()
        self.private_key = load_private_key(self.settings.ed25519_private_key_pem)
    
    def activate_license(
        self,
        license_key: str,
        fingerprint_hash: str,
        device_label: str,
        app_version: str
    ) -> Dict[str, Any]:
        """
        Активация лицензии на устройстве.
        
        Использует SELECT FOR UPDATE для защиты от race conditions.
        """
        logger.info(f"Activating license: {license_key[:10]}... for device: {device_label}")
        
        # Найти лицензию
        license = self.db.query(License).filter(
            License.license_key == license_key
        ).first()
        
        if not license:
            logger.warning(f"License not found: {license_key}")
            raise HTTPException(
                status_code=404,
                detail={"error_code": "INVALID_LICENSE", "error": "License key not found"}
            )
        
        # Проверить статус
        if license.status != "active":
            logger.warning(f"License not active: {license_key}, status={license.status}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "LICENSE_REVOKED",
                    "error": f"License status: {license.status}"
                }
            )
        
        # Проверить срок действия
        now = datetime.utcnow()
        if license.current_period_end < now:
            logger.warning(f"License expired: {license_key}")
            raise HTTPException(
                status_code=403,
                detail={"error_code": "LICENSE_EXPIRED", "error": "License period has ended"}
            )
        
        # Транзакция с блокировкой для защиты от гонок
        try:
            # Заблокировать лицензию для обновления
            license = self.db.query(License).filter(
                License.id == license.id
            ).with_for_update().one()
            
            # Найти существующее устройство
            existing_device = self.db.query(Device).filter(
                and_(
                    Device.license_id == license.id,
                    Device.fingerprint_hash == fingerprint_hash,
                    Device.deactivated_at.is_(None)
                )
            ).first()
            
            if existing_device:
                # Переактивация существующего устройства
                existing_device.last_seen = now
                existing_device.device_label = device_label
                device_id = str(existing_device.id)
                logger.info(f"Reactivated existing device: {device_id}")
            else:
                # Проверить лимит активных устройств
                active_count = self.db.query(Device).filter(
                    and_(
                        Device.license_id == license.id,
                        Device.deactivated_at.is_(None)
                    )
                ).count()
                
                if active_count >= license.max_devices:
                    logger.warning(
                        f"Device limit reached for {license_key}: {active_count}/{license.max_devices}"
                    )
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error_code": "DEVICE_LIMIT_REACHED",
                            "error": f"Maximum {license.max_devices} devices allowed"
                        }
                    )
                
                # Создать новое устройство
                new_device = Device(
                    license_id=license.id,
                    fingerprint_hash=fingerprint_hash,
                    device_label=device_label
                )
                self.db.add(new_device)
                self.db.flush()  # Получить ID
                device_id = str(new_device.id)
                logger.info(f"Registered new device: {device_id}")
            
            self.db.commit()
            
        except HTTPException:
            self.db.rollback()
            raise
        except Exception as e:
            self.db.rollback()
            logger.error(f"Error activating license: {e}", exc_info=True)
            raise HTTPException(
                status_code=500,
                detail={"error_code": "INTERNAL_ERROR", "error": str(e)}
            )
        
        # Создать токен
        payload = {
            "license_key": license.license_key,
            "device_id": device_id,
            "plan": license.plan,
            "status": license.status,
            "current_period_end": int(license.current_period_end.timestamp()),
            "issued_at": int(time.time())
        }
        
        token = sign_token(payload, self.private_key)
        
        logger.info(f"License activated successfully: {license_key}")
        
        return {
            "token": token,
            "plan": license.plan,
            "current_period_end": int(license.current_period_end.timestamp())
        }
    
    def refresh_license(
        self,
        token: str,
        fingerprint_hash: str
    ) -> Dict[str, Any]:
        """
        Обновление токена лицензии.
        
        Возвращает актуальный статус из БД (механизм отзыва).
        """
        logger.info("Refreshing license token")
        
        # Распарсить токен
        success, payload, error = parse_token(token)
        if not success or not payload:
            logger.warning(f"Invalid token: {error}")
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "Token format invalid"}
            )
        
        license_key = payload.get("license_key")
        device_id = payload.get("device_id")
        
        if not license_key or not device_id:
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "Token missing required fields"}
            )
        
        # Найти лицензию
        license = self.db.query(License).filter(
            License.license_key == license_key
        ).first()
        
        if not license:
            logger.warning(f"License not found: {license_key}")
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "License not found"}
            )
        
        # Найти устройство
        try:
            import uuid
            device_uuid = uuid.UUID(device_id)
        except ValueError:
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "Invalid device_id"}
            )
        
        device = self.db.query(Device).filter(
            Device.id == device_uuid
        ).first()
        
        if not device:
            logger.warning(f"Device not found: {device_id}")
            raise HTTPException(
                status_code=403,
                detail={"error_code": "DEVICE_NOT_FOUND", "error": "Device not found"}
            )
        
        # Проверить деактивацию
        if device.deactivated_at is not None:
            logger.warning(f"Device deactivated: {device_id}")
            raise HTTPException(
                status_code=403,
                detail={"error_code": "DEVICE_DEACTIVATED", "error": "Device has been deactivated"}
            )
        
        # Проверить fingerprint (защита от кражи токена)
        if device.fingerprint_hash != fingerprint_hash:
            logger.warning(f"Fingerprint mismatch for device: {device_id}")
            raise HTTPException(
                status_code=403,
                detail={
                    "error_code": "FINGERPRINT_MISMATCH",
                    "error": "Device fingerprint does not match"
                }
            )
        
        # Проверить статус лицензии (механизм отзыва)
        if license.status != "active":
            logger.info(f"License status changed: {license_key} -> {license.status}")
            # Возвращаем токен с актуальным статусом - клиент обработает отзыв
        
        # Обновить last_seen
        device.last_seen = datetime.utcnow()
        self.db.commit()
        
        # Создать новый токен с актуальными данными из БД
        payload = {
            "license_key": license.license_key,
            "device_id": device_id,
            "plan": license.plan,
            "status": license.status,  # Актуальный статус!
            "current_period_end": int(license.current_period_end.timestamp()),
            "issued_at": int(time.time())
        }
        
        token = sign_token(payload, self.private_key)
        
        logger.info(f"License refreshed: {license_key}, status={license.status}")
        
        return {
            "token": token,
            "plan": license.plan,
            "current_period_end": int(license.current_period_end.timestamp())
        }
    
    def deactivate_device(self, token: str) -> Dict[str, Any]:
        """
        Деактивация устройства.
        
        Идемпотентная операция.
        """
        logger.info("Deactivating device")
        
        # Распарсить токен
        success, payload, error = parse_token(token)
        if not success or not payload:
            logger.warning(f"Invalid token: {error}")
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "Token format invalid"}
            )
        
        device_id = payload.get("device_id")
        if not device_id:
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "Token missing device_id"}
            )
        
        # Найти устройство
        try:
            import uuid
            device_uuid = uuid.UUID(device_id)
        except ValueError:
            raise HTTPException(
                status_code=401,
                detail={"error_code": "INVALID_TOKEN", "error": "Invalid device_id"}
            )
        
        device = self.db.query(Device).filter(
            Device.id == device_uuid
        ).first()
        
        if not device:
            # Идемпотентность - не найдено считается успехом
            logger.info(f"Device not found (already deactivated?): {device_id}")
            return {"success": True}
        
        # Деактивировать
        if device.deactivated_at is None:
            device.deactivated_at = datetime.utcnow()
            self.db.commit()
            logger.info(f"Device deactivated: {device_id}")
        else:
            logger.info(f"Device already deactivated: {device_id}")
        
        return {"success": True}
