"""
processing/ocr_pool.py
ProcessPool для асинхронной OCR обработки.
Заменяет ocr_worker.py (QThread) на ProcessPoolExecutor для обхода Python GIL.

КРИТИЧНО: EasyOCR CPU-bound, QThread не даёт реального параллелизма.
ProcessPool позволяет настоящую многопоточность на CPU.
"""
import logging
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass
from typing import Optional, Callable

import numpy as np

from configs.sign_data import TYPE_SIGNS_WITH_TEXT, NAME_SIGNS_CITY

logger = logging.getLogger(__name__)


@dataclass
class OCRTask:
    """Задача для OCR обработки."""
    sign_id: int           # Уникальный ID знака
    frame_number: int      # Номер кадра
    crop_bytes: bytes      # Сериализованное изображение (pickle)
    crop_shape: tuple      # Форма для восстановления
    crop_dtype: str        # Тип данных
    cnn_class: str         # Класс знака
    yolo_class: str        # YOLO класс


@dataclass
class OCRResult:
    """Результат OCR обработки."""
    sign_id: int
    frame_number: int
    text: str
    error: Optional[str] = None


# ══════════════════════════════════════════════════════════════════
# Worker функция для ProcessPool
# ══════════════════════════════════════════════════════════════════

# Глобальный OCR reader для worker процесса
_worker_ocr_reader = None


def _init_worker_ocr():
    """Инициализирует OCR reader в worker процессе (вызывается один раз)."""
    global _worker_ocr_reader
    if _worker_ocr_reader is None:
        import easyocr
        _worker_ocr_reader = easyocr.Reader(["be"], gpu=False)
        logger.info(f"[OCRPool Worker {mp.current_process().name}] EasyOCR инициализирован")


def _process_ocr_task(task: OCRTask) -> OCRResult:
    """
    Worker функция для обработки OCR задачи.
    Выполняется в отдельном процессе.
    """
    global _worker_ocr_reader
    
    # Инициализируем OCR если ещё не инициализирован
    if _worker_ocr_reader is None:
        _init_worker_ocr()
    
    try:
        # Восстанавливаем numpy array из bytes
        crop = np.frombuffer(task.crop_bytes, dtype=task.crop_dtype).reshape(task.crop_shape)
        
        # Определяем тип OCR
        if task.cnn_class in TYPE_SIGNS_WITH_TEXT:
            text = _ocr_basic(crop)
        elif task.yolo_class in NAME_SIGNS_CITY:
            text = _ocr_city(crop)
        else:
            text = ""
        
        return OCRResult(
            sign_id=task.sign_id,
            frame_number=task.frame_number,
            text=text
        )
    
    except Exception as e:
        logger.error(f"[OCRPool] Ошибка обработки sign_id={task.sign_id}: {e}")
        return OCRResult(
            sign_id=task.sign_id,
            frame_number=task.frame_number,
            text="",
            error=str(e)
        )


def _ocr_basic(crop: np.ndarray) -> str:
    """Базовый OCR — возвращает первую строку."""
    global _worker_ocr_reader
    try:
        result = _worker_ocr_reader.readtext(crop)
        if not result:
            return ""
        return result[0][1]
    except Exception as e:
        logger.warning(f"[OCRPool] OCR basic failed: {e}")
        return ""


def _ocr_city(crop: np.ndarray) -> str:
    """OCR для городских знаков — возвращает лучшее совпадение с справочником городов."""
    global _worker_ocr_reader
    import difflib
    
    try:
        result = _worker_ocr_reader.readtext(crop)
        if not result:
            return ""
        
        # Берём текст с наибольшей уверенностью
        best_text = max(result, key=lambda x: x[2])[1] if result else ""
        
        # Загружаем список городов (TODO: кэшировать)
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
        
        # Возвращаем одну строку (не JSON, не список кортежей)
        return matches[0] if matches else best_text
    
    except Exception as e:
        logger.warning(f"[OCRPool] OCR city failed: {e}")
        return ""


# ══════════════════════════════════════════════════════════════════
# OCRPool — главный класс
# ══════════════════════════════════════════════════════════════════

