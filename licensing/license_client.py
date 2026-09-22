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
except ImportError:
    raise ImportError(
        "requests library is required for license verification. "
        "Install it with: pip install requests"
    )

from configs.settings import get_app_settings

logger = logging.getLogger(__name__)

# ════════════════════════════════════════════════════════════════
# Константы
# ════════════════════════════════════════════════════════════════

REQUEST_TIMEOUT = 8.0  # секунды (как в промпте)


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
        self.settings = get_app_settings()
        self.base_url = self.settings.license_server_url.rstrip('/')
    
    def _post_with_retry(self, url: str, payload: dict) -> 'requests.Response':
        """Retry connection failures and transient HTTP errors within one budget.

        Definite license rejections (4xx other than 408/429) are not retried.
        The same policy applies at startup and to checks during work.
        """
        import time
        
        attempts = max(1, min(3, int(self.settings.license_connect_retry_attempts)))
        backoff = max(0.0, min(1.5, float(self.settings.license_connect_retry_backoff_sec)))
        
        last_exception = None
        
        for attempt in range(attempts):
            try:
                response = requests.post(
                    url,
                    json=payload,
                    timeout=REQUEST_TIMEOUT,
                    headers={"Content-Type": "application/json"}
                )
                if response.status_code in (408, 429) or 500 <= response.status_code < 600:
                    if attempt < attempts - 1:
                        logger.warning('License server HTTP %s; retry %s/%s',
                                       response.status_code, attempt + 2, attempts)
                        response.close()
                        time.sleep(backoff)
                        continue
                return response
                
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
                last_exception = e
                
                if attempt < attempts - 1:  # Не последняя попытка
                    # Используем ФИКСИРОВАННЫЙ backoff (не экспоненциальный),
                    # чтобы не превысить разумный общий бюджет ~25 секунд
                    # (3 попытки × 8с таймаут + 2 задержки × 1.5с = ~27с)
                    logger.warning(
                        f"[LicenseClient] Попытка {attempt + 1}/{attempts} не удалась: {e}, "
                        f"повтор через {backoff:.1f}с"
                    )
                    time.sleep(backoff)
                else:
                    # Последняя попытка исчерпана
                    logger.warning(
                        f"[LicenseClient] Все {attempts} попытки подключения исчерпаны: {e}"
                    )
            
            except Exception as e:
                # Другие ошибки (например JSONDecodeError) — пробрасываем сразу без повторов
                logger.error(f"[LicenseClient] Неожиданная ошибка (не ретраим): {e}")
                raise
        
        # Если дошли сюда — все попытки исчерпаны, пробрасываем последнее исключение
        raise last_exception
    
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
        try:
            url = f"{self.base_url}/api/license/activate"
            payload = {
                "license_key": license_key,
                "fingerprint_hash": fingerprint_hash,
                "device_label": device_label,
                "app_version": app_version
            }
            
            logger.info(f"[LicenseClient] Activating license: {license_key[:10]}...")
            
            # ЗАДАЧА 2: используем _post_with_retry вместо прямого requests.post
            response = self._post_with_retry(url, payload)
            
            data = response.json()
            # FastAPI HTTPException wraps structured errors in detail.
            if isinstance(data, dict) and isinstance(data.get("detail"), dict):
                data = data["detail"]
            
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
            logger.warning("[LicenseClient] Activation request timeout (after retries)")
            return LicenseResponse(
                success=False,
                error_code="TIMEOUT",
                error_message="Server did not respond in time. Check your internet connection."
            )
        
        except requests.exceptions.ConnectionError:
            logger.warning("[LicenseClient] Activation connection error (after retries)")
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
        try:
            url = f"{self.base_url}/api/license/refresh"
            payload = {
                "token": current_token,
                "fingerprint_hash": fingerprint_hash
            }
            
            logger.info("[LicenseClient] Refreshing license token...")
            
            # ЗАДАЧА 2: используем _post_with_retry
            response = self._post_with_retry(url, payload)
            
            data = response.json()
            # FastAPI HTTPException wraps structured errors in detail.
            if isinstance(data, dict) and isinstance(data.get("detail"), dict):
                data = data["detail"]
            
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
            logger.warning("[LicenseClient] Refresh request timeout (after retries)")
            return LicenseResponse(
                success=False,
                error_code="TIMEOUT",
                error_message="Server did not respond in time"
            )
        
        except requests.exceptions.ConnectionError:
            logger.warning("[LicenseClient] Refresh connection error (after retries)")
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
    
    def deactivate(self, current_token: str, fingerprint_hash: str) -> LicenseResponse:
        """
        Деактивировать это устройство (освободить слот).
        
        БАГ 3: Теперь требует fingerprint_hash для защиты.
        
        Args:
            current_token: текущий токен
            fingerprint_hash: SHA-256 хэш устройства
        
        Returns:
            LicenseResponse с результатом.
        """
        try:
            url = f"{self.base_url}/api/license/deactivate"
            payload = {
                "token": current_token,
                "fingerprint_hash": fingerprint_hash  # БАГ 3: передаём fingerprint
            }
            
            logger.info("[LicenseClient] Deactivating device...")
            
            # ЗАДАЧА 2: используем _post_with_retry
            response = self._post_with_retry(url, payload)
            
            data = response.json()
            # FastAPI HTTPException wraps structured errors in detail.
            if isinstance(data, dict) and isinstance(data.get("detail"), dict):
                data = data["detail"]
            
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
