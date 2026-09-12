"""
licensing/license_manager.py
Основной менеджер лицензий: проверка, активация, refresh, grace period.
"""
import json
import logging
import os
import time
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Callable, Dict, Any

from PyQt6.QtCore import QThread, pyqtSignal

from .device_fingerprint import get_device_fingerprint, get_device_label
from .license_client import LicenseClient, LicenseResponse
from .public_key import verify_token

logger = logging.getLogger(__name__)


class LicenseStatus(Enum):
    """Статус лицензии."""
    VALID = "valid"                     # Токен валиден, подписка активна
    EXPIRED = "expired"                 # Подписка истекла (current_period_end < now)
    REVOKED = "revoked"                 # Лицензия отозвана (status != active)
    NOT_ACTIVATED = "not_activated"     # Токен отсутствует (первый запуск)
    GRACE_PERIOD = "grace_period"       # Токен просрочен для refresh, но в grace period
    NETWORK_ERROR = "network_error"     # Ошибка сети (для информирования UI)


class LicenseManager:
    """
    Менеджер лицензий.
    
    Публичное API:
    - check_local_status() -> LicenseStatus
    - activate(license_key) -> (success, error_message)
    - refresh_async(callback) -> None (в QThread)
    - deactivate_this_device() -> (success, error_message)
    - get_plan_info() -> dict | None
    """
    
    def __init__(self):
        self.client = LicenseClient()
        self.token_path = self._get_token_path()
        self.fingerprint = get_device_fingerprint()
        
        # Константы из settings.py
        from configs.settings import get_app_settings
        settings = get_app_settings()
        self.refresh_interval_days = settings.license_refresh_interval_days
        self.grace_period_days = settings.license_grace_period_days
        
        logger.info(f"[LicenseManager] Token path: {self.token_path}")
        logger.info(f"[LicenseManager] Fingerprint: {self.fingerprint[:16]}...")
    
    # ════════════════════════════════════════════════════════════════
    # Публичное API
    # ════════════════════════════════════════════════════════════════
    
    def check_local_status(self) -> LicenseStatus:
        """
        Проверить статус лицензии локально (офлайн, без сети).
        
        Логика:
        1. Проверить наличие файла токена
        2. Проверить подпись токена (Ed25519)
        3. Проверить current_period_end > now
        4. Проверить grace period (issued_at + grace_period_days)
        5. Защита от отката часов (issued_at > now)
        
        Returns:
            LicenseStatus
        """
        # 1. Проверяем наличие токена
        token_data = self._load_token()
        if not token_data:
            return LicenseStatus.NOT_ACTIVATED
        
        token_str = token_data.get("token")
        if not token_str:
            return LicenseStatus.NOT_ACTIVATED
        
        # 2. Верифицируем подпись
        valid, payload, error = verify_token(token_str)
        if not valid:
            logger.warning(f"[LicenseManager] Token signature invalid: {error}")
            self._delete_token()  # Удаляем невалидный токен
            return LicenseStatus.NOT_ACTIVATED
        
        # 3. Извлекаем данные
        status = payload.get("status")
        current_period_end = payload.get("current_period_end", 0)
        issued_at = payload.get("issued_at", 0)
        
        now = int(time.time())
        
        # 4. Защита от отката часов
        if now < issued_at:
            logger.warning(
                f"[LicenseManager] Clock rollback detected: now={now}, issued_at={issued_at}. "
                "Forcing online check."
            )
            # Форсируем онлайн-проверку (возвращаем EXPIRED чтобы диалог попросил переактивацию)
            # В реальном сценарии можно добавить спецстатус CLOCK_ROLLBACK
            return LicenseStatus.EXPIRED
        
        # 5. Проверяем статус лицензии (может быть revoked/canceled с сервера)
        if status != "active":
            logger.warning(f"[LicenseManager] License status: {status}")
            return LicenseStatus.REVOKED
        
        # 6. Проверяем окончание подписки
        if current_period_end < now:
            logger.warning(f"[LicenseManager] License expired: {current_period_end} < {now}")
            return LicenseStatus.EXPIRED
        
        # 7. Проверяем grace period для refresh
        days_since_issue = (now - issued_at) / 86400
        
        if days_since_issue > self.grace_period_days:
            logger.warning(
                f"[LicenseManager] Grace period exceeded: {days_since_issue:.1f} > {self.grace_period_days} days"
            )
            # Требуется онлайн-проверка
            return LicenseStatus.EXPIRED
        
        # 8. Если прошло больше refresh_interval_days, но ещё в grace period
        if days_since_issue > self.refresh_interval_days:
            logger.info(
                f"[LicenseManager] In grace period: {days_since_issue:.1f} days since issue "
                f"(refresh interval: {self.refresh_interval_days})"
            )
            return LicenseStatus.GRACE_PERIOD
        
        # Всё ОК
        return LicenseStatus.VALID
    
    def activate(self, license_key: str) -> Tuple[bool, str]:
        """
        Активировать лицензию на этом устройстве.
        
        Args:
            license_key: ключ лицензии (формат SGNR-XXXX-XXXX-XXXX-XXXX)
        
        Returns:
            (success, error_message)
        """
        # Получаем версию приложения
        try:
            from app.version import get_version
            app_version = get_version()
        except Exception:
            app_version = "unknown"
        
        device_label = get_device_label()
        
        logger.info(f"[LicenseManager] Activating license: {license_key[:10]}...")
        
        # Запрос к серверу
        response = self.client.activate(
            license_key=license_key,
            fingerprint_hash=self.fingerprint,
            device_label=device_label,
            app_version=app_version
        )
        
        if not response.success:
            error_msg = self._format_error_message(response)
            return False, error_msg
        
        # Сохраняем токен
        self._save_token(response.token)
        logger.info("[LicenseManager] License activated successfully")
        
        return True, ""
    
    def refresh_async(self, on_done: Callable[[bool], None]) -> None:
        """
        Обновить токен лицензии асинхронно (в QThread).
        
        Не блокирует UI. Вызывает callback по завершении.
        
        Args:
            on_done: callback(success: bool)
        """
        worker = RefreshWorker(self)
        worker.finished.connect(on_done)
        worker.start()
    
    def deactivate_this_device(self) -> Tuple[bool, str]:
        """
        Деактивировать это устройство (освободить слот).
        
        Returns:
            (success, error_message)
        """
        token_data = self._load_token()
        if not token_data:
            return False, "No active license found"
        
        token_str = token_data.get("token")
        if not token_str:
            return False, "No active license found"
        
        logger.info("[LicenseManager] Deactivating this device...")
        
        response = self.client.deactivate(token_str)
        
        if not response.success:
            error_msg = self._format_error_message(response)
            return False, error_msg
        
        # Удаляем локальный токен
        self._delete_token()
        logger.info("[LicenseManager] Device deactivated successfully")
        
        return True, ""
    
    def get_plan_info(self) -> Optional[Dict[str, Any]]:
        """
        Получить информацию о плане (для UI).
        
        Returns:
            {
                "plan": "monthly" | "quarterly" | "yearly",
                "current_period_end": unix_timestamp,
                "license_key": "SGNR-...",
                "issued_at": unix_timestamp
            }
            или None если токен отсутствует/невалиден.
        """
        token_data = self._load_token()
        if not token_data:
            return None
        
        token_str = token_data.get("token")
        if not token_str:
            return None
        
        valid, payload, error = verify_token(token_str)
        if not valid:
            return None
        
        return {
            "plan": payload.get("plan"),
            "current_period_end": payload.get("current_period_end"),
            "license_key": payload.get("license_key"),
            "issued_at": payload.get("issued_at")
        }
    
    # ════════════════════════════════════════════════════════════════
    # Внутренние методы
    # ════════════════════════════════════════════════════════════════
    
    def _get_token_path(self) -> Path:
        """Путь к файлу токена."""
        # %LOCALAPPDATA%\Signer\license.token
        appdata = os.environ.get("LOCALAPPDATA")
        if not appdata:
            # Fallback (не должно случиться на Windows)
            appdata = str(Path.home() / "AppData" / "Local")
        
        token_dir = Path(appdata) / "Signer"
        token_dir.mkdir(parents=True, exist_ok=True)
        
        return token_dir / "license.token"
    
    def _load_token(self) -> Optional[Dict[str, Any]]:
        """Загрузить токен из файла."""
        if not self.token_path.exists():
            return None
        
        try:
            with open(self.token_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            logger.error(f"[LicenseManager] Error loading token: {e}")
            return None
    
    def _save_token(self, token_str: str) -> None:
        """Сохранить токен в файл."""
        try:
            data = {"token": token_str}
            with open(self.token_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            
            logger.info(f"[LicenseManager] Token saved to {self.token_path}")
        except Exception as e:
            logger.error(f"[LicenseManager] Error saving token: {e}")
    
    def _delete_token(self) -> None:
        """Удалить файл токена."""
        try:
            if self.token_path.exists():
                self.token_path.unlink()
                logger.info(f"[LicenseManager] Token deleted: {self.token_path}")
        except Exception as e:
            logger.error(f"[LicenseManager] Error deleting token: {e}")
    
    def _format_error_message(self, response: LicenseResponse) -> str:
        """Форматировать сообщение об ошибке для пользователя."""
        error_code = response.error_code or "UNKNOWN"
        error_msg = response.error_message or "Unknown error"
        
        # Человекочитаемые сообщения для известных кодов
        error_texts = {
            "DEVICE_LIMIT_REACHED": (
                "Device limit reached. You have reached the maximum number of devices "
                "for this license. Please deactivate one of your devices in your account "
                "or contact support."
            ),
            "INVALID_LICENSE": "Invalid license key. Please check and try again.",
            "LICENSE_EXPIRED": "Your subscription has expired. Please renew to continue.",
            "LICENSE_REVOKED": "This license has been revoked. Please contact support.",
            "TIMEOUT": "Server did not respond in time. Please check your internet connection.",
            "CONNECTION_ERROR": "Could not connect to license server. Please check your internet connection.",
        }
        
        return error_texts.get(error_code, f"{error_code}: {error_msg}")
    
    def _refresh_internal(self) -> bool:
        """
        Внутренний метод обновления токена (синхронный).
        Используется RefreshWorker в QThread.
        
        Returns:
            True если успешно обновлено.
        """
        token_data = self._load_token()
        if not token_data:
            logger.warning("[LicenseManager] No token to refresh")
            return False
        
        token_str = token_data.get("token")
        if not token_str:
            logger.warning("[LicenseManager] No token to refresh")
            return False
        
        logger.info("[LicenseManager] Refreshing license token...")
        
        response = self.client.refresh(
            current_token=token_str,
            fingerprint_hash=self.fingerprint
        )
        
        if not response.success:
            error_msg = self._format_error_message(response)
            logger.warning(f"[LicenseManager] Refresh failed: {error_msg}")
            
            # Если сервер вернул revoked/expired/canceled — удаляем токен
            if response.error_code in ("LICENSE_EXPIRED", "LICENSE_REVOKED", "INVALID_LICENSE"):
                self._delete_token()
            
            return False
        
        # Сохраняем новый токен
        self._save_token(response.token)
        logger.info("[LicenseManager] License token refreshed successfully")
        
        return True


# ════════════════════════════════════════════════════════════════
# QThread Worker для асинхронного refresh
# ════════════════════════════════════════════════════════════════

class RefreshWorker(QThread):
    """Воркер для обновления токена в фоне."""
    
    finished = pyqtSignal(bool)  # success: bool
    
    def __init__(self, manager: LicenseManager):
        super().__init__()
        self.manager = manager
    
    def run(self):
        """Выполняется в отдельном потоке."""
        try:
            success = self.manager._refresh_internal()
            self.finished.emit(success)
        except Exception as e:
            logger.error(f"[RefreshWorker] Error: {e}", exc_info=True)
            self.finished.emit(False)
