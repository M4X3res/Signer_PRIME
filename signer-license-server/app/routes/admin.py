"""
app/routes/admin.py
Admin API для ручного управления лицензиями.
"""
import logging
import secrets
import uuid
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.schemas import CreateLicenseRequest, CreateLicenseResponse
from app.crypto import generate_license_key
from app.models import License

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])


def verify_admin_key(x_admin_key: str = Header(...)) -> None:
    """Проверка admin API ключа (защита от timing-атак)."""
    settings = get_settings()
    
    if not settings.admin_api_key:
        raise HTTPException(status_code=500, detail="Admin API not configured")
    
    # secrets.compare_digest защищает от timing-атак
    if not secrets.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=403, detail="Invalid admin key")


@router.post("/licenses", response_model=CreateLicenseResponse)
async def create_license(
    req: CreateLicenseRequest,
    db: Session = Depends(get_db),
    _admin: None = Depends(verify_admin_key)
):
    """
    Создать лицензию вручную (требует X-Admin-Key заголовок).
    
    **Параметры:**
    - **plan**: monthly | quarterly | yearly
    - **duration_days**: длительность в днях (1-3650)
    - **max_devices**: максимум устройств (1-10, default=2)
    
    **Headers:**
    - **X-Admin-Key**: Admin API ключ (из ADMIN_API_KEY env var)
    
    **Пример:**
    ```bash
    curl -X POST http://localhost:8000/api/admin/licenses \
      -H "X-Admin-Key: your_admin_key" \
      -H "Content-Type: application/json" \
      -d '{"plan": "monthly", "duration_days": 30, "max_devices": 2}'
    ```
    """
    logger.info(f"Creating license: plan={req.plan}, duration={req.duration_days}d, max_devices={req.max_devices}")
    
    # Генерация уникального ключа
    license_key = generate_license_key()
    
    # Вычисление даты истечения
    current_period_end = datetime.utcnow() + timedelta(days=req.duration_days)
    
    # Создание лицензии в БД
    license_obj = License(
        id=uuid.uuid4(),
        license_key=license_key,
        plan=req.plan,
        status="active",
        current_period_end=current_period_end,
        max_devices=req.max_devices,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow()
    )
    
    db.add(license_obj)
    
    try:
        db.commit()
        logger.info(f"✅ License created: {license_key}")
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to create license: {e}")
        raise HTTPException(status_code=500, detail="Failed to create license")
    
    return CreateLicenseResponse(
        license_key=license_key,
        plan=req.plan,
        expires_at=int(current_period_end.timestamp()),
        max_devices=req.max_devices
    )
