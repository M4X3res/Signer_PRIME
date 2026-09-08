"""
processing/ocr_worker.py
Отдельный поток для OCR обработки знаков.
Устраняет провалы FPS при обработке текстовых знаков.
"""
import queue
import logging
from dataclasses import dataclass
from typing import Optional
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from configs.sign_data import TYPE_SIGNS_WITH_TEXT, NAME_SIGNS_CITY  # BLOCK FIX-1.2: было sign_config

logger = logging.getLogger(__name__)


@dataclass
class OCRTask:
    """Задача для OCR обработки."""
    sign_id: int           # Уникальный ID знака для сопоставления результата
    frame_number: int      # Номер кадра (для ordering)
    crop: np.ndarray       # Вырезанное изображение знака
    cnn_class: str         # Класс знака для определения типа OCR
    yolo_class: str        # YOLO класс


@dataclass
class OCRResult:
    """Результат OCR обработки."""
    sign_id: int
    frame_number: int
    text: str


class OCRWorkerThread(QThread):
    """
    Поток для асинхронной OCR обработки.
    Работает параллельно с основным DetectorThread.
    """
    
    result_ready = pyqtSignal(object)  # OCRResult
    error = pyqtSignal(str)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self._task_queue = queue.Queue(maxsize=50)  # Ограничиваем очередь
        self._stop = False
        self._ocr_reader = None
        
    def submit_task(self, task: OCRTask, timeout: float = 0.1) -> bool:
        """
        Отправить задачу на OCR обработку.
        
        Returns:
            True если задача добавлена, False если очередь полна
        """
        try:
            self._task_queue.put(task, timeout=timeout)
            return True
        except queue.Full:
            logger.warning(f"[OCRWorker] Очередь переполнена, пропускаем sign_id={task.sign_id}")
            return False
    
    def stop(self):
        """Остановить поток."""
        self._stop = True
        # Добавляем sentinel чтобы разблокировать get()
        try:
            self._task_queue.put(None, timeout=0.1)
        except queue.Full:
            pass
    
    def run(self):
        """Основной цикл обработки OCR задач."""
        logger.info("[OCRWorker] Поток запущен")
        
        # Инициализируем OCR внутри потока
        try:
            from core.detector import _get_ocr
            self._ocr_reader = _get_ocr()
            logger.info("[OCRWorker] ✅ EasyOCR инициализирован")
        except Exception as e:
            logger.error(f"[OCRWorker] ❌ Ошибка инициализации EasyOCR: {e}")
            self.error.emit(f"OCR initialization failed: {e}")
            return
        
        processed_count = 0
        
        while not self._stop:
            try:
                task = self._task_queue.get(timeout=0.2)
            except queue.Empty:
                continue
            
            # Sentinel для остановки
            if task is None:
                break
            
            # Обрабатываем задачу
            try:
                text = self._process_task(task)
                result = OCRResult(
                    sign_id=task.sign_id,
                    frame_number=task.frame_number,
                    text=text
                )
                self.result_ready.emit(result)
                processed_count += 1
                
                if processed_count % 10 == 0:
                    logger.debug(f"[OCRWorker] Обработано {processed_count} задач OCR")
                    
            except Exception as e:
                logger.error(f"[OCRWorker] Ошибка обработки sign_id={task.sign_id}: {e}")
                # Отправляем пустой результат чтобы не блокировать
                result = OCRResult(
                    sign_id=task.sign_id,
                    frame_number=task.frame_number,
                    text=""
                )
                self.result_ready.emit(result)
        
        logger.info(f"[OCRWorker] Поток завершён. Обработано {processed_count} задач")
    
    def _process_task(self, task: OCRTask) -> str:
        """
        Обработать OCR задачу.
        
        Returns:
            Распознанный текст
        """
        # Определяем тип OCR по классу знака
        if task.cnn_class in TYPE_SIGNS_WITH_TEXT:
            return self._ocr_basic(task.crop)
        
        if task.yolo_class in NAME_SIGNS_CITY:
            return self._ocr_city(task.crop)
        
        return ""
    
    def _ocr_basic(self, crop: np.ndarray) -> str:
        """Базовый OCR — возвращает первую строку."""
        try:
            result = self._ocr_reader.readtext(crop)
            if not result:
                return ""
            return result[0][1]
        except Exception as e:
            logger.warning(f"[OCRWorker] OCR basic failed: {e}")
            return ""
    
    def _ocr_city(self, crop: np.ndarray) -> str:
        """
        OCR для городских знаков с поиском в справочнике городов.
        """
        import difflib
        
        try:
            result = self._ocr_reader.readtext(crop)
            if not result:
                return ""
            
            # Берём текст с наибольшей уверенностью
            best_text = max(result, key=lambda x: x[2])[1] if result else ""
            
            # Загружаем список городов
            try:
                from utils import resource_path
                cities_path = resource_path("static/cities_be.txt")
                with open(cities_path, encoding="utf-8") as f:
                    cities = [line.strip().lower() for line in f if line.strip()]
            except Exception:
                cities = []
            
            if not cities:
                return best_text
            
            # Ищем ближайшее совпадение (только 1 лучший вариант)
            matches = difflib.get_close_matches(
                best_text.lower(), cities, n=1, cutoff=0.6
            )
            
            # Возвращаем одну строку
            return matches[0] if matches else best_text
            
        except Exception as e:
            logger.warning(f"[OCRWorker] OCR city failed: {e}")
            return ""
