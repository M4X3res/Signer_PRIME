"""
processing/detector_process_pool.py

Task E: DEPRECATED - больше не вызывается из ProcessingController.
Process Pool режим не даёт выигрыша на CPU и удалён из UI (см. WHY_SINGLE_THREAD_FASTER.md).
Кандидат на удаление в отдельном PR после проверки что тесты не зависят от него.

DetectorProcessPool — многопроцессная обработка кадров для ускорения на CPU.

Архитектура:
    VideoReaderThread
        ↓ frame_queue (Queue)
    DetectorProcessPool
        → ProcessPoolExecutor (N процессов)
        → ReorderBuffer (восстанавливает порядок кадров)
        → ResultAggregator (QThread для UI сигналов)
        ↓ result_queue

Ключевые особенности:
- Использует multiprocessing.Process (не QThread) для CPU-bound задач
- ReorderBuffer гарантирует правильный порядок кадров
- Каждый процесс имеет свои модели (не shared)
- Результаты собираются в главном потоке для UI
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import queue
import threading
import time
from concurrent.futures import ProcessPoolExecutor, Future
from dataclasses import dataclass
from typing import Optional

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal, QThread

from configs import config
from processing.video_reader import RawFrame, _STOP


@dataclass
class ProcessedFrame:
    """Результат обработки одного кадра."""
    frame_idx: int
    video_idx: int
    video_name: str
    image: np.ndarray
    detections: list
    gps_data: Optional[dict]
    timestamp: float


def _safe_log(msg: str) -> None:
    """print() может упасть в windowed/frozen сборке, где sys.stdout is None."""
    try:
        print(msg)
    except Exception:
        pass


def _worker_process_frame(raw_frame_data: dict) -> dict:
    """
    Функция-воркер для обработки одного кадра в отдельном процессе.
    Должна быть top-level функцией для pickling.
    
    Args:
        raw_frame_data: Сериализованные данные кадра
        
    Returns:
        dict с результатами детекции
    """
    # КРИТИЧНО: Настройка окружения для защиты от 0xC0000409
    # Должна быть ДО импорта torch/OpenCV/моделей
    import os
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["MKL_THREADING_LAYER"] = "GNU"
    os.environ["OPENCV_NUM_THREADS"] = "1"
    
    # BLOCK M: Настройка ONNX Runtime для CPU режима
    # DEPRECATED: ORT_DISABLE_CUDA не имеет эффекта, см. apply_cpu_thread_limits() ниже
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if not settings.use_cuda:
            os.environ["ORT_DISABLE_CUDA"] = "1"  # DEPRECATED, no-op
    except Exception:
        os.environ.setdefault("ORT_DISABLE_CUDA", "1")  # DEPRECATED, no-op
    
    # Подавляем TensorRT warning'и от ONNX Runtime
    # (ONNX пытается зарегистрировать TensorRT плагины даже с ORT_DISABLE_CUDA=1)
    import warnings
    warnings.filterwarnings('ignore', message='.*TensorRT.*')
    warnings.filterwarnings('ignore', message='.*TensorrtExecutionProvider.*')
    
    # BLOCK CPU-5: Явное управление потоками ONNX Runtime / OpenVINO в worker процессе
    # Каждый воркер-процесс должен применить ограничения потоков заново (не наследуются при spawn)
    if not hasattr(_worker_process_frame, '_threads_patched'):
        try:
            from configs.settings import get_app_settings
            from configs.inference_threading import apply_cpu_thread_limits, compute_safe_intra_threads
            settings = get_app_settings()
            if not settings.use_cuda:
                num_workers = settings.process_pool_workers or max(1, (os.cpu_count() or 4) - 1)
                intra = settings.cpu_onnx_intra_threads or compute_safe_intra_threads(num_workers)
                ov_threads = settings.cpu_openvino_threads or intra
                apply_cpu_thread_limits(intra, settings.cpu_onnx_inter_threads, ov_threads, True)
                _safe_log(f"[Worker] CPU inference threads: intra={intra}, openvino={ov_threads}")
            _worker_process_frame._threads_patched = True
        except Exception as e:
            _safe_log(f"[Worker] Не удалось применить cpu thread limits: {e}")
    
    # Импорты внутри функции (каждый процесс загружает свои модели)
    try:
        import torch
        torch.set_num_threads(1)  # Ограничиваем потоки в каждом процессе
    except ImportError:
        pass
    
    from core.detector import Detector
    
    # Singleton детектор для процесса (загружается один раз)
    if not hasattr(_worker_process_frame, '_detector'):
        _safe_log("[Worker] Загрузка моделей детектора...")
        try:
            _worker_process_frame._detector = Detector()
            _safe_log("[Worker] Модели загружены")
        except Exception as e:
            _safe_log(f"[Worker] ОШИБКА загрузки: {e}")
            raise
    
    detector = _worker_process_frame._detector
    
    # BLOCK PERF-ANALYSIS-1: Измерение размера данных и времени обработки
    image_bytes_size_mb = len(raw_frame_data['image_bytes']) / (1024 * 1024)
    _safe_log(f"[Worker] image_bytes size: {image_bytes_size_mb:.2f} MB")
    
    try:
        # Восстанавливаем image из bytes
        t_start_reshape = time.time()
        image = np.frombuffer(raw_frame_data['image_bytes'], dtype=np.uint8).reshape(
            raw_frame_data['image_shape']
        )
        t_reshape = time.time() - t_start_reshape
        
        # Детектируем знаки
        t_start_detect = time.time()
        detections = detector.detect(image)
        t_detect = time.time() - t_start_detect
        
        # BLOCK PERF-ANALYSIS-1: Логируем время детекции
        _safe_log(f"[Worker] Detection time: {t_detect:.3f}s, reshape: {t_reshape:.3f}s")
        
        # Сериализуем detections для передачи между процессами
        detections_serialized = [
            {
                'box': det.box,
                'color': det.color,
                'yolo_class': det.yolo_class,
                'cnn_class': det.cnn_class,
                'text': det.text,
                'is_side': det.is_side,
            }
            for det in detections
        ]
    except Exception as e:
        _safe_log(f"[Worker] ОШИБКА обработки кадра: {e}")
        raise
    
    # BLOCK PERF-FIX-1: Возвращаем ТОЛЬКО детекции, БЕЗ image_bytes
    # Устранение двойной сериализации: кадр уже есть в главном процессе
    # (_pending_frames), не нужно гнать его обратно через IPC
    return {
        'seq': raw_frame_data['seq'],
        'frame_idx': raw_frame_data['frame_idx'],
        'frame_number': raw_frame_data.get('frame_number', raw_frame_data['frame_idx']),
        'video_idx': raw_frame_data['video_idx'],
        'video_name': raw_frame_data['video_name'],
        'detections': detections_serialized,
        'gps_data': raw_frame_data.get('gps_data'),
        'timestamp': time.time(),
    }


class ReorderBuffer:
    """
    Буфер для восстановления правильного порядка кадров.

    ВАЖНО (BLOCK PREVIEW-FIX-1): ключ упорядочивания — 'seq', строго
    последовательный счётчик (0, 1, 2, ...), присваиваемый
    DetectorProcessPool._submit_loop() в момент отправки кадра воркеру.
    НЕЛЬЗЯ использовать 'frame_idx' (= raw.abs_frame_number) в этой роли:
    abs_frame_number растёт с шагом FRAME_STEP (обычно 5) и НИКОГДА не
    равен 0 для первого кадра, поэтому _next_expected=0 никогда не находил
    совпадения в self._buffer, add() всегда возвращал [] и все кадры
    накапливались до единственного flush() в самом конце обработки —
    отсюда «нет предпросмотра» и «всё случается одним махом в конце».
    См. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 1.
    """

    def __init__(self, max_gap: int = 32):
        self._buffer: dict[int, dict] = {}
        self._next_expected: int = 0
        self._max_gap = max_gap

    def add(self, frame_data: dict) -> list[dict]:
        """
        Добавить обработанный кадр.
        
        Returns:
            Список кадров в правильном порядке, готовых к отправке.
        """
        seq = frame_data['seq']
        self._buffer[seq] = frame_data

        # Отдаем все последовательные кадры начиная с expected
        ready = []
        while self._next_expected in self._buffer:
            ready.append(self._buffer.pop(self._next_expected))
            self._next_expected += 1

        # Проверяем размер разрыва (защита от утечки памяти)
        if self._buffer:
            min_buffered = min(self._buffer.keys())
            gap = min_buffered - self._next_expected
            if gap > self._max_gap:
                # Пропускаем недостающие кадры (возможно lost)
                logger = logging.getLogger(__name__)
                logger.warning(f"[ReorderBuffer] gap={gap} > max_gap={self._max_gap}, "
                              f"skipping frames seq {self._next_expected}-{min_buffered}")
                self._next_expected = min_buffered
                # Рекурсивно пробуем снова
                return self.add(frame_data)

        return ready
    
    def flush(self) -> list[dict]:
        """Отдать все оставшиеся кадры (при завершении)."""
        remaining = sorted(self._buffer.items())
        self._buffer.clear()
        return [frame_data for _, frame_data in remaining]
    
    def __len__(self) -> int:
        return len(self._buffer)


class ResultAggregatorThread(QThread):
    """
    Поток для агрегации результатов из ProcessPool и отправки в UI.
    Нужен потому что ProcessPoolExecutor работает в background, 
    а Qt сигналы должны отправляться из QThread.
    
    Fix 1.2: Добавлена интеграция с SignHandler для корректного трекинга.
    BLOCK CPU-7: Добавлен SmartFrameSkipper для обновления activity history.
    """
    
    frame_ready = pyqtSignal(object)  # ProcessedFrame для UI
    stats_updated = pyqtSignal(int, int, float)  # frames, signs, fps
    finished_work = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(
        self,
        futures_queue: queue.Queue,
        reorder_buffer: ReorderBuffer,
        sign_handler,  # Fix 1.2: SignHandler для трекинга
        gpx_handler,   # Fix 1.2: GPXHandler для координат
        skipper,       # BLOCK CPU-7: SmartFrameSkipper для activity history
        pending_frames: dict,  # BLOCK PERF-FIX-1: dict[seq, RawFrame] из главного процесса
        pending_frames_lock: threading.Lock,  # BLOCK PERF-FIX-1: синхронизация доступа
        parent=None,
    ):
        super().__init__(parent)
        self._futures_q = futures_queue
        self._reorder_buffer = reorder_buffer
        self._sign_handler = sign_handler  # Fix 1.2
        self._gpx = gpx_handler  # Fix 1.2
        self._skipper = skipper  # BLOCK CPU-7
        self._pending_frames = pending_frames  # BLOCK PERF-FIX-1
        self._pending_frames_lock = pending_frames_lock  # BLOCK PERF-FIX-1

        # NEW (BLOCK PREVIEW-FIX-2): нужен для конвертации WGS84 -> EPSG:32635,
        # см. _build_detected_signs() ниже и PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 2.
        from core.converter import Converter
        self._converter = Converter()

        self._stop = False
        
        # Статистика
        self._frames_processed = 0
        self._signs_found = 0
        self._start_time = time.monotonic()
        self._last_stats_time = self._start_time
        
        # ── Троттлинг предпросмотра (аналогично DetectorThread) ────
        from configs.settings import get_app_settings
        settings = get_app_settings()
        self._preview_min_interval = (
            1.0 / settings.preview_fps_limit if settings.preview_fps_limit > 0 else 0.0
        )
        self._last_emit_time = 0.0
        
        # BLOCK PERF-FIX-1: Периодическая чистка протухших кадров в _pending_frames
        self._last_cleanup_time = time.monotonic()
        self._cleanup_interval = 5.0  # Чистка раз в 5 секунд
    
    def stop(self):
        self._stop = True
    
    def _cleanup_stale_frames(self):
        """
        BLOCK PERF-FIX-1: Периодическая чистка протухших кадров из _pending_frames.
        
        Если кадр был пропущен ReorderBuffer (gap-safety-valve), соответствующий seq
        никогда не придёт в _process_result() и запись останется в памяти навсегда.
        Удаляем все seq старше next_expected - MAX_GAP*2 (с запасом).
        """
        now = time.monotonic()
        if now - self._last_cleanup_time < self._cleanup_interval:
            return  # Ещё рано
        
        self._last_cleanup_time = now
        
        # Определяем порог: seq старше чем (next_expected - буфер) считаются протухшими
        threshold_seq = max(0, self._reorder_buffer._next_expected - config.REORDER_BUFFER_MAX_GAP * 2)
        
        stale_keys = []
        with self._pending_frames_lock:
            for seq in list(self._pending_frames.keys()):
                if seq < threshold_seq:
                    stale_keys.append(seq)
            
            for seq in stale_keys:
                self._pending_frames.pop(seq, None)
        
        if stale_keys:
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[ResultAggregator] Очищено {len(stale_keys)} протухших кадров из "
                f"_pending_frames (seq < {threshold_seq}). Возможны gap'ы в ReorderBuffer."
            )
    
    def _should_emit_preview(self) -> bool:
        """
        Проверяет, нужно ли обновлять UI-превью (троттлинг).
        Аналогично DetectorThread._should_emit_preview().
        
        Returns:
            True, если прошло достаточно времени с последнего эмита.
        """
        if self._preview_min_interval <= 0:
            return True
        now = time.monotonic()
        if now - self._last_emit_time < self._preview_min_interval:
            return False
        self._last_emit_time = now
        return True
    
    def run(self):
        """Цикл агрегации результатов."""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            while not self._stop:
                try:
                    future: Future = self._futures_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                
                if future is None:  # Sentinel для остановки
                    logger.debug("[ResultAggregator] Получен sentinel, завершаем")
                    break
                
                # BLOCK PERF-ANALYSIS-1: Измерение времени распаковки future.result()
                t_start_unpickle = time.time()
                try:
                    result = future.result(timeout=10.0)
                    t_unpickle = time.time() - t_start_unpickle
                    logger.debug(f"[ResultAggregator] future.result() unpickle time: {t_unpickle:.3f}s")
                except TimeoutError:
                    logger.warning("[ResultAggregator] Future timeout — worker процесс завис или упал")
                    continue
                except Exception as e:
                    logger.error(f"[ResultAggregator] Ошибка получения результата: {e}")
                    continue

                try:
                    ready_frames = self._reorder_buffer.add(result)
                except Exception as e:
                    logger.exception(f"[ResultAggregator] Ошибка reorder buffer: {e}")
                    continue

                # BLOCK STAB-2: каждый кадр обрабатывается в своём try/except,
                # чтобы ошибка в ОДНОМ кадре не «съедала» остальные кадры
                # того же батча ready_frames.
                for frame_data in ready_frames:
                    try:
                        self._process_result(frame_data)
                    except Exception as e:
                        logger.exception(
                            f"[ResultAggregator] Ошибка обработки кадра "
                            f"{frame_data.get('frame_idx')}: {e}"
                        )
                        self.error.emit(
                            f"Пропущен кадр {frame_data.get('frame_idx')} из-за ошибки: {e}"
                        )
                        continue
                
                # BLOCK PERF-FIX-1: Периодическая чистка протухших кадров
                self._cleanup_stale_frames()

            # Финальная очистка буфера
            logger.debug("[ResultAggregator] Финальная очистка reorder buffer")
            try:
                remaining = self._reorder_buffer.flush()
            except Exception as e:
                logger.exception(f"[ResultAggregator] Ошибка flush reorder buffer: {e}")
                remaining = []

            for frame_data in remaining:
                try:
                    self._process_result(frame_data)
                except Exception as e:
                    logger.exception(f"[ResultAggregator] Ошибка обработки remaining frame: {e}")

            # БАГ E: Финализируем активные знаки в конце видео
            if self._sign_handler:
                logger.info("[ResultAggregator] Финализация оставшихся активных знаков...")
                try:
                    self._sign_handler.finalize_remaining()
                except Exception as e:
                    logger.exception(f"[ResultAggregator] Ошибка финализации знаков: {e}")

            logger.info("[ResultAggregator] Завершён корректно")

        except Exception as e:
            logger.error(f"[ResultAggregator] Критическая ошибка: {e}")
            self.error.emit(f"Aggregator error: {e}")
        finally:
            # BLOCK STAB-2: finished_work ДОЛЖЕН эмититься ровно один раз,
            # независимо от того, как завершился цикл — штатно или через
            # исключение. Раньше вызов был только в «счастливом» пути внутри
            # try — при ошибке ProcessingController никогда не получал сигнал
            # finished, и UI бесконечно висел в состоянии «обработка идёт».
            self.finished_work.emit()
    
    def _process_result(self, frame_data: dict):
        """
        Обработка одного готового результата.
        Fix 1.2: Добавлена интеграция с SignHandler (портировано из DetectorPool).
        BLOCK CPU-7: Добавлено обновление activity history через SmartFrameSkipper.
        BLOCK PERF-FIX-1: Берём кадр из _pending_frames вместо десериализации из frame_data.
        """
        seq = frame_data['seq']
        
        # BLOCK PERF-FIX-1: Берём image из главного процесса вместо распаковки
        with self._pending_frames_lock:
            raw_frame = self._pending_frames.pop(seq, None)
        
        if raw_frame is None:
            import logging
            logger = logging.getLogger(__name__)
            logger.error(f"[ResultAggregator] Кадр seq={seq} не найден в _pending_frames! "
                        f"Возможна утечка или gap в ReorderBuffer.")
            return
        
        image = raw_frame.image  # Используем исходный кадр, без reshape/tobytes overhead
        
        # Fix 1.2: Обновляем глобальные индексы перед SignHandler
        # (SignHandler зависит от этих глобалов — см. sign_handler.py)
        config.INDEX_OF_FRAME = frame_data.get('frame_number', frame_data['frame_idx'])
        config.INDEX_OF_All_FRAME = frame_data['frame_idx']  # теперь действительно абсолютный номер
        config.INDEX_OF_VIDEO = frame_data['video_idx']
        config.INDEX_OF_GPS = frame_data.get('gps_data', {}).get('gps_index', 0)
        
        # Fix 1.2: Конвертируем detections в DetectedSign для SignHandler
        detected_signs = self._build_detected_signs(frame_data)
        
        # Fix 1.2: Прогоняем через SignHandler для трекинга
        from core.turn import Turn
        if not hasattr(self, '_turn'):
            self._turn = Turn()
        
        self._turn = self._sign_handler.check_the_data_to_add(
            detected_signs or None, 
            self._turn
        )
        
        # BLOCK CPU-7: Обновляем историю активности для адаптивного skip
        self._skipper.update_activity(len(frame_data['detections']))
        
        # Обновляем статистику
        self._frames_processed += 1
        self._signs_found += len(frame_data['detections'])
        
        # ── Превью для UI (с троттлингом) ────────────────────────
        t_start_emit = time.time()
        if self._should_emit_preview():
            import logging
            logger = logging.getLogger(__name__)
            logger.debug(f"[ProcessPool._process_result] Эмит preview для кадра {frame_data['frame_idx']}")
            self._emit_frame(image, frame_data['detections'])
        t_emit = time.time() - t_start_emit
        
        # BLOCK PERF-ANALYSIS-1: Логируем время обработки в аггрегаторе
        import logging
        logger = logging.getLogger(__name__)
        logger.debug(f"[ResultAggregator] _process_result times: reshape={t_reshape:.3f}s, emit={t_emit:.3f}s")
        
        # Обновляем статистику каждую секунду
        now = time.monotonic()
        if now - self._last_stats_time >= 1.0:
            elapsed = now - self._start_time
            fps = self._frames_processed / elapsed if elapsed > 0 else 0.0
            self.stats_updated.emit(self._frames_processed, self._signs_found, fps)
            self._last_stats_time = now
    
    def _emit_frame(self, image: np.ndarray, detections: list[dict]) -> None:
        """
        Рисует bbox'ы и отправляет BGR numpy кадр в UI.
        
        ВАЖНО: НЕ создаём QPixmap здесь! ResultAggregatorThread — это QThread,
        а QPixmap нельзя создавать в non-GUI потоке (Qt ограничение).
        Вместо этого отправляем annotated numpy array через build_frame_dict(),
        а ProcessingController создаст QPixmap в главном GUI потоке.
        
        См. processing/preview_utils.py для деталей thread-safe архитектуры.
        """
        import cv2
        from processing.preview_utils import build_frame_dict

        # Рисуем bbox на копии кадра
        frame = image.copy()
        for det in detections:
            x, y, w, h = det['box']
            color = det.get('color', (0, 255, 0))
            label = det.get('cnn_class') or det.get('yolo_class') or ''
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame, str(label), (x, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
            )
        
        # Используем единую утилиту для сериализации
        self.frame_ready.emit(build_frame_dict(frame))

    def _build_detected_signs(self, frame_data: dict):
        """
        Fix 1.2 (историческая правка): конвертирует serialized detections
        в DetectedSign objects. Портировано из DetectorPool._build_detected_signs().

        BLOCK PREVIEW-FIX-2: добавлена конвертация координат WGS84 -> EPSG:32635,
        без которой все знаки, найденные в режиме Process Pool, оказывались
        на координатах около экватора («Африка-баг»). Тот же фикс уже был
        применён в DetectorThread._build_detected() ранее — здесь он был
        пропущен. См. Часть 2 промпта.
        """
        from core.frame import DetectedSign
        
        result = []
        lat, lon = 0.0, 0.0
        
        # Получаем координаты из GPX и конвертируем в EPSG:32635
        try:
            gps_index = frame_data.get('gps_data', {}).get('gps_index', 0)
            lat, lon = self._gpx.get_current_coordinate(gps_index)
            if lat != 0.0 and lon != 0.0:
                lat, lon = self._converter.coordinateConverter(
                    lat, lon, "epsg:4326", "epsg:32635"
                )
        except Exception:
            pass
        
        # Конвертируем каждую детекцию
        for det in frame_data['detections']:
            result.append(DetectedSign(
                x=det['box'][0],
                y=det['box'][1],
                w=det['box'][2],
                h=det['box'][3],
                name_sign=det['yolo_class'],
                number_sign=det['cnn_class'],
                frame_number=frame_data.get('frame_number', frame_data['frame_idx']),
                absolute_frame_number=frame_data['frame_idx'],
                latitude=lat,
                longitude=lon,
                text_on_sign=det.get('text', ''),
                is_side=det.get('is_side', False),
            ))
        
        return result


class DetectorProcessPool(QObject):
    """
    Пул процессов для параллельной детекции знаков.
    Использует ProcessPoolExecutor для CPU-bound задач.
    
    Fix 1.2: Добавлены SignHandler интеграция и методы get_result_signs/get_turn_data.
    BLOCK CPU-7: Добавлен SmartFrameSkipper для умного пропуска кадров.
    """
    
    frame_ready = pyqtSignal(object)
    stats_updated = pyqtSignal(int, int, float)
    finished_work = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(
        self,
        frame_queue: queue.Queue,
        parent=None,
    ):
        super().__init__(parent)
        self._frame_q = frame_queue
        
        # Определяем количество воркеров
        self._num_workers = self._detect_optimal_workers()
        
        # ProcessPoolExecutor
        self._executor: Optional[ProcessPoolExecutor] = None
        
        # ReorderBuffer для восстановления порядка
        self._reorder_buffer = ReorderBuffer(
            max_gap=config.REORDER_BUFFER_MAX_GAP
        )
        
        # Очередь для futures
        self._futures_q: queue.Queue = queue.Queue(maxsize=self._num_workers * 4)
        
        # NEW (BLOCK PREVIEW-FIX-1): строго последовательный счётчик отправки кадров
        self._submit_seq = 0
        
        # BLOCK PERF-FIX-1: Хранилище кадров для устранения двойной сериализации
        # Ключ seq -> RawFrame с исходным image. Кадр отправляется воркеру один раз,
        # а при получении результата берётся из этого словаря вместо десериализации
        # из future.result(). Защита от утечки: периодическая чистка протухших записей.
        self._pending_frames: dict[int, RawFrame] = {}
        self._pending_frames_lock = threading.Lock()
        
        # Fix 1.2: SignHandler и GPXHandler для трекинга знаков
        self._sign_handler = None
        self._gpx = None
        
        # BLOCK CPU-7: SmartFrameSkipper для умного пропуска кадров
        from processing.frame_skip import SmartFrameSkipper
        self._skipper = SmartFrameSkipper()
        
        # Поток агрегации результатов
        self._aggregator: Optional[ResultAggregatorThread] = None
        
        # Поток отправки задач в pool
        self._submitter_thread: Optional[QThread] = None
        
        self._stop = False
        
        logger = logging.getLogger(__name__)
        logger.info(f"[DetectorProcessPool] Создан пул из {self._num_workers} процессов")
    
    def _detect_optimal_workers(self) -> int:
        """
        Определяет оптимальное количество воркеров.
        
        Порядок приоритета:
        1) AppSettings.process_pool_workers, если пользователь явно задал > 0
           (Settings UI -> "Количество воркеров")
        2) config.N_WORKERS, если когда-либо будет установлен программно
        3) автоопределение по cpu_count
        
        См. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 3.1
        """
        try:
            from configs.settings import get_app_settings
            settings = get_app_settings()
            if settings.process_pool_workers and settings.process_pool_workers > 0:
                return max(1, settings.process_pool_workers)
        except Exception:
            pass

        if config.N_WORKERS is not None:
            return max(1, config.N_WORKERS)
        
        cpu_count = os.cpu_count() or 4
        
        # Эвристика: N-1 процессов (оставляем 1 для UI и VideoReader)
        optimal = max(2, min(8, cpu_count - 1))
        
        return optimal
    
    def start(self):
        """Запуск пула обработки."""
        logger = logging.getLogger(__name__)
        
        if self._executor is not None:
            logger.warning("[DetectorProcessPool] Уже запущен")
            return
        
        logger.info(f"[DetectorProcessPool] Запуск с {self._num_workers} процессами...")
        
        # Fix 1.2: Создаём SignHandler и GPXHandler в главном потоке
        from core.sign_handler import SignHandler
        from core.gpx_handler import GPXHandler
        
        self._sign_handler = SignHandler()
        self._gpx = GPXHandler()
        
        try:
            # Создаем ProcessPoolExecutor
            self._executor = ProcessPoolExecutor(
                max_workers=self._num_workers,
                mp_context=mp.get_context('spawn'),  # Важно для Windows/PyQt
            )
        except Exception as e:
            logger.error(f"[DetectorProcessPool] ОШИБКА: {e}")
            self.error.emit(f"Ошибка создания пула процессов: {e}")
            return
        
        # Запускаем aggregator thread с SignHandler и SmartFrameSkipper (BLOCK CPU-7)
        # BLOCK PERF-FIX-1: передаём _pending_frames для устранения двойной сериализации
        self._aggregator = ResultAggregatorThread(
            self._futures_q,
            self._reorder_buffer,
            self._sign_handler,  # Fix 1.2
            self._gpx,            # Fix 1.2
            self._skipper,        # BLOCK CPU-7
            self._pending_frames,  # BLOCK PERF-FIX-1
            self._pending_frames_lock,  # BLOCK PERF-FIX-1
        )
        self._aggregator.frame_ready.connect(self.frame_ready)
        self._aggregator.stats_updated.connect(self.stats_updated)
        self._aggregator.finished_work.connect(self._on_aggregator_finished)
        self._aggregator.error.connect(self.error)
        self._aggregator.start()
        
        # Запускаем submitter thread
        self._start_submitter()
        
        logger.info(f"[DetectorProcessPool] Запущен")
    
    def _start_submitter(self):
        """Запуск потока отправки задач в ProcessPool."""
        class SubmitterThread(QThread):
            def __init__(self, pool_instance):
                super().__init__()
                self.pool = pool_instance
            
            def run(self):
                self.pool._submit_loop()
        
        self._submitter_thread = SubmitterThread(self)
        self._submitter_thread.start()
    
    def _submit_loop(self):
        """Цикл отправки кадров на обработку (BLOCK CPU-7: с SmartFrameSkipper)."""
        logger = logging.getLogger(__name__)
        try:
            while not self._stop:
                try:
                    raw: RawFrame = self._frame_q.get(timeout=0.2)
                except queue.Empty:
                    continue
                
                if raw is _STOP:
                    logger.debug("[DetectorProcessPool] Получен _STOP, завершаем submit loop")
                    break
                
                # BLOCK CPU-7: Умный frame skipping
                speed = self._gpx.get_speed(raw.gps_index) if self._gpx else None
                
                # Пропускаем если машина стоит
                if self._skipper.is_stationary(speed):
                    continue
                
                # Вычисляем интервал пропуска
                self._skipper.calc_skip_interval(speed)
                
                # Проверяем нужно ли обрабатывать этот кадр
                if not self._skipper.should_process():
                    continue
                
                # Прокидываем эффективный skip в config для SignHandler
                config.CURRENT_EFFECTIVE_SKIP = self._skipper.current_skip
                
                # BLOCK PERF-FIX-1: Сохраняем кадр в главном процессе ПЕРЕД отправкой
                seq = self._submit_seq
                with self._pending_frames_lock:
                    self._pending_frames[seq] = raw  # raw.image остаётся в главном процессе
                
                # Сериализуем кадр для передачи в процесс
                frame_data = {
                    'seq': seq,                                 # NEW — строго 0,1,2,3,...
                    'frame_idx': raw.abs_frame_number,          # без изменений
                    'frame_number': raw.frame_number,           # локальный номер — для UI/переходов к кадру
                    'video_idx': raw.video_index,
                    'video_name': raw.video_name,
                    'image_bytes': raw.image.tobytes(),
                    'image_shape': raw.image.shape,
                    'gps_data': {'gps_index': raw.gps_index},   # Передаем как dict
                }
                self._submit_seq += 1                           # NEW
                
                # Проверяем что executor ещё жив
                if self._executor is None:
                    logger.warning("[DetectorProcessPool] Executor is None, прерываем submit loop")
                    break
                
                try:
                    # Отправляем на обработку
                    future = self._executor.submit(_worker_process_frame, frame_data)
                    
                    # Добавляем future в очередь для aggregator
                    self._futures_q.put(future)
                except Exception as e:
                    logger.error(f"[DetectorProcessPool] Ошибка submit: {e}")
                    break
            
            # Отправляем sentinel для остановки aggregator
            logger.debug("[DetectorProcessPool] Отправка sentinel в futures_q")
            self._futures_q.put(None)
            
        except Exception as e:
            self.error.emit(f"Submitter error: {e}")
    
    def _on_aggregator_finished(self) -> None:
        """
        Вызывается когда ResultAggregatorThread САМ естественно завершился —
        то есть весь бэклог из очереди прочитан reader'ом, отправлен
        submitter'ом, обработан воркер-процессами и агрегирован. В этот
        момент executor можно закрыть штатно (executor.shutdown(wait=True)):
        все задачи уже выполнены, никто больше не вызывает executor.submit(),
        поэтому wait=True не зависнет и не потребует kill() процессов.
        """
        logger = logging.getLogger(__name__)
        logger.info("[DetectorProcessPool] Aggregator завершился естественно — закрываем executor...")

        if self._submitter_thread and not self._submitter_thread.wait(30000):
            logger.warning("[DetectorProcessPool] Submitter не завершился за 30 сек после aggregator")

        if self._executor is not None:
            try:
                self._executor.shutdown(wait=True)  # безопасно: новых задач больше не будет
            except Exception as e:
                logger.error(f"[DetectorProcessPool] Ошибка graceful shutdown executor: {e}")
            finally:
                self._executor = None

        logger.info("[DetectorProcessPool] Executor закрыт корректно")
        self.finished_work.emit()

    def stop(self):
        """
        Немедленная остановка (используется кнопкой "Стоп"/закрытием
        приложения — БЕЗ ожидания полной обработки очереди, оставшийся
        бэклог кадров отбрасывается).

        ВАЖНО: НЕ убивает OS-процессы принудительно (proc.terminate()/kill()).
        Вместо этого прекращает приём НОВЫХ кадров в submit_loop (он выйдет
        на следующей итерации, максимум ~0.2с) и позволяет уже запущенным
        задачам (их не больше self._num_workers*4, см. futures_q maxsize)
        доработать штатно. Дальше _on_aggregator_finished() сам закроет
        executor через обычный graceful shutdown(wait=True). Именно
        принудительный kill() воркер-процессов посреди вычисления был
        вероятной причиной крашей 0xC0000409 — см. Часть 1 промпта
        PROMPT_FIX_PROCESSPOOL_PIPELINE_CRASH.md.
        """
        logger = logging.getLogger(__name__)
        logger.info("[DetectorProcessPool] Останавливаем (abort)...")
        self._stop = True
        # Дальнейшая остановка (submitter → aggregator → executor.shutdown)
        # произойдёт естественно и безопасно через _on_aggregator_finished().
    
    def wait(self, timeout_ms: int = 5000) -> bool:
        """Ожидание завершения обработки."""
        if self._aggregator:
            return self._aggregator.wait(timeout_ms)
        return True
    
    # Fix 1.2: Добавлены методы для получения результатов (как в DetectorPool)
    
    def get_result_signs(self) -> list:
        """
        Получить финализированные знаки из SignHandler.
        Fix 1.2: Реализовано для совместимости с ProcessingController.
        """
        if self._sign_handler:
            return self._sign_handler.result_signs
        return []
    
    def get_turn_data(self) -> list:
        """
        Получить данные о поворотах из SignHandler.
        Fix 1.2: Реализовано для совместимости с ProcessingController.
        """
        if self._sign_handler:
            return self._sign_handler.turns
        return []
