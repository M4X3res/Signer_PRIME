"""
app/routes/license.py
Production эндпоинты для управления лицензиями.
"""
import logging
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.schemas import (
    ActivateRequest, RefreshRequest, DeactivateRequest,
    LicenseResponse, ErrorResponse
)
from app.services.license_service import LicenseService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/license", tags=["license"])


@router.post("/activate", response_model=LicenseResponse, responses={
    404: {"model": ErrorResponse},
    403: {"model": ErrorResponse},
    409: {"model": ErrorResponse}
})
async def activate_license(
    req: ActivateRequest,
    db: Session = Depends(get_db)
):
    """
    Активация лицензии на устройстве.
    
    - **license_key**: Ключ лицензии (SGNR-XXXX-XXXX-XXXX-XXXX)
    - **fingerprint_hash**: SHA-256 хэш устройства
    - **device_label**: Имя устройства (hostname)
    - **app_version**: Версия приложения
    
    **Errors:**
    - 404 INVALID_LICENSE - ключ не найден
    - 403 LICENSE_REVOKED - лицензия отозвана
    - 403 LICENSE_EXPIRED - подписка истекла
    - 409 DEVICE_LIMIT_REACHED - лимит устройств исчерпан
    """
    service = LicenseService(db)
    return service.activate_license(
        req.license_key,
        req.fingerprint_hash,
        req.device_label,
        req.app_version
    )


@router.post("/refresh", response_model=LicenseResponse, responses={
    401: {"model": ErrorResponse},
    403: {"model": ErrorResponse}
})
async def refresh_license(
    req: RefreshRequest,
    db: Session = Depends(get_db)
):
    """
    Обновление токена лицензии.
    
    Возвращает актуальный статус из БД.
    Механизм отзыва: если статус изменился, новый токен содержит актуальный status.
    
    - **token**: Текущий токен
    - **fingerprint_hash**: SHA-256 хэш устройства (для проверки)
    
    **Errors:**
    - 401 INVALID_TOKEN - токен невалиден
    - 403 DEVICE_DEACTIVATED - устройство деактивировано
    - 403 FINGERPRINT_MISMATCH - fingerprint не совпадает
    """
    service = LicenseService(db)
    return service.refresh_license(req.token, req.fingerprint_hash)


@router.post("/deactivate", response_model=dict, responses={
    401: {"model": ErrorResponse}
})
async def deactivate_device(
    req: DeactivateRequest,
    db: Session = Depends(get_db)
):
    """
    Деактивация устройства (освобождение слота).
    
    Идемпотентная операция - повторный вызов не приводит к ошибке.
    
    - **token**: Токен устройства
    
    **Errors:**
    - 401 INVALID_TOKEN - токен невалиден
    """
    service = LicenseService(db)
    return service.deactivate_device(req.token)
