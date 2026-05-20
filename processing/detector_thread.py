"""
threading/detector_thread.py
DetectorThread — берёт RawFrame из очереди, прогоняет через Detector,
передаёт результат в SignHandler, отправляет сигналы в UI.
Модели загружаются ОДИН РАЗ при создании треда.
"""
from __future__ import annotations

import queue
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal
from PyQt6.QtGui import QImage, QPixmap

from configs import config
from core.frame import DetectedSign
from processing.video_reader import RawFrame, _STOP


class DetectorThread(QThread):
    """
    Читает RawFrame из frame_queue.
    Детектирует знаки через Detector.
    Передаёт результат в SignHandler.
    Сигналы:
        frame_ready(QPixmap)              — кадр для UI
        sign_detected(str, str, float)    — тип, видео, уверенность
        stats_updated(int, int, float)    — frames, signs, fps
        finished()
        error(str)
    """

    frame_ready    = pyqtSignal(object)           # QPixmap
    sign_detected  = pyqtSignal(str, str, float)  # type, video, conf
    stats_updated  = pyqtSignal(int, int, float)  # frames, signs, fps
    finished_work  = pyqtSignal()
    error          = pyqtSignal(str)

    # Минимальная скорость (км/ч) для запуска детекции
    MIN_SPEED_KMH = 2.0

    def __init__(
        self,
        frame_queue: queue.Queue,
        result_queue: queue.Queue,
        parent=None,
    ):
        super().__init__(parent)
        self._frame_q  = frame_queue
        self._result_q = result_queue
        self._stop     = False

        # Объекты создаются в run() — уже внутри QThread
        # чтобы не загружать модели в главном потоке (краш на Windows)
        self._detector     = None
        self._sign_handler = None
        self._gpx          = None

        # Статистика
        self._frames_processed = 0
        self._signs_found      = 0
        self._fps_timer        = time.monotonic()
        self._fps_frames       = 0

    # ── Control ───────────────────────────────────────────────────

    def stop(self) -> None:
        self._stop = True

    # ── Main loop ─────────────────────────────────────────────────

    def run(self) -> None:
        # Загружаем модели здесь — внутри QThread, не в главном потоке
        try:
            from core.detector import Detector
            from core.sign_handler import SignHandler
            from GPXHandler import GPXHandler
            self._detector     = Detector()
            self._sign_handler = SignHandler()
            self._gpx          = GPXHandler()
        except Exception as e:
            self.error.emit(f"Ошибка загрузки моделей: {e}")
            self.finished_work.emit()
            return

        try:
            self._process_loop()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self.finished_work.emit()

    def _process_loop(self) -> None:
        from Turn import Turn
        turn = Turn()

        while not self._stop:
            try:
                raw = self._frame_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if raw is _STOP:
                break

            # Обновляем глобальные индексы (нужны старым модулям)
            config.INDEX_OF_FRAME      = raw.frame_number
            config.INDEX_OF_All_FRAME  = raw.abs_frame_number
            config.INDEX_OF_VIDEO      = raw.video_index
            config.INDEX_OF_GPS        = raw.gps_index

            # Пропускаем если машина стоит
            speed = self._gpx.get_speed(raw.gps_index)
            if speed is not None and speed < self.MIN_SPEED_KMH:
                self._emit_frame(raw.image)
                continue

            # Динамический FRAME_STEP по скорости
            if speed:
                config.FRAME_STEP = max(2, round(-0.5 * speed + 10.9))

            # Детекция
            detections = self._detector.find_rectangles(raw.image)

            # Конвертируем в DetectedSign
            detected = self._build_detected(detections, raw)

            # Трекинг
            turn = self._sign_handler.check_the_data_to_add(detected or None, turn)

            # Финальные знаки → в очередь результатов
            for sign in self._sign_handler.result_signs:
                self._result_q.put(sign)
            self._sign_handler.result_signs.clear()

            # UI
            annotated = self._draw_boxes(raw.image, detections)
            self._emit_frame(annotated)
            self._update_stats(len(detections))

            if detections:
                for det in detections:
                    self.sign_detected.emit(
                        det.number_sign,
                        raw.video_name,
                        0.0,   # confidence будет добавлен из Detector
                    )

    # ── Helpers ───────────────────────────────────────────────────

    def _build_detected(
        self,
        detections: list,
        raw: RawFrame,
    ) -> list[DetectedSign]:
        """
        Конвертирует raw-результат Detector в список DetectedSign.
        detections item: [box, color, label, class_name, res, text, isSide]
        """
        result = []
        lat, lon = config.INDEX_OF_GPS, 0.0
        try:
            lat, lon = self._gpx.get_current_coordinate(raw.gps_index)
        except Exception:
            pass

        for item in detections:
            box, _, _, class_name, cnn_class, text, is_side = item
            x, y, w, h = box
            result.append(DetectedSign(
                x=int(x), y=int(y), w=int(w), h=int(h),
                name_sign=class_name,
                number_sign=cnn_class,
                frame_number=raw.frame_number,
                absolute_frame_number=raw.abs_frame_number,
                latitude=lat,
                longitude=lon,
                text_on_sign=text or "",
                is_side=bool(is_side),
            ))
        return result

    def _draw_boxes(self, image: np.ndarray, detections: list) -> np.ndarray:
        """Рисует bounding boxes на кадре для предпросмотра."""
        frame = image.copy()
        for item in detections:
            box, color, label, *_ = item
            x, y, w, h = box
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame, label, (x, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
            )
        return frame

    def _emit_frame(self, image: np.ndarray) -> None:
        """Конвертирует BGR numpy → QPixmap и отправляет в UI."""
        rgb   = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg  = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            960, 540,
            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,  # type: ignore
        )
        self.frame_ready.emit(pixmap)

    def _update_stats(self, n_detections: int) -> None:
        self._frames_processed += 1
        self._signs_found      += n_detections
        self._fps_frames       += 1

        now = time.monotonic()
        elapsed = now - self._fps_timer
        if elapsed >= 1.0:
            fps = self._fps_frames / elapsed
            self._fps_timer  = now
            self._fps_frames = 0
            self.stats_updated.emit(
                self._frames_processed,
                self._signs_found,
                fps,
            )

    # Нужен для _emit_frame
    from PyQt6.QtCore import Qt