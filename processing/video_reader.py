"""
threading/video_reader.py
VideoReaderThread — единственная ответственность: читать кадры из видеофайлов
и класть их в очередь для DetectorThread.
Не занимается детекцией, GPS, UI.
"""
from __future__ import annotations
import os
import queue
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from configs import config


# Sentinel — означает конец потока кадров
_STOP = object()


@dataclass
class RawFrame:
    """Один сырой кадр из видео."""
    image:              np.ndarray
    frame_number:       int    # номер внутри текущего видеофайла
    abs_frame_number:   int    # глобальный номер по всем видео
    video_index:        int    # индекс видеофайла
    video_name:         str
    gps_index:          int    # соответствующий индекс GPS точки


class VideoReaderThread(QThread):
    """
    Читает кадры из списка mp4-файлов (config.VIDEOS).
    Каждый FRAME_STEP-й кадр кладёт в frame_queue.
    Сигналы:
        started(total_frames)
        progress(abs_frame, total_frames)
        video_switched(video_index, video_name)
        finished()
        error(message)
    """

    started_reading  = pyqtSignal(int)           # total_frames
    progress         = pyqtSignal(int, int)      # abs_frame, total
    video_switched   = pyqtSignal(int, str)      # idx, name
    finished_reading = pyqtSignal()
    error            = pyqtSignal(str)

    def __init__(
        self,
        frame_queue: queue.Queue,
        parent=None,
    ):
        super().__init__(parent)
        self._queue   = frame_queue
        self._stop    = False
        self._paused  = False

    # ── Control ───────────────────────────────────────────────────

    def stop(self) -> None:
        self._stop = True
        # Разблокируем очередь если детектор ждёт
        try:
            self._queue.put_nowait(_STOP)
        except queue.Full:
            pass

    def pause(self) -> None:
        self._paused = True

    def resume(self) -> None:
        self._paused = False

    # ── Main loop ─────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._read_all_videos()
        except Exception as e:
            self.error.emit(str(e))
        finally:
            self._queue.put(_STOP)
            self.finished_reading.emit()

    def _read_all_videos(self) -> None:
        total = self._count_total_frames()
        self.started_reading.emit(total)

        abs_frame  = config.INDEX_OF_FRAME + (63600 * config.INDEX_OF_VIDEO)
        gps_index  = int(round(abs_frame / 60, 0))

        for video_idx, video_name in enumerate(config.VIDEOS):
            if self._stop:
                break

            video_path = os.path.join(config.PATH_TO_VIDEO, video_name)
            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                self.error.emit(f"Не удалось открыть {video_name}")
                continue

            self.video_switched.emit(video_idx, video_name)
            frame_in_video = 0

            # Если это первое видео — начинаем с сохранённой позиции
            if video_idx == config.INDEX_OF_VIDEO:
                cap.set(cv2.CAP_PROP_POS_FRAMES, config.INDEX_OF_FRAME)
                frame_in_video = config.INDEX_OF_FRAME

            step_counter = 0

            while cap.isOpened():
                if self._stop:
                    break

                while self._paused:
                    time.sleep(0.05)

                ret, image = cap.read()
                if not ret:
                    break

                frame_in_video += 1
                abs_frame      += 1
                step_counter   += 1

                # GPS синхронизация: 1 GPS точка ≈ 60 кадров
                if (abs_frame - gps_index * 60) > 60:
                    gps_index += 1

                # Пропуск кадров согласно FRAME_STEP
                if step_counter < config.FRAME_STEP:
                    continue
                step_counter = 0

                raw = RawFrame(
                    image            = image,
                    frame_number     = frame_in_video,
                    abs_frame_number = abs_frame,
                    video_index      = video_idx,
                    video_name       = video_name,
                    gps_index        = gps_index,
                )

                # Блокируем если очередь полная (backpressure)
                while not self._stop:
                    try:
                        self._queue.put(raw, timeout=0.1)
                        break
                    except queue.Full:
                        continue

                self.progress.emit(abs_frame, total)

            cap.release()

    def _count_total_frames(self) -> int:
        """Быстрый подсчёт общего числа кадров по metadata."""
        total = 0
        for name in config.VIDEOS:
            path = os.path.join(config.PATH_TO_VIDEO, name)
            cap  = cv2.VideoCapture(path)
            if cap.isOpened():
                total += int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                cap.release()
        return total