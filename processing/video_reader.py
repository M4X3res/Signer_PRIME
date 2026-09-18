"""
threading/video_reader.py
VideoReaderThread — единственная ответственность: читать кадры из видеофайлов
и класть их в очередь для DetectorThread.
Не занимается детекцией, GPS, UI.

ВАЖНО: Для GoPro видео используется MSMF бэкенд (Windows Media Foundation).
FFMPEG падает на ~44 кадре из-за множественных потоков в MP4 (видео+GPS+акселерометр).
"""
from __future__ import annotations
import logging
import os

# Оставляем для совместимости, но MSMF бэкенд не нуждается в этом
os.environ["OPENCV_FFMPEG_READ_ATTEMPTS"] = "100000"

import queue
import time
from dataclasses import dataclass
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from configs import config
from core.profiler import profiler

logger = logging.getLogger(__name__)

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
    
    # BLOCK STAB-3: константы для устойчивости к сбоям grab()
    GRAB_RETRY_ATTEMPTS = 3        # количество попыток при сбое grab()
    GRAB_RETRY_DELAY_S  = 0.05     # задержка между попытками
    FRAME_COUNT_SAFETY_MARGIN = 1.02  # запас на неточность cv2 CAP_PROP_FRAME_COUNT
    VIDEO_REOPEN_ATTEMPTS = 2      # количество попыток переоткрыть видео при стойком сбое

    def __init__(
        self,
        frame_queue: queue.Queue,
        parent=None,
    ):
        super().__init__(parent)
        self._queue   = frame_queue
        self._stop    = False
        self._paused  = False
        self._next_cap = None  # Prefetched VideoCapture для следующего видео

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

    # ── Helper: открытие видео с fallback бэкендами ───────────────

    def _open_video_with_fallback(self, video_path: str, start_frame: int = 0) -> Optional[cv2.VideoCapture]:
        """
        Открывает видео, пробуя разные бэкенды.
        Если start_frame > 0, позиционируется на этот кадр.
        
        Returns:
            VideoCapture или None если не удалось открыть
        """
        backends_to_try = [
            (cv2.CAP_MSMF, "MSMF (Windows Media Foundation)"),
            (cv2.CAP_DSHOW, "DirectShow"),
            (cv2.CAP_FFMPEG, "FFMPEG"),
            (cv2.CAP_ANY, "Auto"),
        ]
        
        for backend_id, backend_name in backends_to_try:
            try:
                test_cap = cv2.VideoCapture(video_path, backend_id)
                if not test_cap.isOpened():
                    test_cap.release()
                    logger.debug(f"[VideoReader] Бэкенд {backend_name} не открыл файл")
                    continue
                
                # Проверяем что можем читать кадры
                ret = test_cap.grab()
                if not ret:
                    test_cap.release()
                    logger.warning(f"[VideoReader] ⚠️ Бэкенд {backend_name} открыл файл, но не может читать кадры")
                    continue
                
                # Бэкенд работает! Позиционируемся если нужно
                if start_frame > 0:
                    # Для GoPro set() не надежен, читаем и пропускаем кадры
                    test_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    for _ in range(start_frame):
                        if not test_cap.grab():
                            logger.warning(f"[VideoReader] Не удалось перемотать до кадра {start_frame}")
                            test_cap.release()
                            break
                    else:
                        # Успешно перемотали
                        actual_backend = test_cap.getBackendName()
                        logger.info(f"[VideoReader] ✅ Переоткрыли видео с {backend_name} (actual: {actual_backend}), позиция: кадр {start_frame}")
                        test_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                        return test_cap
                else:
                    # start_frame == 0, начинаем с начала
                    test_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    actual_backend = test_cap.getBackendName()
                    logger.info(f"[VideoReader] ✅ Используем бэкенд: {backend_name} (actual: {actual_backend})")
                    test_cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
                    return test_cap
                    
            except Exception as e:
                logger.warning(f"[VideoReader] Ошибка при попытке использовать {backend_name}: {e}")
                continue
        
        logger.error(f"[VideoReader] ❌ Все бэкенды не смогли открыть видео")
        return None

    # ── Main loop ─────────────────────────────────────────────────

    def run(self) -> None:
        try:
            self._read_all_videos()
        except Exception as e:
            logger.error(f"Ошибка чтения видео: {e}")
            self.error.emit(str(e))
        finally:
            self._queue.put(_STOP)
            self.finished_reading.emit()

    def _read_all_videos(self) -> None:
        total = self._count_total_frames()
        self.started_reading.emit(total)

        abs_frame  = config.INDEX_OF_FRAME + (config.FRAMES_PER_VIDEO * config.INDEX_OF_VIDEO)
        gps_index  = int(round(abs_frame / config.VIDEO_FPS, 0))  # BLOCK J.2: используем реальный FPS
        
        # Fix 2.4: Используем logging вместо прямого file I/O
        # Создаём отдельный logger для video debug
        video_logger = logging.getLogger(f"{__name__}.video_debug")
        video_logger.setLevel(logging.DEBUG)
        
        # log_path нужен ниже (ветка "SKIPPED") независимо от того, создаём ли мы
        # FileHandler в этом вызове, или он уже был создан предыдущим запуском.
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "video_debug.log")
        if not any(isinstance(h, logging.FileHandler) for h in video_logger.handlers):
            file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
            file_handler.setFormatter(logging.Formatter('%(message)s'))
            video_logger.addHandler(file_handler)
        
        video_logger.info("=== VideoReader Debug Log ===")
        video_logger.info(f"START: INDEX_OF_VIDEO={config.INDEX_OF_VIDEO}, INDEX_OF_FRAME={config.INDEX_OF_FRAME}")
        video_logger.info(f"Total videos: {len(config.VIDEOS)}\n")

        for video_idx, video_name in enumerate(config.VIDEOS):
            if self._stop:
                break

            # Пропускаем видео, которые уже обработаны
            if video_idx < config.INDEX_OF_VIDEO:
                video_logger.info(f"[VIDEO {video_idx}] SKIPPED: {video_name}")
                self.video_switched.emit(video_idx, video_name)
                continue

            video_path = os.path.join(config.PATH_TO_VIDEO, video_name)
            
            # Используем prefetched VideoCapture если доступен
            if self._next_cap is not None:
                logger.info(f"[VideoReader] Используем prefetched VideoCapture для {video_name}")
                cap = self._next_cap
                self._next_cap = None
            else:
                cap = self._open_video_with_fallback(video_path)
            
            if cap is None or not cap.isOpened():
                self.error.emit(f"Не удалось открыть {video_name}")
                continue
            
            # Читаем метаданные видео и сохраняем в config (BLOCK 2: для bearing geometry)
            config.FRAME_WIDTH = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            config.FRAME_HEIGHT = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            
            # BLOCK J.2: Читаем реальный FPS видео
            fps = cap.get(cv2.CAP_PROP_FPS)
            if fps > 0:
                config.VIDEO_FPS = fps
            else:
                config.VIDEO_FPS = 60.0  # Fallback если метаданные некорректны
            
            logger.info(f"[VideoReader] Видео: {config.FRAME_WIDTH}x{config.FRAME_HEIGHT}, FPS: {config.VIDEO_FPS:.2f}")
            
            # Минимальный буфер для уменьшения задержки
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)

            self.video_switched.emit(video_idx, video_name)
            
            # Инициализация счетчиков
            local_frame = 0
            frames_read = 0
            frame_in_video = 0

            # Если это первое обрабатываемое видео — начинаем с сохранённой позиции
            if video_idx == config.INDEX_OF_VIDEO and config.INDEX_OF_FRAME > 0:
                # ДЛЯ GOPRO: cap.set() не работает надежно - нужно читать и пропускать кадры
                # Пропускаем кадры вручную
                for _ in range(config.INDEX_OF_FRAME):
                    ret, _ = cap.read()
                    if not ret:
                        break
                local_frame = config.INDEX_OF_FRAME
                frame_in_video = config.INDEX_OF_FRAME

            total_frames_in_video = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

            # Для некоторых форматов (GoPro) total_frames может быть 0 —
            # читаем до конца файла без ограничения по числу кадров
            use_frame_limit = total_frames_in_video > 0

            # Fix 2.4: Используем video_logger вместо file I/O
            video_logger.info(f"[VIDEO {video_idx}] START: {video_name}")
            video_logger.info(f"  total_frames={total_frames_in_video}, starting_frame={frame_in_video}")
            video_logger.info(f"  backend={cap.getBackendName()}, fourcc={cap.get(cv2.CAP_PROP_FOURCC)}")
            video_logger.info(f"  fps={cap.get(cv2.CAP_PROP_FPS)}, use_frame_limit={use_frame_limit}")
            
            # Счетчик для пропуска кадров (как в старом коде)
            frame_counter = 0
            
            while True:
                if self._stop:
                    break

                while self._paused:
                    time.sleep(0.05)

                step = max(1, int(config.FRAME_STEP))

                # Выходим если прошли весь файл, с небольшим запасом (BLOCK
                # STAB-3): CAP_PROP_FRAME_COUNT у некоторых форматов (GoPro
                # поверх MSMF) бывает слегка занижен, из-за чего чтение
                # обрывалось раньше реального конца файла и обработка
                # «сама» заканчивалась досрочно. Настоящим признаком конца
                # файла считаем повторный сбой grab() (см. ниже), а не
                # только формальный лимит по метаданным.
                if use_frame_limit and local_frame >= int(total_frames_in_video * self.FRAME_COUNT_SAFETY_MARGIN):
                    video_logger.info(f"[VIDEO {video_idx}] END (limit reached): frames_read={frames_read}, local_frame={local_frame}/{total_frames_in_video}\n")
                    logger.info(f"[VIDEO {video_idx}] Завершено по лимиту: прочитано {frames_read} кадров, local_frame={local_frame}")
                    break

                # КРИТИЧНО: Читаем КАЖДЫЙ кадр последовательно (как в старом коде)
                # Это единственный способ который работает с GoPro
                # ═══════════════════════════════════════════════════════════════
                # ОПТИМИЗАЦИЯ (BLOCK CPU-1): grab() вместо read() для пропускаемых кадров
                # ═══════════════════════════════════════════════════════════════
                # Дешёвый grab() сначала — только захват следующего кадра из потока
                # Полное декодирование (retrieve()) — только если кадр будет использован
                
                with profiler.measure("video_grab_frame"):
                    grabbed = cap.grab()

                if not grabbed:
                    # BLOCK STAB-3: не считаем это сразу концом видео —
                    # даём несколько попыток с небольшой паузой. Это может
                    # быть кратковременный сбой чтения multi-stream MP4
                    # (видео + GPS + акселерометр), а не реальный EOF.
                    for attempt in range(self.GRAB_RETRY_ATTEMPTS):
                        time.sleep(self.GRAB_RETRY_DELAY_S)
                        grabbed = cap.grab()
                        if grabbed:
                            video_logger.info(
                                f"  Frame {local_frame}: grab retry succeeded "
                                f"(attempt {attempt + 1}/{self.GRAB_RETRY_ATTEMPTS})"
                            )
                            break

                # Логируем первые 50 кадров для диагностики
                if local_frame < 50:
                    video_logger.debug(f"  Frame {local_frame}: grabbed={grabbed}")
                
                if not grabbed:
                    # GoPro RECOVERY: Попытка переоткрыть видео и продолжить
                    # Это может помочь при рассинхронизации multi-stream MP4
                    current_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
                    
                    # Проверяем что это не конец файла
                    if local_frame < int(total_frames_in_video * 0.95):  # Если меньше 95% видео
                        logger.warning(
                            f"[VIDEO {video_idx}] Grab failed на кадре {local_frame}/{total_frames_in_video} "
                            f"({local_frame/total_frames_in_video*100:.1f}%). Пытаемся переоткрыть видео..."
                        )
                        video_logger.info(
                            f"[VIDEO {video_idx}] Пытаемся переоткрыть видео и продолжить с кадра {local_frame}"
                        )
                        
                        # Закрываем текущий захват
                        cap.release()
                        
                        # Пытаемся переоткрыть и продолжить
                        for reopen_attempt in range(self.VIDEO_REOPEN_ATTEMPTS):
                            new_cap = self._open_video_with_fallback(video_path, start_frame=local_frame)
                            if new_cap is not None and new_cap.isOpened():
                                # Проверяем что новый захват может читать
                                test_grab = new_cap.grab()
                                if test_grab:
                                    logger.info(
                                        f"[VIDEO {video_idx}] ✅ Видео переоткрыто успешно, "
                                        f"продолжаем с кадра {local_frame} (попытка {reopen_attempt + 1})"
                                    )
                                    video_logger.info(
                                        f"  Reopen successful (attempt {reopen_attempt + 1}), continuing from frame {local_frame}"
                                    )
                                    cap = new_cap
                                    grabbed = True
                                    break
                                else:
                                    new_cap.release()
                                    logger.warning(
                                        f"[VIDEO {video_idx}] Переоткрытое видео не может читать кадры "
                                        f"(попытка {reopen_attempt + 1}/{self.VIDEO_REOPEN_ATTEMPTS})"
                                    )
                            else:
                                logger.warning(
                                    f"[VIDEO {video_idx}] Не удалось переоткрыть видео "
                                    f"(попытка {reopen_attempt + 1}/{self.VIDEO_REOPEN_ATTEMPTS})"
                                )
                                if new_cap is not None:
                                    new_cap.release()
                            
                            time.sleep(0.1)  # Небольшая пауза перед следующей попыткой
                        
                        if not grabbed:
                            logger.error(
                                f"[VIDEO {video_idx}] ❌ Не удалось переоткрыть видео после "
                                f"{self.VIDEO_REOPEN_ATTEMPTS} попыток. Завершаем обработку этого видео."
                            )
                            video_logger.info(
                                f"[VIDEO {video_idx}] END (reopen failed): frames_read={frames_read}, "
                                f"local_frame={local_frame}/{total_frames_in_video}\n"
                            )
                            break
                        # Если grabbed == True, продолжаем обработку с переоткрытым файлом
                    else:
                        # Похоже на реальный конец файла
                        video_logger.info(
                            f"[VIDEO {video_idx}] END (grab failed after {self.GRAB_RETRY_ATTEMPTS} retries): "
                            f"frames_read={frames_read}, local_frame={local_frame}/{total_frames_in_video}"
                        )
                        video_logger.info(f"  CAP_PROP_POS_FRAMES: {current_pos}")
                        video_logger.info(f"  CAP_PROP_FRAME_COUNT: {cap.get(cv2.CAP_PROP_FRAME_COUNT)}")
                        video_logger.info(f"  isOpened: {cap.isOpened()}\n")
                        logger.info(
                            f"[VIDEO {video_idx}] Завершено: не удалось захватить кадр {local_frame} "
                            f"после повторов, прочитано {frames_read} кадров"
                        )
                        break
                
                local_frame += 1
                frame_counter += 1
                
                # Обрабатываем только каждый FRAME_STEP-й кадр (как в старом коде)
                if frame_counter % step != 0:
                    # Кадр пропускается — НЕ вызываем retrieve(), экономим декодирование
                    continue
                
                # ═══════════════════════════════════════════════════════════════
                # Полное декодирование — только для обрабатываемого кадра
                # ═══════════════════════════════════════════════════════════════
                with profiler.measure("video_retrieve_frame"):
                    ret, image = cap.retrieve()
                
                if not ret or image is None:
                    video_logger.info(f"[VIDEO {video_idx}] END (retrieve failed): frames_read={frames_read}, local_frame={local_frame}, ret={ret}, image={'None' if image is None else 'OK'}\n")
                    logger.warning(f"[VIDEO {video_idx}] Ошибка retrieve() на кадре {local_frame}")
                    break
                
                # Этот кадр обрабатываем
                frames_read += 1
                
                # frame_in_video и abs_frame соответствуют local_frame
                frame_in_video = local_frame
                
                # GPS синхронизация: 1 GPS точка ≈ 60 кадров
                # abs_frame = начальная позиция + local_frame текущего видео
                if video_idx == 0:
                    abs_frame = local_frame
                else:
                    # Для видео после первого нужно учесть все предыдущие
                    abs_frame = (video_idx * config.FRAMES_PER_VIDEO) + local_frame
                
                # Лог каждые 100 кадров для контроля прогресса
                if frames_read % 100 == 0:
                    video_logger.debug(f"  Progress: {frames_read} frames read, local={local_frame}/{total_frames_in_video}, abs={abs_frame}")
                    logger.info(f"[VIDEO {video_idx}] Прогресс: {frames_read} кадров, local_frame={local_frame}/{total_frames_in_video}")
                
                # BLOCK FIX-3.1: используем реальный VIDEO_FPS вместо захардкоженного 60
                if (abs_frame - gps_index * config.VIDEO_FPS) > config.VIDEO_FPS:
                    gps_index += 1

                raw = RawFrame(
                    image            = image,
                    frame_number     = frame_in_video,
                    abs_frame_number = abs_frame,
                    video_index      = video_idx,
                    video_name       = video_name,
                    gps_index        = gps_index,
                )

                # Backpressure — ждём пока DetectorThread освободит очередь
                while not self._stop:
                    try:
                        self._queue.put(raw, timeout=0.5)
                        break
                    except queue.Full:
                        continue

                self.progress.emit(abs_frame, total)

            # Prefetch следующего видео (если есть) за ~500 кадров до конца текущего
            if (self._next_cap is None and 
                video_idx < len(config.VIDEOS) - 1 and 
                use_frame_limit and 
                local_frame > total_frames_in_video - 500):
                self._prefetch_next_video(video_idx + 1)

            cap.release()
            
            # Используем prefetched cap для следующего видео (если есть)
            if self._next_cap is not None and video_idx < len(config.VIDEOS) - 1:
                logger.info(f"[VideoReader] Используем prefetched VideoCapture для видео {video_idx + 1}")
                # Следующая итерация цикла будет использовать self._next_cap через специальную проверку
    
    def _prefetch_next_video(self, next_video_idx: int) -> None:
        """
        Предзагрузка следующего видео в фоне.
        Открывает VideoCapture следующего файла заранее.
        """
        try:
            next_video_name = config.VIDEOS[next_video_idx]
            next_video_path = os.path.join(config.PATH_TO_VIDEO, next_video_name)
            
            logger.info(f"[VideoReader] Prefetch: открываем {next_video_name}...")
            
            self._next_cap = self._open_video_with_fallback(next_video_path)
            
            if self._next_cap is not None and self._next_cap.isOpened():
                logger.info(f"[VideoReader] ✅ Prefetch успешен для {next_video_name}")
            else:
                logger.warning(f"[VideoReader] ⚠️ Prefetch не удался для {next_video_name}")
                self._next_cap = None
                
        except Exception as e:
            logger.error(f"[VideoReader] Ошибка prefetch: {e}")
            self._next_cap = None

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