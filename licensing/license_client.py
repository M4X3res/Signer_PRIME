"""
licensing/license_client.py
HTTP-клиент для общения с сервером лицензий.
Все запросы выполняются с таймаутом и обработкой ошибок.
"""
import logging
from typing import Tuple, Optional, Dict, Any
from dataclasses import dataclass

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False
    requests = None

from configs.settings import get_app_settings

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# Константы
# ════════════════════════════════════════════════════════════════

REQUEST_TIMEOUT = 8.0  # секунды (как в промпте)

# Моковый режим для разработки без сервера
LICENSE_MOCK_MODE = True  # Установить False для продакшна с реальным сервером


@dataclass
class LicenseResponse:
    """Ответ от сервера лицензий."""
    success: bool
    token: Optional[str] = None
    plan: Optional[str] = None
    current_period_end: Optional[int] = None  # unix timestamp
    error_code: Optional[str] = None
    error_message: Optional[str] = None


class LicenseClient:
    """HTTP-клиент для сервера лицензий."""
    
    def __init__(self):
        if not REQUESTS_AVAILABLE:
            logger.error("[LicenseClient] requests library not installed")
        
        self.settings = get_app_settings()
        self.base_url = self.settings.license_server_url.rstrip('/')
    
    def activate(
        self,
        license_key: str,
        fingerprint_hash: str,
        device_label: str,
        app_version: str
    ) -> LicenseResponse:
        """
        Активировать лицензию на этом устройстве.
        
        Args:
            license_key: ключ лицензии (формат SGNR-XXXX-XXXX-XXXX-XXXX)
            fingerprint_hash: SHA-256 хэш устройства
            device_label: имя устройства (hostname)
            app_version: версия приложения
        
        Returns:
            LicenseResponse с токеном или ошибкой.
        """
        if LICENSE_MOCK_MODE:
            return self._mock_activate(license_key, fingerprint_hash)
        
        if not REQUESTS_AVAILABLE:
            return LicenseResponse(
                success=False,
                error_code="NO_REQUESTS",
                error_message="requests library not installed"
            )
        
        try:
            url = f"{self.base_url}/api/license/activate"
            payload = {
                "license_key": license_key,
                "fingerprint_hash": fingerprint_hash,
                "device_label": device_label,
                "app_version": app_version
            }
            
            logger.info(f"[LicenseClient] Activating license: {license_key[:10]}...")
            
            response = requests.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"}
            )
            
            data = response.json()
            
            if response.status_code == 200:
                return LicenseResponse(
                    success=True,
                    token=data.get("token"),
                    plan=data.get("plan"),
                    current_period_end=data.get("current_period_end")
                )
            else:
                error_code = data.get("error_code", "UNKNOWN")
                error_message = data.get("error", "Unknown error")
                logger.warning(f"[LicenseClient] Activation failed: {error_code} - {error_message}")
                return LicenseResponse(
                    success=False,
                    error_code=error_code,
                    error_message=error_message
                )
        
        except requests.exceptions.Timeout:
            logger.warning("[LicenseClient] Activation request timeout")
            return LicenseResponse(
                success=False,
                error_code="TIMEOUT",
                error_message="Server did not respond in time. Check your internet connection."
            )
        
        except requests.exceptions.ConnectionError:
            logger.warning("[LicenseClient] Activation connection error")
            return LicenseResponse(
                success=False,
                error_code="CONNECTION_ERROR",
                error_message="Could not connect to license server. Check your internet connection."
            )
        
        except Exception as e:
            logger.error(f"[LicenseClient] Activation error: {e}", exc_info=True)
            return LicenseResponse(
                success=False,
                error_code="UNKNOWN",
                error_message=f"Unexpected error: {e}"
            )
    
    def refresh(
        self,
        current_token: str,
        fingerprint_hash: str
    ) -> LicenseResponse:
        """
        Обновить токен лицензии (получить актуальный статус).
        
        Args:
            current_token: текущий токен
            fingerprint_hash: SHA-256 хэш устройства
        
        Returns:
            LicenseResponse с новым токеном или ошибкой.
        """
        if LICENSE_MOCK_MODE:
            return self._mock_refresh(current_token)
        
        if not REQUESTS_AVAILABLE:
            return LicenseResponse(
                success=False,
                error_code="NO_REQUESTS",
                error_message="requests library not installed"
            )
        
        try:
            url = f"{self.base_url}/api/license/refresh"
            payload = {
                "token": current_token,
                "fingerprint_hash": fingerprint_hash
            }
            
            logger.info("[LicenseClient] Refreshing license token...")
            
            response = requests.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"}
            )
            
            data = response.json()
            
            if response.status_code == 200:
                return LicenseResponse(
                    success=True,
                    token=data.get("token"),
                    plan=data.get("plan"),
                    current_period_end=data.get("current_period_end")
                )
            else:
                error_code = data.get("error_code", "UNKNOWN")
                error_message = data.get("error", "Unknown error")
                logger.warning(f"[LicenseClient] Refresh failed: {error_code} - {error_message}")
                return LicenseResponse(
                    success=False,
                    error_code=error_code,
                    error_message=error_message
                )
        
        except requests.exceptions.Timeout:
            logger.warning("[LicenseClient] Refresh request timeout")
            return LicenseResponse(
                success=False,
                error_code="TIMEOUT",
                error_message="Server did not respond in time"
            )
        
        except requests.exceptions.ConnectionError:
            logger.warning("[LicenseClient] Refresh connection error")
            return LicenseResponse(
                success=False,
                error_code="CONNECTION_ERROR",
                error_message="Could not connect to license server"
            )
        
        except Exception as e:
            logger.error(f"[LicenseClient] Refresh error: {e}", exc_info=True)
            return LicenseResponse(
                success=False,
                error_code="UNKNOWN",
                error_message=f"Unexpected error: {e}"
            )
    
    def deactivate(self, current_token: str) -> LicenseResponse:
        """
        Деактивировать это устройство (освободить слот).
        
        Args:
            current_token: текущий токен
        
        Returns:
            LicenseResponse с результатом.
        """
        if LICENSE_MOCK_MODE:
            return LicenseResponse(success=True)
        
        if not REQUESTS_AVAILABLE:
            return LicenseResponse(
                success=False,
                error_code="NO_REQUESTS",
                error_message="requests library not installed"
            )
        
        try:
            url = f"{self.base_url}/api/license/deactivate"
            payload = {"token": current_token}
            
            logger.info("[LicenseClient] Deactivating device...")
            
            response = requests.post(
                url,
                json=payload,
                timeout=REQUEST_TIMEOUT,
                headers={"Content-Type": "application/json"}
            )
            
            data = response.json()
            
            if response.status_code == 200:
                return LicenseResponse(success=True)
            else:
                error_code = data.get("error_code", "UNKNOWN")
                error_message = data.get("error", "Unknown error")
                logger.warning(f"[LicenseClient] Deactivation failed: {error_code} - {error_message}")
                return LicenseResponse(
                    success=False,
                    error_code=error_code,
                    error_message=error_message
                )
        
        except Exception as e:
            logger.error(f"[LicenseClient] Deactivation error: {e}", exc_info=True)
            return LicenseResponse(
                success=False,
                error_code="UNKNOWN",
                error_message=f"Unexpected error: {e}"
            )
    
    # ════════════════════════════════════════════════════════════════
    # Мок-режим для разработки
    # ════════════════════════════════════════════════════════════════
    
    def _mock_activate(self, license_key: str, fingerprint_hash: str) -> LicenseResponse:
        """Мок: всегда успешная активация."""
        import time
        import json
        import base64
        
        logger.info("[LicenseClient MOCK] Activating (mock mode)...")
        
        # Генерируем фиктивный валидный токен
        payload = {
            "license_key": license_key,
            "device_id": fingerprint_hash[:16],
            "plan": "monthly",
            "status": "active",
            "current_period_end": int(time.time()) + 30 * 86400,  # +30 дней
            "issued_at": int(time.time())
        }
        
        payload_json = json.dumps(payload, sort_keys=True)
        payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
        # Фиктивная подпись (НЕ валидна для настоящего публичного ключа)
        signature_b64 = base64.urlsafe_b64encode(b"mock_signature_12345").decode().rstrip('=')
        
        mock_token = f"{payload_b64}.{signature_b64}"
        
        return LicenseResponse(
            success=True,
            token=mock_token,
            plan="monthly",
            current_period_end=payload["current_period_end"]
        )
    
    def _mock_refresh(self, current_token: str) -> LicenseResponse:
        """Мок: всегда успешное обновление."""
        import time
        import json
        import base64
        
        logger.info("[LicenseClient MOCK] Refreshing (mock mode)...")
        
        # Декодируем текущий токен и обновляем даты
        try:
            payload_b64 = current_token.split(".")[0]
            padding = 4 - (len(payload_b64) % 4)
            if padding != 4:
                payload_b64 += '=' * padding
            payload_json = base64.urlsafe_b64decode(payload_b64.replace('-', '+').replace('_', '/')).decode()
            payload = json.loads(payload_json)
            
            # Обновляем даты
            payload["current_period_end"] = int(time.time()) + 30 * 86400
            payload["issued_at"] = int(time.time())
            
            payload_json = json.dumps(payload, sort_keys=True)
            payload_b64 = base64.urlsafe_b64encode(payload_json.encode()).decode().rstrip('=')
            signature_b64 = base64.urlsafe_b64encode(b"mock_signature_12345").decode().rstrip('=')
            
            mock_token = f"{payload_b64}.{signature_b64}"
            
            return LicenseResponse(
                success=True,
                token=mock_token,
                plan=payload["plan"],
                current_period_end=payload["current_period_end"]
            )
        except Exception as e:
            logger.error(f"[LicenseClient MOCK] Error parsing token: {e}")
            return LicenseResponse(
                success=False,
                error_code="INVALID_TOKEN",
                error_message="Mock refresh failed"
            )
