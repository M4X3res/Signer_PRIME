"""
threading/processing_controller.py
ProcessingController — создаёт и связывает все потоки обработки.
Заменяет PlayerHandler + treatment() из старого кода.

Схема:
    VideoReaderThread
        ↓ frame_queue (Queue, maxsize=8)
    DetectorThread
        ↓ result_queue (Queue, unbounded)
    ResultCollectorThread
        ↓ сигналы → UI, FinalHandler
"""
from __future__ import annotations

import logging
import multiprocessing as mp
import queue
from typing import Optional

from PyQt6.QtCore import QObject, pyqtSignal, QThread

from configs import config
from processing.video_reader  import VideoReaderThread
from processing.detector_thread import DetectorThread


class ProcessingController(QObject):
    """
    Единая точка управления обработкой.
    Создаётся один раз, start/stop вызываются по кнопкам UI.

    Сигналы наружу (подписывается MainWindow / ProcessingPage):
        frame_ready(QPixmap)
        progress(int, int)            — abs_frame, total
        stats(int, int, float)        — frames, signs, fps
        video_switched(int, str)      — idx, name
        sign_found(str, str, float)   — type, video, conf
        finished()
        error(str)
    """

    frame_ready    = pyqtSignal(object)
    progress       = pyqtSignal(int, int)
    stats          = pyqtSignal(int, int, float)
    video_switched = pyqtSignal(int, str)
    sign_found     = pyqtSignal(str, str, float)
    finished       = pyqtSignal()
    error          = pyqtSignal(str)

    # ── Размеры очередей (ограничение памяти) ────────────────────
    FRAME_QUEUE_SIZE  = 100   # кадров в буфере (было 8, увеличено для стабильности)
    RESULT_QUEUE_SIZE = 5000  # знаков в буфере (увеличено с 500 до 5000 для длинных видео)
    
    # ── Автосохранение checkpoint ─────────────────────────────────
    CHECKPOINT_INTERVAL = 60  # секунд между автосохранениями
    CHECKPOINT_PATH = "checkpoint.pkl"

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._reader:   Optional[VideoReaderThread] = None
        self._detector: Optional[DetectorThread]    = None
        self._detector_pool = None  # Новое: пул детекторов
        self._frame_q:  Optional[queue.Queue]       = None
        self._result_q: Optional[queue.Queue]       = None
        self._running   = False
        
        # Автосохранение checkpoint
        self._checkpoint_timer: Optional[QThread] = None
        self._last_checkpoint_time = 0
        
        # BLOCK SIGN-LOSS-2: состояние восстановления из checkpoint
        self._resume_from_checkpoint: bool = False
        self._checkpoint_data: Optional[dict] = None

    # ── Public API ────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        
        self._reset_config()
        
        # Fix 1.3: Применяем режим обработки из Settings перед созданием воркеров
        from configs.settings import get_app_settings
        settings = get_app_settings()
        # Task E: Всегда используем single_thread (выбор режима убран из UI)
        config.PROCESSING_MODE = "single_thread"
        logging.getLogger(__name__).info(f"[ProcessingController] Режим обработки: {config.PROCESSING_MODE} (Task E: всегда single_thread)")
        
        # NEW (BLOCK PREVIEW-FIX-4): подхватить изменение "Использовать CUDA"
        # без перезапуска приложения, если пользователь переключил его со
        # времени последнего прогона.
        # BLOCK FIX-3: НЕ проглатывать ошибки молча - логировать их явно
        try:
            from configs.sign_models import reload_all_models_if_device_changed
            reload_all_models_if_device_changed()
        except Exception as e:
            logging.getLogger(__name__).error(
                f"[ProcessingController] reload_all_models_if_device_changed() упал: {e}. "
                f"ORT_DISABLE_CUDA мог не синхронизироваться с текущим backend!",
                exc_info=True,
            )
        
        # BLOCK CPU-6: Проверка реального backend перед началом обработки (асинхронно)
        # До BLOCK CPU-6 это делалось синхронно, загружая все модели в GUI-потоке → зависание UI.
        requested_backend = "torch" if settings.use_cuda else settings.cpu_inference_backend
        if requested_backend != "torch":
            self._start_backend_verify(requested_backend)
        
        self._create_queues()
        self._start_reader()
        
        # Task E: Упрощено - всегда вызываем _start_detector (Process Pool больше не используется)
        self._start_detector()
        
        self._start_checkpoint_timer()
        self._running = True

    def stop(self) -> None:
        """Немедленная остановка — знаки не сохраняются."""
        if self._reader:
            self._reader.stop()
        
        if self._detector_pool:
            self._detector_pool.stop()
        elif self._detector:
            self._detector.stop()
        
        self._running = False

    def pause(self) -> None:
        if self._reader:
            self._reader.pause()

    def resume(self) -> None:
        if self._reader:
            self._reader.resume()

    def finish_and_save(self) -> None:
        """
        Мягкая остановка — просим reader прекратить чтение НОВЫХ кадров.

        ВАЖНО: вызывается из UI-потока (слот на кнопку "Завершить") и НЕ
        ДОЛЖЕН блокировать его вызовами .wait()! DetectorThread /
        DetectorProcessPool сами доработают весь бэклог кадров, оставшийся
        в очереди (ограничен FRAME_QUEUE_SIZE), и когда реально закончат —
        испустят finished_work, уже подключённый к _on_detector_finished()
        → self.finished → MainWindow._on_finish() → _save_results().

        Никакого принудительного .stop()/.wait() здесь быть не должно —
        именно комбинация "короткий таймаут + forced stop посреди активных
        задач ProcessPoolExecutor" (OCRPool в pipeline или основной пул в
        process_pool) была причиной краша 0xC0000409 при нажатии "Завершить".
        """
        logger = logging.getLogger(__name__)
        logger.info("[ProcessingController] finish_and_save: сигнал остановки чтения видео")

        if self._reader:
            self._reader.stop()

        # НЕ вызывать .wait()/.stop() на self._detector или self._detector_pool
        # здесь — см. docstring выше.

    def get_result_signs(self) -> list:
        """Забрать накопленные знаки из очереди результатов."""
        # Если используется пул — забираем из него
        if self._detector_pool:
            return self._detector_pool.get_result_signs()
        
        # Иначе из очереди (старый способ)
        results = []
        if not self._result_q:
            logging.getLogger(__name__).warning("[ProcessingController] result_q не создана!")
            return results
        while True:
            try:
                results.append(self._result_q.get_nowait())
            except queue.Empty:
                break
        logging.getLogger(__name__).info(f"[ProcessingController] Получено {len(results)} знаков из очереди")
        return results

    def get_turn_data(self) -> list:
        """Данные о поворотах из DetectorThread."""
        if self._detector_pool:
            return self._detector_pool.get_turn_data()
        
        if self._detector and hasattr(self._detector, "_sign_handler"):
            return self._detector._sign_handler.turns
        return []

    # ── Private ───────────────────────────────────────────────────

    def _reset_config(self) -> None:
        """
        Сброс всех индексов перед началом обработки.
        
        BLOCK PREVIEW-FIX-3: читает настройки frame_step из UI.
        См. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 3.2
        
        BLOCK SIGN-LOSS-2 FIX: если восстанавливаемся из checkpoint
        (self._resume_from_checkpoint == True), индексы НЕ трогаем — они уже
        выставлены в load_checkpoint(). Раньше это делалось безусловно, из-за
        чего восстановление позиции в видео не работало никогда.
        """
        from configs.settings import get_app_settings
        settings = get_app_settings()

        if settings.frame_step_mode == "manual" and settings.frame_step_manual > 0:
            config.FRAME_STEP = max(1, int(settings.frame_step_manual))
        else:
            # "auto": базовый шаг чтения видео остаётся стандартным; дополнительная
            # адаптивная подстройка по скорости уже делается отдельно внутри
            # DetectorThread._calc_skip_interval() поверх этого базового шага —
            # это НЕ то же самое поле и трогать его тут не нужно.
            config.FRAME_STEP = 5

        if self._resume_from_checkpoint:
            logging.getLogger(__name__).info(
                f"[ProcessingController] Resume: индексы НЕ сбрасываются "
                f"(video={config.INDEX_OF_VIDEO}, frame={config.INDEX_OF_FRAME}, "
                f"abs_frame={config.INDEX_OF_All_FRAME})"
            )
            return

        config.COUNT_PROCESSED_FRAMES = 0
        config.INDEX_OF_FRAME       = 0
        config.INDEX_OF_VIDEO       = 0
        config.INDEX_OF_All_FRAME   = 0
        config.INDEX_OF_GPS         = 0
        config.INDEX_OF_SING        = 0

    def _create_queues(self) -> None:
        """
        Создаёт очереди с ограниченным размером.
        Предотвращает неконтролируемый рост памяти.
        """
        self._frame_q  = queue.Queue(maxsize=self.FRAME_QUEUE_SIZE)
        self._result_q = queue.Queue(maxsize=self.RESULT_QUEUE_SIZE)
        
        logger = logging.getLogger(__name__)
        logger.debug(f"[ProcessingController] Очереди созданы:")
        logger.debug(f"  frame_queue:  maxsize={self.FRAME_QUEUE_SIZE}")
        logger.debug(f"  result_queue: maxsize={self.RESULT_QUEUE_SIZE}")

    def _start_reader(self) -> None:
        self._reader = VideoReaderThread(self._frame_q, parent=self)
        self._reader.started_reading.connect(
            lambda total: self.progress.emit(0, total)
        )
        self._reader.progress.connect(self.progress)
        self._reader.video_switched.connect(self.video_switched)
        self._reader.error.connect(self.error)
        self._reader.finished_reading.connect(self._on_reader_finished)
        self._reader.start()

    def _start_detector(self) -> None:
        # BLOCK SIGN-LOSS-2: передаём данные восстановления если есть
        checkpoint_signs = None
        if self._resume_from_checkpoint and self._checkpoint_data:
            checkpoint_signs = self._checkpoint_data.get('signs')
        
        self._detector = DetectorThread(
            self._frame_q, self._result_q, 
            controller=self,  # передаём self для checkpoint
            checkpoint_signs=checkpoint_signs,  # BLOCK SIGN-LOSS-2
            parent=self
        )
        # Единый обработчик кадров для потокобезопасной конвертации в QPixmap
        self._detector.frame_ready.connect(self._on_worker_frame_ready)
        self._detector.sign_detected.connect(self.sign_found)
        self._detector.stats_updated.connect(self.stats)
        self._detector.error.connect(self.error)
        self._detector.finished_work.connect(self._on_detector_finished)
        self._detector.start()
        
        # BLOCK SIGN-LOSS-2: одноразовое восстановление — данные переданы, флаг больше не нужен
        self._resume_from_checkpoint = False
        self._checkpoint_data = None
    
    def _start_process_pool(self) -> None:
        """Запускает многопроцессный пул детекции (новый ProcessPoolExecutor-based)."""
        from processing.detector_process_pool import DetectorProcessPool
        from configs.settings import get_app_settings
        import logging
        
        # BLOCK FIX-3.3: Предупреждение о дублировании моделей на CPU
        settings = get_app_settings()
        logger = logging.getLogger(__name__)
        
        # BLOCK SIGN-LOSS-2 SHOULD: предупреждение о неподдержке checkpoint в process_pool
        if self._resume_from_checkpoint:
            logger.warning(
                "[ProcessingController] Восстановление знаков из checkpoint пока "
                "поддерживается только в режимах 'Один поток'/'Pipeline'. "
                "В Process Pool будут восстановлены только индексы позиции, "
                "но НЕ ранее найденные знаки."
            )
            # Сбрасываем флаг, чтобы он не мешал следующим запускам
            self._resume_from_checkpoint = False
            self._checkpoint_data = None
        
        if not settings.use_cuda:
            n_workers = config.N_WORKERS if config.N_WORKERS else (mp.cpu_count() - 1)
            logger.warning(
                f"[ProcessingController] Process Pool на CPU: каждый из {n_workers} воркеров "
                f"загрузит собственную копию всех моделей (~2-3 ГБ каждая). "
                f"Рекомендуется режим 'Один поток' для CPU."
            )
        
        self._detector_pool = DetectorProcessPool(
            self._frame_q,
            parent=self
        )
        # Единый обработчик кадров для потокобезопасной конвертации в QPixmap
        self._detector_pool.frame_ready.connect(self._on_worker_frame_ready)
        self._detector_pool.stats_updated.connect(self.stats)
        self._detector_pool.error.connect(self.error)
        self._detector_pool.finished_work.connect(self._on_detector_finished)
        self._detector_pool.start()
    
    def _on_worker_frame_ready(self, frame_data):
        """
        Единый обработчик кадров от ЛЮБОГО источника детекции.
        Выполняется в главном потоке — здесь и только здесь можно создавать QPixmap.
        
        Обрабатывает кадры от:
        - DetectorThread (single_thread / pipeline режимы)
        - DetectorProcessPool (process_pool режим)
        
        Все воркеры теперь отправляют dict с сериализованными данными
        (через build_frame_dict), а не готовый QPixmap.
        
        См. processing/preview_utils.py для архитектурного обоснования.
        """
        from processing.preview_utils import build_pixmap_from_frame_dict, build_frame_dict
        import numpy as np
        import logging
        
        logger = logging.getLogger(__name__)
        
        try:
            # Основной путь: dict с image_bytes (потокобезопасный)
            if isinstance(frame_data, dict) and 'image_bytes' in frame_data:
                logger.debug(f"[ProcessingController] Получен dict с image: shape={frame_data['shape']}")
                pixmap = build_pixmap_from_frame_dict(frame_data)
                logger.debug(f"[ProcessingController] QPixmap создан: {pixmap.width()}x{pixmap.height()}")
                self.frame_ready.emit(pixmap)
                
            # Fallback: numpy array напрямую (для обратной совместимости)
            elif isinstance(frame_data, np.ndarray):
                logger.debug(f"[ProcessingController] Получен numpy array напрямую: {frame_data.shape}")
                pixmap = build_pixmap_from_frame_dict(build_frame_dict(frame_data))
                self.frame_ready.emit(pixmap)
                
            else:
                # Последний fallback: готовый QPixmap (не должно случаться после рефакторинга)
                logger.warning(f"[ProcessingController] Получен неожиданный тип: {type(frame_data)}")
                self.frame_ready.emit(frame_data)
                
        except Exception as e:
            logger.error(f"[ProcessingController] Ошибка конвертации кадра: {e}", exc_info=True)

    def _on_reader_finished(self) -> None:
        # Ридер закончил — детектор доработает остаток очереди сам
        pass

    def _on_detector_finished(self) -> None:
        self._running = False
        self._stop_checkpoint_timer()
        self.finished.emit()
    
    # ── Автосохранение checkpoint ─────────────────────────────────
    
    def _start_checkpoint_timer(self) -> None:
        """Запускает периодическое автосохранение."""
        import time
        self._last_checkpoint_time = time.time()
        # Checkpoint будет вызываться из DetectorThread при обработке кадров
    
    def _stop_checkpoint_timer(self) -> None:
        """Останавливает автосохранение."""
        self._last_checkpoint_time = 0
    
    def save_checkpoint(self) -> None:
        """
        Сохраняет текущий прогресс обработки в checkpoint файл.
        Вызывается автоматически каждые CHECKPOINT_INTERVAL секунд.
        """
        import time
        import joblib
        import os
        
        now = time.time()
        
        # Throttling — сохраняем не чаще чем раз в N секунд
        if (self._last_checkpoint_time > 0 and 
            now - self._last_checkpoint_time < self.CHECKPOINT_INTERVAL):
            return
        
        self._last_checkpoint_time = now
        
        # Получаем SignHandler (из детектора или пула)
        sign_handler = None
        detector = None
        
        if self._detector_pool and hasattr(self._detector_pool, '_sign_handler'):
            sign_handler = self._detector_pool._sign_handler
        elif self._detector and hasattr(self._detector, '_sign_handler'):
            sign_handler = self._detector._sign_handler
            detector = self._detector
        else:
            return  # Нет данных для сохранения
        
        if not sign_handler:
            return
        
        try:
            checkpoint_data = {
                'version': '1.0',
                'timestamp': now,
                'config': {
                    'INDEX_OF_FRAME': config.INDEX_OF_FRAME,
                    'INDEX_OF_VIDEO': config.INDEX_OF_VIDEO,
                    'INDEX_OF_All_FRAME': config.INDEX_OF_All_FRAME,
                    'INDEX_OF_GPS': config.INDEX_OF_GPS,
                    'FRAME_STEP': config.FRAME_STEP,
                    'VIDEOS': config.VIDEOS,
                    'PATH_TO_VIDEO': config.PATH_TO_VIDEO,
                    'PATH_TO_GPX': config.PATH_TO_GPX,
                    'PATH_TO_GEOJSON': config.PATH_TO_GEOJSON,
                },
                'signs': {
                    'result_signs': sign_handler.result_signs,
                    'active_signs': sign_handler.signs,
                    'turns': sign_handler.turns,
                },
                'stats': {
                    'frames_processed': detector._frames_processed if detector else 0,
                    'signs_found': detector._signs_found if detector else 0,
                }
            }
            
            # Сохраняем во временный файл, потом переименовываем (атомарность)
            temp_path = f"{self.CHECKPOINT_PATH}.tmp"
            joblib.dump(checkpoint_data, temp_path, compress=3)
            
            # Атомарная замена
            if os.path.exists(self.CHECKPOINT_PATH):
                os.remove(self.CHECKPOINT_PATH)
            os.rename(temp_path, self.CHECKPOINT_PATH)
            
            logger.info(f"[Checkpoint] Сохранено: {len(sign_handler.result_signs)} знаков, "
                       f"кадр {config.INDEX_OF_All_FRAME}, видео {config.INDEX_OF_VIDEO}")
        
        except Exception as e:
            logger.error(f"[Checkpoint] Ошибка сохранения: {e}")
    
    def load_checkpoint(self) -> bool:
        """
        Загружает checkpoint и восстанавливает состояние.
        
        Returns:
            bool: True если checkpoint загружен успешно
        """
        import joblib
        import os
        
        logger = logging.getLogger(__name__)
        
        if not os.path.exists(self.CHECKPOINT_PATH):
            logger.debug("[Checkpoint] Файл не найден")
            return False
        
        try:
            checkpoint_data = joblib.load(self.CHECKPOINT_PATH)
            
            # Восстанавливаем config
            cfg = checkpoint_data['config']
            config.INDEX_OF_FRAME = cfg['INDEX_OF_FRAME']
            config.INDEX_OF_VIDEO = cfg['INDEX_OF_VIDEO']
            config.INDEX_OF_All_FRAME = cfg['INDEX_OF_All_FRAME']
            config.INDEX_OF_GPS = cfg['INDEX_OF_GPS']
            config.FRAME_STEP = cfg['FRAME_STEP']
            config.VIDEOS = cfg['VIDEOS']
            config.PATH_TO_VIDEO = cfg['PATH_TO_VIDEO']
            config.PATH_TO_GPX = cfg['PATH_TO_GPX']
            config.PATH_TO_GEOJSON = cfg['PATH_TO_GEOJSON']
            
            # BLOCK SIGN-LOSS-2: сохраняем данные и выставляем флаг восстановления
            self._checkpoint_data = checkpoint_data
            self._resume_from_checkpoint = True
            
            logger.info(f"[Checkpoint] Загружено: {len(checkpoint_data['signs']['result_signs'])} знаков, "
                       f"кадр {config.INDEX_OF_All_FRAME}, видео {config.INDEX_OF_VIDEO}")
            
            return True
        
        except Exception as e:
            logger.error(f"[Checkpoint] Ошибка загрузки: {e}")
            self._resume_from_checkpoint = False
            self._checkpoint_data = None
            return False
            logger.error(f"[Checkpoint] Ошибка загрузки: {e}")
            return False
    def delete_checkpoint(self) -> None:
        """Удаляет checkpoint файл."""
        import os
        
        if os.path.exists(self.CHECKPOINT_PATH):
            try:
                os.remove(self.CHECKPOINT_PATH)
                print("[Checkpoint] Удалён")
            except Exception as e:
                print(f"[Checkpoint] Ошибка удаления: {e}")
    
    def has_checkpoint(self) -> bool:
        """Проверяет наличие checkpoint файла."""
        import os
        return os.path.exists(self.CHECKPOINT_PATH)
    
    # ── BLOCK CPU-6: Backend verify (асинхронно) ──────────────────
    
    def _start_backend_verify(self, requested_backend: str) -> None:
        """
        Запускает асинхронную проверку backend'ов моделей.
        
        Args:
            requested_backend: Ожидаемый backend ('onnx' или 'openvino')
        
        Note:
            Работает параллельно с запуском VideoReader/DetectorThread.
            Не блокирует UI и не блокирует начало обработки.
        """
        from processing.backend_verify_thread import BackendVerifyThread
        
        self._backend_verify_thread = BackendVerifyThread(self)
        self._backend_verify_thread.finished_check.connect(
            lambda status: self._on_backend_verify_finished(requested_backend, status)
        )
        self._backend_verify_thread.error.connect(
            lambda msg: logging.getLogger(__name__).warning(
                f"[ProcessingController] backend verify error: {msg}"
            )
        )
        self._backend_verify_thread.start()
    
    def _on_backend_verify_finished(self, requested_backend: str, backend_status: dict) -> None:
        """
        Обработчик завершения проверки backend'ов.
        
        Args:
            requested_backend: Ожидаемый backend
            backend_status: Результат проверки {model_name: backend_or_error}
        """
        mismatched = {k: v for k, v in backend_status.items()
                      if not str(v).startswith("ERROR") and v != requested_backend}
        
        if mismatched:
            msg = (
                f"Backend '{requested_backend}' запрошен в настройках, но реально "
                f"не используется для {len(mismatched)} моделей: {list(mismatched.keys())}. "
                f"Проверьте экспорт моделей (scripts/export_models_onnx.py --format {requested_backend})."
            )
            logging.getLogger(__name__).warning(msg)
            self.error.emit(f"⚠️ ПРЕДУПРЕЖДЕНИЕ: {msg}")