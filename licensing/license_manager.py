"""
licensing/license_manager.py
Онлайн-проверка лицензии при запуске, ключевых действиях и каждые пять минут.
"""
import json
import logging
import os
import time
import tempfile
import threading
from enum import Enum
from pathlib import Path
from typing import Optional, Tuple, Callable, Dict, Any

from PyQt6.QtCore import QObject, QThread, pyqtSignal, pyqtSlot

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
    NETWORK_ERROR = "network_error"     # Ошибка сети (для информирования UI)


class LicenseManager(QObject):
    """
    Менеджер лицензий.
    
    Публичное API:
    - check_local_status() -> LicenseStatus  (быстрая локальная проверка)
    - verify_access_async(callback) -> None  (НОВОЕ в ЗАДАЧЕ 2: строгая проверка при старте)
    - activate(license_key) -> (success, error_message)
    - refresh_async(callback) -> None (в QThread, для runtime мониторинга)
    - deactivate_this_device() -> (success, error_message)
    - get_plan_info() -> dict | None
    """
    
    access_changed = pyqtSignal(object)
    
    def __init__(self):
        super().__init__()
        self._verification_lock = threading.RLock()
        self._online_until = 0.0
        self._access_status = LicenseStatus.NOT_ACTIVATED
        self._verify_callbacks = []
        self._verify_running = False
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
        
        return self._payload_status(payload)

    def _payload_status(self, payload) -> LicenseStatus:
        if not isinstance(payload, dict):
            return LicenseStatus.NOT_ACTIVATED
        if any(type(payload.get(key)) is not int for key in ('issued_at', 'current_period_end')):
            return LicenseStatus.NOT_ACTIVATED
        if not payload.get('license_key') or not payload.get('device_id'):
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
        if current_period_end <= now:
            logger.warning(f"[LicenseManager] License expired: {current_period_end} < {now}")
            return LicenseStatus.EXPIRED
        
        # Всё ОК локально
        return LicenseStatus.VALID

    def has_online_access(self) -> bool:
        return (self._access_status == LicenseStatus.VALID and
                time.monotonic() < self._online_until)

    def _record_access(self, status):
        self._access_status = status
        if status != LicenseStatus.VALID:
            self._online_until = 0.0
        self.access_changed.emit(status)

    def _accept_server_token(self, token):
        if not isinstance(token, str) or not token:
            raise ValueError('Сервер не прислал токен лицензии')
        valid, payload, error = verify_token(token)
        if not valid or self._payload_status(payload) != LicenseStatus.VALID:
            raise ValueError('Сервер прислал недействительный токен лицензии')
        self._save_token(token)
        self._online_until = time.monotonic() + max(0, payload['current_period_end'] - time.time())
    
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
        
        try:
            with self._verification_lock:
                self._accept_server_token(response.token)
                self._record_access(LicenseStatus.VALID)
        except (ValueError, OSError) as error:
            self._record_access(LicenseStatus.NETWORK_ERROR)
            return False, str(error)
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
        self._verify_callbacks.append(on_result)
        if self._verify_running:
            return
        self._verify_running = True
        worker = VerifyAccessWorker(self)
        
        # Сохраняем ссылку на воркер
        self._verify_workers.add(worker)
        
        worker.result.connect(self._deliver_verification)
        worker.finished.connect(self._release_verify_worker)
        worker.start()

    @pyqtSlot(object, object)
    def _deliver_verification(self, status, error):
        self._verify_running = False
        callbacks, self._verify_callbacks = self._verify_callbacks, []
        for callback in callbacks:
            try:
                callback(status, error)
            except Exception:
                logger.exception('License verification callback failed')

    @pyqtSlot()
    def _release_verify_worker(self):
        worker = self.sender()
        self._verify_workers.discard(worker)
        worker.deleteLater()
    
    def refresh_async(self, on_done: Callable[[bool], None]) -> None:
        """
        Обновить токен лицензии асинхронно (в QThread).
        
        Не блокирует UI. Вызывает callback по завершении.
        
        Args:
            on_done: callback(success: bool)
        """
        self.verify_access_async(lambda status, error: on_done(status == LicenseStatus.VALID))

    def deactivate_this_device(self) -> Tuple[bool, str]:
        with self._verification_lock:
            return self._deactivate_locked()

    def _deactivate_locked(self) -> Tuple[bool, str]:
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
        self._record_access(LicenseStatus.NOT_ACTIVATED)
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
        if not valid or not isinstance(payload, dict):
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
            return data if isinstance(data, dict) else None
        except Exception as e:
            logger.error(f"[LicenseManager] Error loading token: {e}")
            return None
    
    def _save_token(self, token_str: str) -> None:
        """Сохранить токен в файл."""
        fd, name = tempfile.mkstemp(prefix='license-', suffix='.tmp', dir=self.token_path.parent)
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as stream:
                json.dump({'token': token_str}, stream)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.token_path)
        finally:
            Path(name).unlink(missing_ok=True)
    
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
        with self._verification_lock:
            try:
                status, error = self._verify_access_locked()
            except Exception as exc:
                logger.exception('License verification failed')
                status, error = LicenseStatus.NETWORK_ERROR, str(exc)
            self._record_access(status)
            return status, error

    def _verify_access_locked(self) -> Tuple[LicenseStatus, Optional[str]]:
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
            self._accept_server_token(response.token)
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
        status, _ = self._verify_access_internal()
        return status == LicenseStatus.VALID


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
    
    result = pyqtSignal(object, object)
    
    def __init__(self, manager: LicenseManager):
        super().__init__()
        self.manager = manager
    
    def run(self):
        """Выполняется в отдельном потоке."""
        try:
            status, error_msg = self.manager._verify_access_internal()
            self.result.emit(status, error_msg)
        except Exception as e:
            logger.error(f"[VerifyAccessWorker] Error: {e}", exc_info=True)
            self.result.emit(LicenseStatus.NETWORK_ERROR, str(e))
