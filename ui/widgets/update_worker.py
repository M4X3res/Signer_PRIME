"""
ui/widgets/update_worker.py
Асинхронные воркеры для проверки и загрузки обновлений в фоновом потоке.
По образцу VideoScanWorker и BackendVerifyThread.
"""
import logging
from pathlib import Path
from typing import Optional

from PyQt6.QtCore import QThread, pyqtSignal

import updater

logger = logging.getLogger(__name__)


class UpdateCheckWorker(QThread):
    """
    Фоновый поток для проверки обновлений через GitHub API.
    Не блокирует UI во время сетевого запроса.
    """
    
    finished_check = pyqtSignal(object)  # Несёт UpdateInfo | None
    error = pyqtSignal(str)
    
    def run(self):
        """Выполняет проверку обновлений."""
        try:
            logger.info("[UpdateCheckWorker] Проверка обновлений...")
            update_info = updater.check_for_update()
            self.finished_check.emit(update_info)
        except Exception as e:
            logger.error(f"[UpdateCheckWorker] Ошибка: {e}", exc_info=True)
            self.error.emit(f"Ошибка при проверке обновлений: {e}")


class UpdateDownloadWorker(QThread):
    """
    Фоновый поток для загрузки и проверки обновлений.
    Отправляет прогресс через сигналы.
    """
    
    progress = pyqtSignal(str, int, int, float)  # filename, downloaded, total, speed_bps
    finished_ok = pyqtSignal()
    checksum_failed = pyqtSignal()
    error = pyqtSignal(str)
    cancelled = pyqtSignal()  # Новый сигнал для отмены
    
    def __init__(self, update_info: updater.UpdateInfo, temp_dir: Path):
        super().__init__()
        self.update_info = update_info
        self.temp_dir = temp_dir
        self._cancel_flag = False  # Флаг отмены
    
    def cancel(self):
        """Отменяет загрузку."""
        logger.info("[UpdateDownloadWorker] Отмена загрузки...")
        self._cancel_flag = True
    
    def run(self):
        """Загружает обновление и проверяет чексуммы."""
        try:
            logger.info(f"[UpdateDownloadWorker] Загрузка обновления в {self.temp_dir}...")
            
            # Загрузка с callback для прогресса
            success = updater.download_assets(
                self.update_info.assets,
                self.temp_dir,
                progress_cb=self._on_progress,
                cancel_check=lambda: self._cancel_flag  # Передаём функцию проверки отмены
            )
            
            if self._cancel_flag:
                logger.info("[UpdateDownloadWorker] Загрузка отменена пользователем")
                self.cancelled.emit()
                return
            
            if not success:
                self.error.emit("Ошибка при скачивании файлов")
                return
            
            logger.info("[UpdateDownloadWorker] Проверка целостности...")
            
            # Для дельта-обновления нужно прочитать delta_manifest.json
            delta_manifest_data = None
            if self.update_info.is_delta:
                delta_manifest_path = self.temp_dir / "delta_manifest.json"
                if delta_manifest_path.exists():
                    import json
                    with open(delta_manifest_path, "r", encoding="utf-8") as f:
                        delta_manifest_data = json.load(f)
            
            # Проверка целостности
            if not updater.verify_downloaded_assets(
                self.temp_dir,
                self.update_info.is_delta,
                delta_manifest_data
            ):
                self.checksum_failed.emit()
                return
            
            logger.info("[UpdateDownloadWorker] Обновление успешно загружено и проверено")
            self.finished_ok.emit()
            
        except Exception as e:
            if not self._cancel_flag:  # Не показываем ошибку если отменено
                logger.error(f"[UpdateDownloadWorker] Ошибка: {e}", exc_info=True)
                self.error.emit(f"Ошибка при загрузке: {e}")
    
    def _on_progress(self, filename: str, downloaded: int, total: int, speed_bps: float):
        """Callback для прогресса загрузки."""
        if not self._cancel_flag:
            self.progress.emit(filename, downloaded, total, speed_bps)
