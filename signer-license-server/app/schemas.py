"""
app/schemas.py
Pydantic схемы для валидации запросов и ответов.
"""
from pydantic import BaseModel, Field


class ActivateRequest(BaseModel):
    """Запрос активации лицензии."""
    license_key: str = Field(..., min_length=20, max_length=32)
    fingerprint_hash: str = Field(..., min_length=64, max_length=64)
    device_label: str = Field(..., max_length=128)
    app_version: str = Field(..., max_length=32)


class RefreshRequest(BaseModel):
    """Запрос обновления токена."""
    token: str = Field(..., min_length=10)
    fingerprint_hash: str = Field(..., min_length=64, max_length=64)


class DeactivateRequest(BaseModel):
    """Запрос деактивации устройства."""
    token: str = Field(..., min_length=10)


class LicenseResponse(BaseModel):
    """Ответ с токеном лицензии."""
    token: str
    plan: str
    current_period_end: int


class ErrorResponse(BaseModel):
    """Ответ с ошибкой."""
    error_code: str
    error: str


class CreateLicenseRequest(BaseModel):
    """Запрос создания лицензии (admin)."""
    plan: str = Field(..., pattern="^(monthly|quarterly|yearly)$")
    duration_days: int = Field(..., gt=0, le=3650)
    max_devices: int = Field(default=2, gt=0, le=10)


class CreateLicenseResponse(BaseModel):
    """Ответ с созданной лицензией."""
    license_key: str
    plan: str
    expires_at: int
    max_devices: int
