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


# Константа отображаемых названий планов (для UI)
# Используется в license_dialog.py и settings_page.py
PLAN_DISPLAY_NAMES = {
    "monthly": "Месячная подписка",
    "quarterly": "Подписка на 3 месяца",
    "yearly": "Годовая подписка",
    "internal": "Внутренняя лицензия"
}


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
    - check_local_status() -> LicenseStatus  (быстрая локальная проверка)
    - verify_access_async(callback) -> None  (НОВОЕ в ЗАДАЧЕ 2: строгая проверка при старте)
    - activate(license_key) -> (success, error_message)
    - refresh_async(callback) -> None (в QThread, для runtime мониторинга)
    - deactivate_this_device() -> (success, error_message)
    - get_plan_info() -> dict | None
    - start_runtime_monitor(on_status_changed) -> QTimer
    """
    
    # Интервал runtime проверки лицензии (часы)
    RUNTIME_CHECK_INTERVAL_HOURS = 6
    
    def __init__(self):
        self.client = LicenseClient()
        self.token_path = self._get_token_path()
        self.fingerprint = get_device_fingerprint()
        
        # БАГ 1: Хранилище активных воркеров (предотвращает GC пока QThread работает)
        self._refresh_workers = set()
        # Хранилище для verify воркеров
        self._verify_workers = set()
        
        logger.info(f"[LicenseManager] Token path: {self.token_path}")
        logger.info(f"[LicenseManager] Fingerprint: {self.fingerprint[:16]}...")
    
    # ════════════════════════════════════════════════════════════════
    # Публичное API
    # ════════════════════════════════════════════════════════════════
    
    def check_local_status(self) -> LicenseStatus:
        """
        Проверить статус лицензии локально (офлайн, без сети).
        
        ВАЖНО (ЗАДАЧА 2): Этот метод больше НЕ используется для решения
        "можно ли запустить приложение". Он только для быстрой локальной
        проверки подписи и дат (защита от подделки, отката часов, явно
        истёкшей подписки).
        
        Для проверки доступа при старте используй verify_access_async().
        
        Логика:
        1. Проверить наличие файла токена
        2. Проверить подпись токена (Ed25519)
        3. Проверить current_period_end > now
        4. Защита от отката часов (issued_at > now)
        
        Returns:
            LicenseStatus (VALID, EXPIRED, REVOKED, NOT_ACTIVATED)
            Больше не возвращает GRACE_PERIOD.
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
                "Token will be rejected."
            )
            return LicenseStatus.EXPIRED
        
        # 5. Проверяем статус лицензии (может быть revoked/canceled с сервера)
        if status != "active":
            logger.warning(f"[LicenseManager] License status: {status}")
            return LicenseStatus.REVOKED
        
        # 6. Проверяем окончание подписки
        if current_period_end < now:
            logger.warning(f"[LicenseManager] License expired: {current_period_end} < {now}")
            return LicenseStatus.EXPIRED
        
        # Всё ОК локально
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
    
    def verify_access_async(self, on_result: Callable[[LicenseStatus, Optional[str]], None]) -> None:
        """
        Проверить доступ к приложению (ЗАДАЧА 2 - обязательная онлайн-проверка).
        
        Этот метод используется при СТАРТЕ приложения для строгой проверки:
        1. Если токена нет → NOT_ACTIVATED
        2. Если токен есть → быстрая локальная проверка (подпись, даты)
        3. ВСЕГДА пытается обратиться к серверу (refresh)
        4. Только успешный ответ сервера → VALID
        5. Сетевая ошибка → NETWORK_ERROR (блокирует запуск)
        
        Args:
            on_result: callback(status: LicenseStatus, error_msg: Optional[str])
        """
        worker = VerifyAccessWorker(self)
        
        # Сохраняем ссылку на воркер
        self._verify_workers.add(worker)
        
        def _cleanup_and_callback(status: LicenseStatus, error_msg: Optional[str]):
            """Wrapper который удаляет воркер после завершения."""
            on_result(status, error_msg)
            self._verify_workers.discard(worker)
            worker.deleteLater()
        
        worker.finished.connect(_cleanup_and_callback)
        worker.start()
    
    def refresh_async(self, on_done: Callable[[bool], None]) -> None:
        """
        Обновить токен лицензии асинхронно (в QThread).
        
        Не блокирует UI. Вызывает callback по завершении.
        
        Args:
            on_done: callback(success: bool)
        """
        worker = RefreshWorker(self)
        
        # БАГ 1: Сохраняем ссылку на воркер чтобы PyQt не собрал его GC
        self._refresh_workers.add(worker)
        
        def _cleanup_and_callback(success: bool):
            """Wrapper который удаляет воркер после завершения."""
            # Сначала вызываем пользовательский callback
            on_done(success)
            # Потом удаляем ссылку и планируем deleteLater
            self._refresh_workers.discard(worker)
            worker.deleteLater()
        
        worker.finished.connect(_cleanup_and_callback)
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
        
        # БАГ 3: передаём fingerprint для защиты
        response = self.client.deactivate(token_str, self.fingerprint)
        
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
    
    def start_runtime_monitor(self, on_status_changed: Callable[[LicenseStatus], None]):
        """
        Запускает QTimer, который каждые RUNTIME_CHECK_INTERVAL_HOURS часов
        асинхронно обновляет токен (refresh_async) и уведомляет
        on_status_changed новым статусом.
        
        Таймер должен быть создан ПОСЛЕ QApplication и жить пока живо главное окно.
        Вызывающий код отвечает за то, чтобы держать ссылку на QTimer
        (иначе Python GC его соберёт).
        
        Args:
            on_status_changed: callback(LicenseStatus) - вызывается при изменении статуса
        
        Returns:
            QTimer объект (сохраните ссылку на него!)
        """
        from PyQt6.QtCore import QTimer
        
        timer = QTimer()
        interval_ms = self.RUNTIME_CHECK_INTERVAL_HOURS * 60 * 60 * 1000
        timer.setInterval(interval_ms)
        
        def _tick():
            """Callback для таймера - проверяет лицензию асинхронно."""
            def _on_refresh_done(success: bool):
                # После refresh проверяем новый статус
                new_status = self.check_local_status()
                logger.info(f"[LicenseManager] Runtime check: status={new_status.value}, refresh_success={success}")
                on_status_changed(new_status)
            
            # Запускаем асинхронный refresh
            self.refresh_async(_on_refresh_done)
        
        timer.timeout.connect(_tick)
        timer.start()
        
        logger.info(f"[LicenseManager] Runtime monitor started (interval: {self.RUNTIME_CHECK_INTERVAL_HOURS}h)")
        
        return timer
    
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
    
    def _verify_access_internal(self) -> Tuple[LicenseStatus, Optional[str]]:
        """
        Внутренний метод проверки доступа (синхронный).
        Используется VerifyAccessWorker в QThread.
        
        ЗАДАЧА 2: Строгая проверка доступа при старте.
        
        Returns:
            (LicenseStatus, error_message)
        """
        # 1. Если токена нет вообще → сразу NOT_ACTIVATED
        token_data = self._load_token()
        if not token_data:
            logger.info("[LicenseManager] No token found, activation required")
            return LicenseStatus.NOT_ACTIVATED, None
        
        token_str = token_data.get("token")
        if not token_str:
            logger.info("[LicenseManager] Empty token, activation required")
            return LicenseStatus.NOT_ACTIVATED, None
        
        # 2. Быстрая локальная проверка (подпись, даты, откат часов)
        local_status = self.check_local_status()
        
        # Если локально токен явно невалиден (подделка, истёк, откат часов) → сразу отклоняем
        if local_status in (LicenseStatus.NOT_ACTIVATED, LicenseStatus.EXPIRED, LicenseStatus.REVOKED):
            logger.warning(f"[LicenseManager] Local check failed: {local_status.value}")
            return local_status, None
        
        # 3. Локально токен выглядит валидным → ОБЯЗАТЕЛЬНАЯ проверка с сервером
        logger.info("[LicenseManager] Local check passed, verifying with server...")
        
        response = self.client.refresh(
            current_token=token_str,
            fingerprint_hash=self.fingerprint
        )
        
        # 4. Обработка ответа сервера
        if response.success:
            # Сервер подтвердил активный статус → сохраняем обновлённый токен
            self._save_token(response.token)
            logger.info("[LicenseManager] Server verified license as VALID")
            return LicenseStatus.VALID, None
        
        # 5. Ошибки от сервера
        error_code = response.error_code or "UNKNOWN"
        error_msg = self._format_error_message(response)
        
        # Критические ошибки (лицензия реально проблемная) → удаляем токен
        if error_code in ("LICENSE_EXPIRED", "LICENSE_REVOKED", "INVALID_LICENSE", 
                          "DEVICE_DEACTIVATED", "FINGERPRINT_MISMATCH"):
            logger.warning(f"[LicenseManager] License rejected by server: {error_code}")
            self._delete_token()
            
            if error_code in ("LICENSE_EXPIRED", "DEVICE_DEACTIVATED"):
                return LicenseStatus.EXPIRED, error_msg
            elif error_code in ("LICENSE_REVOKED", "INVALID_LICENSE", "FINGERPRINT_MISMATCH"):
                return LicenseStatus.REVOKED, error_msg
        
        # Сетевые ошибки → NETWORK_ERROR (блокирует запуск)
        if error_code in ("TIMEOUT", "CONNECTION_ERROR"):
            logger.error(f"[LicenseManager] Network error during startup verification: {error_msg}")
            return LicenseStatus.NETWORK_ERROR, error_msg
        
        # Неизвестная ошибка → тоже считаем сетевой
        logger.error(f"[LicenseManager] Unknown error during verification: {error_msg}")
        return LicenseStatus.NETWORK_ERROR, error_msg
    
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


class VerifyAccessWorker(QThread):
    """Воркер для проверки доступа при старте (ЗАДАЧА 2)."""
    
    finished = pyqtSignal(object, object)  # status: LicenseStatus, error_msg: Optional[str]
    
    def __init__(self, manager: LicenseManager):
        super().__init__()
        self.manager = manager
    
    def run(self):
        """Выполняется в отдельном потоке."""
        try:
            status, error_msg = self.manager._verify_access_internal()
            self.finished.emit(status, error_msg)
        except Exception as e:
            logger.error(f"[VerifyAccessWorker] Error: {e}", exc_info=True)
            self.finished.emit(LicenseStatus.NETWORK_ERROR, str(e))