class OCRPool:
    """
    ProcessPool для асинхронной OCR обработки.
    
    Использование:
        pool = OCRPool(max_workers=2)
        future = pool.submit(sign_id, frame_number, crop, cnn_class, yolo_class)
        future.add_done_callback(lambda f: print(f.result()))
    """
    
    def __init__(self, max_workers: int = 2):
        """
        Args:
            max_workers: Количество worker процессов (рекомендуется 1-2 для CPU)
        """
        self._max_workers = max_workers
        self._executor: Optional[ProcessPoolExecutor] = None
        self._pending_tasks: dict[int, Future] = {}  # sign_id -> Future
        self._processed_count = 0
        
        logger.info(f"[OCRPool] Инициализирован с {max_workers} воркерами")
    
    def start(self):
        """Запустить pool."""
        if self._executor is not None:
            logger.warning("[OCRPool] Pool уже запущен")
            return
        
        self._executor = ProcessPoolExecutor(
            max_workers=self._max_workers,
            mp_context=mp.get_context('spawn')  # Важно для Windows
        )
        logger.info("[OCRPool] Pool запущен")
    
    def stop(self, wait: bool = True):
        """Остановить pool."""
        if self._executor is None:
            return
        
        logger.info(f"[OCRPool] Остановка... (обработано {self._processed_count} задач)")
        
        try:
            if wait:
                # Ждём завершения всех задач
                self._executor.shutdown(wait=True, cancel_futures=False)
            else:
                # Быстрая остановка: не ждём, но НЕ отменяем уже запущенные futures
                # чтобы избежать краша 0xC0000409 при работе с EasyOCR/PyTorch
                self._executor.shutdown(wait=False, cancel_futures=False)
        except Exception as e:
            logger.error(f"[OCRPool] Ошибка при остановке: {e}")
        finally:
            self._executor = None
            self._pending_tasks.clear()
            logger.info("[OCRPool] Остановлен")
    
    def submit(
        self,
        sign_id: int,
        frame_number: int,
        crop: np.ndarray,
        cnn_class: str,
        yolo_class: str,
        callback: Optional[Callable[[OCRResult], None]] = None
    ) -> Optional[Future]:
        """
        Отправить задачу на OCR обработку.
        
        Args:
            sign_id: Уникальный ID знака
            frame_number: Номер кадра
            crop: BGR изображение знака
            cnn_class: Класс знака
            yolo_class: YOLO класс
            callback: Функция для вызова при завершении
        
        Returns:
            Future или None если pool не запущен
        """
        if self._executor is None:
            logger.error("[OCRPool] Pool не запущен, вызовите start()")
            return None
        
        # Проверка: нужен ли OCR для этого знака
        if cnn_class not in TYPE_SIGNS_WITH_TEXT and yolo_class not in NAME_SIGNS_CITY:
            return None
        
        # Сериализуем изображение для передачи в другой процесс
        task = OCRTask(
            sign_id=sign_id,
            frame_number=frame_number,
            crop_bytes=crop.tobytes(),
            crop_shape=crop.shape,
            crop_dtype=str(crop.dtype),
            cnn_class=cnn_class,
            yolo_class=yolo_class
        )
        
        # Отправляем в pool
        future = self._executor.submit(_process_ocr_task, task)
        self._pending_tasks[sign_id] = future
        
        # Добавляем callback если указан
        if callback:
            def wrapper(f: Future):
                try:
                    result = f.result()
                    self._processed_count += 1
                    callback(result)
                except Exception as e:
                    logger.error(f"[OCRPool] Ошибка callback для sign_id={sign_id}: {e}")
                finally:
                    # Удаляем из pending
                    self._pending_tasks.pop(sign_id, None)
            
            future.add_done_callback(wrapper)
        else:
            # Cleanup без callback
            future.add_done_callback(lambda f: self._pending_tasks.pop(sign_id, None))
        
        return future
    
    def get_result(self, sign_id: int, timeout: Optional[float] = None) -> Optional[OCRResult]:
        """
        Получить результат по sign_id (блокирующий вызов).
        
        Args:
            sign_id: ID знака
            timeout: Таймаут ожидания (None = бесконечно)
        
        Returns:
            OCRResult или None если задача не найдена
        """
        future = self._pending_tasks.get(sign_id)
        if future is None:
            return None
        
        try:
            result = future.result(timeout=timeout)
            self._processed_count += 1
            return result
        except Exception as e:
            logger.error(f"[OCRPool] Ошибка получения результата sign_id={sign_id}: {e}")
            return None
    
    @property
    def pending_count(self) -> int:
        """Количество задач в обработке."""
        return len(self._pending_tasks)
    
    @property
    def processed_count(self) -> int:
        """Количество обработанных задач."""
        return self._processed_count
