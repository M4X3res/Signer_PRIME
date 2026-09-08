"""
threading/detector_thread.py
DetectorThread — берёт RawFrame из очереди, прогоняет через Detector,
передаёт результат в SignHandler, отправляет сигналы в UI.
Модели загружаются ОДИН РАЗ при создании треда.
"""
from __future__ import annotations

import logging
import queue
import time
from typing import Optional

import cv2
import numpy as np
from PyQt6.QtCore import QThread, pyqtSignal

from configs import config
from core.frame import DetectedSign
from core.converter import Converter
from core.profiler import profiler
from processing.video_reader import RawFrame, _STOP

logger = logging.getLogger(__name__)


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

    def __init__(
        self,
        frame_queue: queue.Queue,
        result_queue: queue.Queue,
        controller=None,  # ProcessingController для checkpoint
        checkpoint_signs: Optional[dict] = None,  # BLOCK SIGN-LOSS-2: данные восстановления
        parent=None,
    ):
        super().__init__(parent)
        self._frame_q  = frame_queue
        self._result_q = result_queue
        self._controller = controller
        self._checkpoint_signs = checkpoint_signs  # BLOCK SIGN-LOSS-2
        self._stop     = False

        # Объекты создаются в run() — уже внутри QThread
        # чтобы не загружать модели в главном потоке (краш на Windows)
        self._detector     = None
        self._sign_handler = None
        self._gpx          = None
        
        # OCR Worker для pipeline режима
        self._ocr_worker   = None
        self._use_pipeline = False  # Определяется из настроек в run()
        self._using_ocr_pool = False  # True если используется OCRPool вместо QThread
        self._ocr_sign_counter = 0  # Счётчик для уникальных ID знаков
        self._pending_ocr = {}  # {sign_id: TrackedSign} для ожидания OCR

        # Статистика
        self._frames_processed = 0
        self._signs_found      = 0
        self._fps_timer        = time.monotonic()
        self._fps_frames       = 0
        
        # BLOCK CPU-7: Умный frame skipping (вынесено в отдельный модуль)
        from processing.frame_skip import SmartFrameSkipper
        self._skipper = SmartFrameSkipper()
        
        # ── UI Preview Throttling (BLOCK CPU-2) ───────────────────
        self._preview_min_interval = 0.0  # Будет установлено в run() из settings
        self._last_emit_time = 0.0
        
        # ── OCR Throttling (BLOCK CPU-4) ──────────────────────────
        self._ocr_calls_total = 0      # Всего OCR-вызовов
        self._ocr_calls_skipped = 0    # Пропущено благодаря троттлингу

    # ── Control ───────────────────────────────────────────────────

    def stop(self) -> None:
        self._stop = True
        
        # Не останавливаем OCR worker здесь - это делается в finally блоке run()
        # чтобы избежать двойного вызова и race condition

    # ── Main loop ─────────────────────────────────────────────────

    def run(self) -> None:
        # Ограничиваем OpenMP/MKL потоки torch внутри рабочего потока.
        # Это предотвращает краш 0xC0000409 (конфликт libiomp5md.dll с Qt).
        try:
            import torch
            torch.set_num_threads(1)
        except Exception:
            pass

        # Загружаем модели здесь — внутри QThread, не в главном потоке
        try:
            # Проверяем доступность GPU
            import torch
            cuda_available = torch.cuda.is_available()
            if cuda_available:
                gpu_name = torch.cuda.get_device_name(0)
                logger.info(f"✅ CUDA доступна: {gpu_name}")
            else:
                logger.warning("⚠️ CUDA недоступна - используется CPU")
                logger.info("Для ускорения установите CUDA-совместимую версию PyTorch")
            
            # Загружаем настройки
            from configs.settings import get_app_settings
            settings = get_app_settings()
            
            # Task E: Pipeline режим больше не выбирается из UI, всегда False
            self._use_pipeline = False
            
            # ── UI Preview Throttling (BLOCK CPU-2) ───────────────────
            # Ограничиваем частоту обновления превью в UI
            self._preview_min_interval = 1.0 / settings.preview_fps_limit if settings.preview_fps_limit > 0 else 0.0
            logger.info(f"📺 UI Preview: макс. {settings.preview_fps_limit} FPS (интервал {self._preview_min_interval:.3f}s)")
            
            from core.detector import Detector
            from core.sign_handler import SignHandler
            from core.gpx_handler import GPXHandler
            
            # Передаём настройки в классы обработки
            self._detector     = Detector(settings=settings)
            self._sign_handler = SignHandler(settings=settings)
            self._gpx          = GPXHandler()
            self._converter    = Converter()  # Для конвертации GPS координат
            
            # BLOCK SIGN-LOSS-2: восстанавливаем знаки из checkpoint, если есть
            if self._checkpoint_signs:
                restored_result = list(self._checkpoint_signs.get('result_signs', []))
                restored_active = list(self._checkpoint_signs.get('active_signs', []))
                restored_turns  = list(self._checkpoint_signs.get('turns', []))
                self._sign_handler.result_signs = restored_result
                self._sign_handler.signs        = restored_active
                self._sign_handler.turns        = restored_turns
                logger.info(
                    f"[Checkpoint] Восстановлено в SignHandler: "
                    f"{len(restored_result)} финализированных, "
                    f"{len(restored_active)} активных, {len(restored_turns)} поворотов"
                )
            
            # Логируем информацию о кэше
            logger.info(f"CNN кэш инициализирован: размер={self._detector._cnn_cache._maxsize}")
            
            # Task E: OCR Worker больше не запускается (pipeline режим удалён)
            # OCR всегда выполняется синхронно в single thread режиме
            logger.info("🔧 Режим: SINGLE THREAD — OCR выполняется синхронно (Task E)")
            self._using_ocr_pool = False
            
            # Прогреваем EasyOCR заранее
            logger.info("Прогрев EasyOCR...")
            try:
                from core.detector import _get_ocr
                ocr_reader = _get_ocr()
                logger.info("✅ EasyOCR прогрет успешно")
            except Exception as ocr_err:
                logger.warning(f"⚠️ Не удалось прогреть EasyOCR: {ocr_err}")
                logger.warning("OCR будет инициализирован при первом текстовом знаке")
            
        except Exception as e:
            self.error.emit(f"Ошибка загрузки моделей: {e}")
            self.finished_work.emit()
            return

        try:
            self._process_loop()
        except Exception as e:
            logger.exception(f"[DetectorThread] Необработанная ошибка в _process_loop: {e}")
            self.error.emit(str(e))
        finally:
            # БАГ E: Финализируем активные знаки в конце видео
            if self._sign_handler:
                logger.info("[DetectorThread] Финализация оставшихся активных знаков...")
                try:
                    self._sign_handler.finalize_remaining()
                except Exception as e:
                    logger.exception(f"[DetectorThread] Ошибка финализации активных знаков: {e}")
                
                # BLOCK SIGN-LOSS-1 FIX (finally block): Добавляем финализированные знаки в очередь результатов
                # с блокирующим put и попыткой для каждого знака, без break при первой ошибке
                if self._sign_handler.result_signs:
                    logger.debug(f"Финальная отправка {len(self._sign_handler.result_signs)} знаков в очередь")
                    lost = []
                    for sign in self._sign_handler.result_signs:
                        try:
                            self._result_q.put(sign, timeout=2.0)
                        except queue.Full:
                            lost.append(sign.best_cnn)
                    if lost:
                        logger.error(
                            f"[SignLoss-Guard] КРИТИЧНО: {len(lost)} знаков потеряны при финальной "
                            f"отправке (очередь не освободилась даже за 2с/знак): {lost}"
                        )
                    self._sign_handler.result_signs.clear()
            
            # Останавливаем OCR Worker если был запущен
            if self._ocr_worker:
                logger.info("[DetectorThread] Останавливаем OCR Worker...")
                if self._using_ocr_pool:
                    # OCRPool не имеет метода wait(), используем shutdown с wait=True
                    self._ocr_worker.stop(wait=True)
                else:
                    # OCRWorkerThread имеет метод wait()
                    self._ocr_worker.stop()
                    if hasattr(self._ocr_worker, 'wait'):
                        self._ocr_worker.wait(3000)  # Ждём до 3 секунд
                logger.info("[DetectorThread] OCR Worker остановлен")
            
            self.finished_work.emit()

    def _process_loop(self) -> None:
        from core.turn import Turn
        turn = Turn()
        
        self._frame_errors = 0  # BLOCK STAB-1: счётчик кадров, пропущенных из-за ошибок
        last_position_update = 0  # Для throttling обновлений позиции

        while not self._stop:
            try:
                raw = self._frame_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if raw is _STOP:
                break

            # BLOCK STAB-1: ошибка на ОДНОМ кадре больше не прерывает всю
            # обработку видео — она логируется, кадр пропускается, цикл
            # продолжает работу со следующего кадра. Раньше любое исключение
            # здесь (деление на ноль в геометрии, некорректные координаты и
            # т.п.) убивало весь while и приводило к тому, что обработка
            # «сама» завершалась намного раньше конца видео, при этом
            # выглядело это для пользователя как штатное завершение —
            # см. PROMPT_FIX_UX_STABILITY_THEME.md, Задача 2.
            try:
                turn, last_position_update = self._process_single_frame(
                    raw, turn, last_position_update
                )
            except Exception as e:
                self._frame_errors += 1
                logger.exception(
                    f"[DetectorThread] Ошибка обработки кадра "
                    f"abs_frame={raw.abs_frame_number}: {e}"
                )
                self.error.emit(
                    f"Пропущен кадр {raw.abs_frame_number} из-за ошибки: {e}"
                )
                continue

        if self._frame_errors:
            logger.warning(
                f"[DetectorThread] Обработка завершена: {self._frame_errors} "
                f"кадров были пропущены из-за ошибок обработки (см. лог выше)"
            )


    def _process_single_frame(self, raw, turn, last_position_update: int):
        """
        Обработка одного кадра. Вынесено из _process_loop() отдельным методом,
        чтобы вызывающий код мог обернуть один этот вызов в try/except и не
        терять весь прогон обработки видео из-за ошибки в единственном кадре.
        Логика ниже — это ровно то, что раньше было внутри while-цикла, без
        изменений поведения; изменилась только структура (extract method).
        """
        # Обновляем глобальные индексы (нужны старым модулям)
        config.INDEX_OF_FRAME      = raw.frame_number
        config.INDEX_OF_All_FRAME  = raw.abs_frame_number
        config.INDEX_OF_VIDEO      = raw.video_index
        config.INDEX_OF_GPS        = raw.gps_index

        # Отправляем позицию на карту (раз в секунду)
        current_second = int(raw.abs_frame_number / config.VIDEO_FPS)  # BLOCK J.2: реальный FPS
        if current_second != last_position_update:
            last_position_update = current_second
            try:
                from server.map_server import emit_position
                emit_position(current_second)
            except Exception:
                pass

        # Получаем скорость для умного skipping
        speed = self._gpx.get_speed(raw.gps_index)
        
        # Пропускаем если машина стоит (BLOCK CPU-7: через SmartFrameSkipper)
        if self._skipper.is_stationary(speed):
            # BLOCK CPU-2: Троттлинг превью
            if self._should_emit_preview():
                self._emit_frame(raw.image)
            return turn, last_position_update

        # ══════════════════════════════════════════════════════════
        # УМНЫЙ FRAME SKIPPING (BLOCK CPU-7: через SmartFrameSkipper)
        # ══════════════════════════════════════════════════════════
        
        # Обновляем текущий интервал пропуска на основе скорости и активности
        self._skipper.calc_skip_interval(speed)
        # BLOCK FIX-2.1: прокидываем эффективный skip в config для SignHandler
        config.CURRENT_EFFECTIVE_SKIP = self._skipper.current_skip
        
        # Проверяем, нужно ли обрабатывать этот кадр
        if not self._skipper.should_process():
            # Пропускаем детекцию, но показываем кадр в UI
            # BLOCK CPU-2: Троттлинг превью
            if self._should_emit_preview():
                self._emit_frame(raw.image)
            return turn, last_position_update
        
        # ══════════════════════════════════════════════════════════

        # ══════════════════════════════════════════════════════════
        # BLOCK CPU-3: CNN-skip cache через detect_with_tracking
        # ══════════════════════════════════════════════════════════
        # Получаем карту активных трекаемых знаков для пропуска повторного CNN
        tracked_map = self._sign_handler.get_tracked_signs_map()
        
        # Детекция (с пропуском OCR в pipeline режиме + CNN-skip для стабильных знаков)
        with profiler.measure("detector_find_rectangles"):
            detections_raw = self._detector.detect_with_tracking(
                raw.image, 
                tracked_map, 
                skip_ocr=self._use_pipeline
            )
            # Конвертируем в старый формат
            detections = [
                [list(d.box), d.color, d.cnn_class, d.yolo_class, d.cnn_class, d.text, d.is_side]
                for d in detections_raw
            ]

        # Обновляем историю активности для адаптивного skip (BLOCK CPU-7: через SmartFrameSkipper)
        self._skipper.update_activity(len(detections))

        # Конвертируем в DetectedSign
        with profiler.measure("build_detected_signs"):
            detected = self._build_detected(detections, raw)
        
        # Трекинг ПЕРЕД OCR (BLOCK CPU-4: нужен TrackedSign для троттлинга)
        with profiler.measure("sign_handler_tracking"):
            turn = self._sign_handler.check_the_data_to_add(detected or None, turn)
        
        # ══════════════════════════════════════════════════════════
        # BLOCK CPU-4: OCR Throttling на уровне TrackedSign
        # ══════════════════════════════════════════════════════════
        # В pipeline режиме отправляем знаки требующие OCR в OCR Worker
        # ПОСЛЕ трекинга, чтобы использовать TrackedSign.should_run_ocr()
        if self._use_pipeline and self._sign_handler.signs:
            for tracked_sign in self._sign_handler.signs:
                # Проверяем нужен ли OCR для этого типа знака
                if self._detector.needs_ocr(tracked_sign.best_cnn, tracked_sign.best_yolo):
                    # Проверяем троттлинг на уровне TrackedSign
                    if tracked_sign.should_run_ocr(raw.abs_frame_number):
                        # Отправляем в OCR Worker
                        self._submit_ocr_task(tracked_sign, raw.image)
                        
                        # Отмечаем, что OCR запрошен
                        tracked_sign.mark_ocr_requested(raw.abs_frame_number)
                        self._ocr_calls_total += 1  # BLOCK CPU-4: счётчик
                    else:
                        self._ocr_calls_skipped += 1  # BLOCK CPU-4: пропущено

        # Финальные знаки → в очередь результатов
        # BLOCK SIGN-LOSS-1 FIX: НЕ теряем знаки при переполнении очереди
        if self._sign_handler.result_signs:
            logger.debug(f"Добавляю {len(self._sign_handler.result_signs)} знаков в очередь")
        
        remaining = []
        for sign in self._sign_handler.result_signs:
            try:
                self._result_q.put(sign, timeout=0.1)
            except queue.Full:
                # BLOCK SIGN-LOSS-1 FIX: НЕ теряем знак — откладываем его и пробуем
                # отправить повторно на следующей итерации цикла, когда в очереди
                # освободится место (её вычитывает ProcessingController.get_result_signs()
                # только в конце обработки, поэтому переполнение — явление временное).
                logger.warning(
                    f"result_queue переполнена (размер={self._result_q.qsize()})! "
                    f"Знак {sign.best_cnn} отложен и будет отправлен повторно."
                )
                remaining.append(sign)
        
        # ВАЖНО: очищаем список знаков, которые ДЕЙСТВИТЕЛЬНО ушли в очередь.
        # Всё, что не поместилось, остаётся в self._sign_handler.result_signs и
        # НИКОГДА не удаляется молча.
        self._sign_handler.result_signs = remaining
        if remaining:
            logger.warning(f"[SignLoss-Guard] {len(remaining)} знаков ожидают повторной отправки в очередь")
        
        # Автосохранение checkpoint (если контроллер передан)
        if self._controller and hasattr(self._controller, 'save_checkpoint'):
            self._controller.save_checkpoint()

        # UI
        # BLOCK CPU-2: Троттлинг превью — рисуем и эмитим только если прошёл интервал
        if self._should_emit_preview():
            with profiler.measure("draw_boxes_and_emit"):
                annotated = self._draw_boxes(raw.image, detections)
                self._emit_frame(annotated)
        
        self._update_stats(len(detections))

        for det in detected:
            self.sign_detected.emit(
                det.number_sign,
                raw.video_name,
                0.0,
            )
        
        return turn, last_position_update

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
        lat, lon = 0.0, 0.0
        
        try:
            # BLOCK J.2: Используем интерполированные GPS координаты
            gps_point = self._gpx.get_interpolated(raw.abs_frame_number, config.VIDEO_FPS)
            
            if gps_point:
                lat, lon = gps_point.latitude, gps_point.longitude
                # Конвертируем из WGS84 (lat/lon) в EPSG:32635 (x/y) для внутреннего использования
                if lat != 0.0 and lon != 0.0:
                    lat, lon = self._converter.coordinateConverter(
                        lat, lon, "epsg:4326", "epsg:32635"
                    )
        except Exception as e:
            # Fallback на старый метод если интерполяция не удалась
            try:
                lat, lon = self._gpx.get_current_coordinate(raw.gps_index)
                if lat != 0.0 and lon != 0.0:
                    lat, lon = self._converter.coordinateConverter(
                        lat, lon, "epsg:4326", "epsg:32635"
                    )
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
        """
        Сериализует BGR-кадр и отправляет его как данные (без QPixmap!).
        
        ВАЖНО: QPixmap собирается только в главном потоке ProcessingController,
        а не здесь в QThread. Это соблюдает требование Qt: GUI-объекты (QPixmap)
        можно создавать только в главном GUI-потоке.
        
        См. processing/preview_utils.py для деталей архитектуры.
        """
        from processing.preview_utils import build_frame_dict
        
        self.frame_ready.emit(build_frame_dict(image))
    
    def _should_emit_preview(self) -> bool:
        """
        Проверяет, нужно ли обновлять UI-превью (троттлинг).
        
        BLOCK CPU-2: Ограничиваем частоту обновления превью до preview_fps_limit.
        Экономит CPU на cv2.cvtColor + QPixmap.scaled для невидимых пользователю кадров.
        
        Returns:
            bool: True если можно эмитить, False если слишком рано
        """
        if self._preview_min_interval <= 0:
            return True  # Троттлинг отключён
        
        now = time.monotonic()
        if now - self._last_emit_time < self._preview_min_interval:
            return False  # Слишком рано
        
        self._last_emit_time = now
        return True

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
            
            # Логируем статистику умного skipping (BLOCK CPU-7: через SmartFrameSkipper)
            if self._frames_processed > 0:
                skip_ratio = (self._skipper.frames_skipped / 
                             (self._frames_processed + self._skipper.frames_skipped)) * 100
                
                # Получаем статистику CNN кэша
                cache_info = ""
                if self._detector and hasattr(self._detector, '_cnn_cache'):
                    try:
                        stats = self._detector._cnn_cache.stats()
                        cache_info = (f", Cache: {stats['hit_rate']:.1f}% "
                                    f"({stats['hits']}/{stats['hits']+stats['misses']}) "
                                    f"size={stats['size']}")
                    except Exception as e:
                        cache_info = f", Cache Error: {e}"
                
                # BLOCK CPU-3: Статистика TrackedSign CNN-skip
                tracked_skip_info = ""
                if self._detector and hasattr(self._detector, '_tracked_skip_count'):
                    skip_count = self._detector._tracked_skip_count
                    total_count = self._detector._counter
                    if total_count > 0:
                        skip_pct = (skip_count / total_count) * 100
                        tracked_skip_info = f", TrackedSkip: {skip_count}/{total_count} ({skip_pct:.1f}%)"
                
                # Добавляем статистику OCR Worker если используется
                ocr_info = ""
                if self._use_pipeline and self._ocr_worker:
                    pending = len(self._pending_ocr)
                    # BLOCK CPU-4: Добавляем статистику троттлинга OCR
                    total_ocr_ops = self._ocr_calls_total + self._ocr_calls_skipped
                    if total_ocr_ops > 0:
                        skip_pct = (self._ocr_calls_skipped / total_ocr_ops) * 100
                        ocr_info = (f", OCR: {self._ocr_calls_total} calls, "
                                   f"{self._ocr_calls_skipped} skipped ({skip_pct:.1f}%), "
                                   f"pending: {pending}")
                    else:
                        ocr_info = f", OCR pending: {pending}"
                
                # БАГ C: Статистика OCR кэша
                ocr_cache_info = ""
                if self._detector and hasattr(self._detector, 'get_ocr_cache_stats'):
                    try:
                        ocr_stats = self._detector.get_ocr_cache_stats()
                        ocr_cache_info = (f", OCR Cache: {ocr_stats['hit_rate']:.1f}% "
                                        f"({ocr_stats['hits']}/{ocr_stats['hits']+ocr_stats['misses']}) "
                                        f"size={ocr_stats['size']}")
                    except Exception as e:
                        ocr_cache_info = f", OCR Cache Error: {e}"
                
                logger.info(f"[SmartSkip] Обработано: {self._frames_processed}, "
                           f"Пропущено: {self._skipper.frames_skipped} ({skip_ratio:.1f}%), "
                           f"Текущий интервал: 1/{self._skipper.current_skip}, "
                           f"FPS: {fps:.1f}{cache_info}{tracked_skip_info}{ocr_info}{ocr_cache_info}")
                
                # Печатаем отчет профилирования каждые N кадров
                if (config.ENABLE_PROFILING and 
                    self._frames_processed >= config.PROFILING_MIN_FRAMES and
                    self._frames_processed % config.PROFILING_REPORT_INTERVAL == 0):
                    profiler.log_report()
            
            self.stats_updated.emit(
                self._frames_processed,
                self._signs_found,
                fps,
            )
    
    # ── Pipeline OCR Support ──────────────────────────────────────
    
    def _submit_ocr_task(self, tracked_sign: "TrackedSign", frame: np.ndarray) -> None:
        """
        Отправляет знак на OCR обработку.
        ВАЖНО: храним ссылку на TrackedSign (а не на одноразовый DetectedSign),
        чтобы результат OCR можно было дописать обратно в tracked_sign.text_results.
        
        Args:
            tracked_sign: TrackedSign который нужно обработать через OCR
            frame: Полный кадр для извлечения crop
        """
        if not self._ocr_worker:
            return
        if not tracked_sign.pixel_x or not tracked_sign.pixel_y:
            return
        
        # Генерируем уникальный ID
        sign_id = self._ocr_sign_counter
        self._ocr_sign_counter += 1
        
        # Извлекаем координаты последнего наблюдения
        x = tracked_sign.pixel_x[-1]
        y = tracked_sign.pixel_y[-1]
        w = tracked_sign.widths[-1]
        h = tracked_sign.heights[-1]
        
        # Извлекаем crop из кадра
        crop = frame[y:y+h, x:x+w]
        
        if crop.size == 0:
            return
        
        # Сохраняем ссылку на TrackedSign (не DetectedSign!)
        self._pending_ocr[sign_id] = tracked_sign
        
        if self._using_ocr_pool:
            # ProcessPool: используем submit с callback
            self._ocr_worker.submit(
                sign_id=sign_id,
                frame_number=tracked_sign.frame_numbers[-1],
                crop=crop.copy(),
                cnn_class=tracked_sign.best_cnn,
                yolo_class=tracked_sign.best_yolo,
                callback=self._on_ocr_result_pool
            )
        else:
            # QThread: используем submit_task
            from processing.ocr_worker import OCRTask
            task = OCRTask(
                sign_id=sign_id,
                frame_number=tracked_sign.frame_numbers[-1],
                crop=crop.copy(),
                cnn_class=tracked_sign.best_cnn,
                yolo_class=tracked_sign.best_yolo
            )
            submitted = self._ocr_worker.submit_task(task)
            
            if not submitted:
                logger.warning(f"[Pipeline] Не удалось отправить OCR задачу для sign_id={sign_id}")
                self._pending_ocr.pop(sign_id, None)

    
    def _on_ocr_result(self, result) -> None:
        """
        Обработчик результата OCR из OCRWorkerThread (QThread).
        Дописывает текст в TrackedSign.text_results.
        
        Args:
            result: OCRResult
        """
        tracked_sign = self._pending_ocr.pop(result.sign_id, None)
        if tracked_sign is None:
            logger.warning(f"[Pipeline] Получен OCR результат для неизвестного sign_id={result.sign_id}")
            return
        
        # Дописываем результат в text_results
        if result.text:
            tracked_sign.text_results.append(result.text)
        
        logger.debug(f"[Pipeline] OCR завершён для sign_id={result.sign_id}, "
                    f"text='{result.text}'")
    
    def _on_ocr_result_pool(self, result) -> None:
        """
        Callback для результата OCR из OCRPool (ProcessPool).
        Вызывается в основном потоке через Future.add_done_callback.
        Дописывает текст в TrackedSign.text_results.
        
        Args:
            result: OCRResult from ocr_pool
        """
        from processing.ocr_pool import OCRResult
        
        tracked_sign = self._pending_ocr.pop(result.sign_id, None)
        if tracked_sign is None:
            logger.warning(f"[OCRPool] Получен OCR результат для неизвестного sign_id={result.sign_id}")
            return
        
        if result.error:
            logger.warning(f"[OCRPool] Ошибка для sign_id={result.sign_id}: {result.error}")
            return
        
        # Дописываем результат в text_results
        if result.text:
            tracked_sign.text_results.append(result.text)
        
        logger.debug(f"[OCRPool] OCR завершён для sign_id={result.sign_id}, "
                    f"text='{result.text}'")


    # Qt импортирован на уровне модуля — см. начало файла