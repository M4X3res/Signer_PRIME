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

    # Размер буфера между ридером и детектором
    FRAME_QUEUE_SIZE = 8

    def __init__(self, parent: Optional[QObject] = None):
        super().__init__(parent)
        self._reader:   Optional[VideoReaderThread] = None
        self._detector: Optional[DetectorThread]    = None
        self._frame_q:  Optional[queue.Queue]       = None
        self._result_q: Optional[queue.Queue]       = None
        self._running   = False

    # ── Public API ────────────────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    def start(self) -> None:
        if self._running:
            return
        self._reset_config()
        self._create_queues()
        self._start_reader()
        self._start_detector()
        self._running = True

    def stop(self) -> None:
        """Немедленная остановка — знаки не сохраняются."""
        if self._reader:
            self._reader.stop()
        if self._detector:
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
        Мягкая остановка — дожидаемся конца текущего видео,
        затем сохраняем GeoJSON через FinalHandler.
        """
        if self._reader:
            self._reader.stop()
        # DetectorThread сам завершится когда получит _STOP из очереди

    def get_result_signs(self) -> list:
        """Забрать накопленные знаки из очереди результатов."""
        results = []
        if not self._result_q:
            return results
        while True:
            try:
                results.append(self._result_q.get_nowait())
            except queue.Empty:
                break
        return results

    def get_turn_data(self) -> list:
        """Данные о поворотах из DetectorThread."""
        if self._detector and hasattr(self._detector, "_sign_handler"):
            return self._detector._sign_handler.turns
        return []

    # ── Private ───────────────────────────────────────────────────

    def _reset_config(self) -> None:
        config.FRAME_STEP           = 5
        config.COUNT_PROCESSED_FRAMES = 0
        config.INDEX_OF_FRAME       = 0
        config.INDEX_OF_VIDEO       = 0
        config.INDEX_OF_All_FRAME   = 0
        config.INDEX_OF_GPS         = 0
        config.INDEX_OF_SING        = 0

    def _create_queues(self) -> None:
        self._frame_q  = queue.Queue(maxsize=self.FRAME_QUEUE_SIZE)
        self._result_q = queue.Queue()

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
        self._detector = DetectorThread(
            self._frame_q, self._result_q, parent=self
        )
        self._detector.frame_ready.connect(self.frame_ready)
        self._detector.sign_detected.connect(self.sign_found)
        self._detector.stats_updated.connect(self.stats)
        self._detector.error.connect(self.error)
        self._detector.finished_work.connect(self._on_detector_finished)
        self._detector.start()

    def _on_reader_finished(self) -> None:
        # Ридер закончил — детектор доработает остаток очереди сам
        pass

    def _on_detector_finished(self) -> None:
        self._running = False
        self.finished.emit()