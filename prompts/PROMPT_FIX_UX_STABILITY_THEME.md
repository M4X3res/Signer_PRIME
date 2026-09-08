# PROMPT: Settings UX, самозавершение обработки, видеоплеер карты, светлая тема

**Для кого:** ИИ-агент с доступом к репозиторию RoadScanner (Signer PRIME) на запись.
**Формат:** аналогичен другим `PROMPT_*.md` в этом репозитории (см. `docs/`). Каждая задача
самодостаточна: диагноз → точные изменения → критерии приёмки. Выполняй задачи по порядку,
после каждой — прогоняй чек-лист из раздела 6.

---

## 0. Контекст и общие ограничения

Проект — PyQt6-приложение для детекции дорожных знаков на видео с GPS-трекингом. В коде уже
есть несколько хрупких, документированных обходов крашей — **их нельзя случайно сломать**:

1. **QPixmap создаётся ТОЛЬКО в главном GUI-потоке.** Вся архитектура превью построена вокруг
   `processing/preview_utils.py` (`build_frame_dict()` в воркер-потоке →
   `build_pixmap_from_frame_dict()` в главном потоке через
   `ProcessingController._on_worker_frame_ready()`). Не создавай `QPixmap`/`QImage` внутри
   `DetectorThread`, `ResultAggregatorThread` или worker-процессов.
2. **OpenMP/MKL workaround.** `main.py` выставляет `OMP_NUM_THREADS=1`, `torch.set_num_threads(1)`
   и т.д. для защиты от краша `0xC0000409` (см. `docs/CRASH_FIX_0xC0000409.md`,
   `docs/CRASH_FIX_v1.3.3.md`). Не убирай эти строки.
3. **Не используй `print()`** — только `logging` (см. `docs/LOGGING_MIGRATION_GUIDE.md`).
4. Сохраняй существующие сигнатуры сигналов Qt (`pyqtSignal(...)`), которые слушает
   `ProcessingController`/`MainWindow` — их нельзя менять без согласованного обновления
   подписчиков.
5. После каждой задачи — запусти существующие структурные тесты в `tests/` (`pytest tests/`
   и standalone-скрипты `tests/check_*.py`, `tests/run_geometry_tests.py`), чтобы убедиться,
   что ничего не сломано.

---

## ЗАДАЧА 1 — Показать выбор режима обработки (CPU) в Простом режиме настроек

### Диагноз
Файл: `ui/widgets/settings_page.py`.

Виджет `self._processing_mode_combo` («Один поток» / «Pipeline» / «Process Pool») создаётся
внутри группы `mt_group = SettingsGroup("Многопоточность")`, а сама `mt_group` целиком
добавлена в список `self._advanced_only_widgets`:

```python
self._advanced_only_widgets = [
    ui_group, proc_group, gps_group, mt_group, lane_group,
    log_group, turn_group, diag_group_advanced, export_group,
]
```

Поэтому в «Простом режиме» (`_set_ui_mode("simple")`, значение по умолчанию) весь блок скрыт
и пользователь не может переключить режим обработки, не заходя в «Расширенный режим».

### Изменения

В `SettingsPage.__init__`, **сразу после блока `ui_group`** (перед созданием `proc_group`),
добавь новую, ВСЕГДА видимую группу:

```python
# ── Group: Режим обработки (ВСЕГДА ВИДНА, даже в Простом режиме) ────
mode_group = SettingsGroup("Режим обработки")

self._processing_mode_combo = QComboBox()
self._processing_mode_combo.setFixedWidth(180)
self._processing_mode_combo.addItems(["Один поток", "Pipeline", "Process Pool"])
mode_idx = {"single_thread": 0, "pipeline": 1, "process_pool": 2}.get(
    self._settings.processing_mode, 0
)
self._processing_mode_combo.setCurrentIndex(mode_idx)
self._processing_mode_combo.setToolTip(
    "Режим обработки видео:\n\n"
    "• Один поток (рекомендуется для CPU) — самый быстрый вариант без GPU,\n"
    "  минимум накладных расходов на синхронизацию.\n\n"
    "• Pipeline — распознавание текста (OCR) выполняется в отдельном потоке.\n"
    "  Полезно, если в видео много знаков с текстом (ограничения скорости,\n"
    "  названия населённых пунктов).\n\n"
    "• Process Pool — детекция в нескольких процессах одновременно.\n"
    "  Даёт выигрыш в основном с видеокартой (CUDA). На процессоре обычно\n"
    "  МЕДЛЕННЕЕ «Одного потока» из-за копирования моделей и данных между\n"
    "  процессами (подробности: WHY_SINGLE_THREAD_FASTER.md).\n\n"
    "⚡ Если у вас нет NVIDIA GPU — оставляйте «Один поток»."
)
mode_group.add_row(
    "Режим обработки видео",
    "«Один поток» быстрее всего на CPU. Pipeline/Process Pool — если есть GPU",
    self._processing_mode_combo,
)

content_layout.addWidget(mode_group)
```

Затем в существующем блоке `mt_group` **удали** дублирующее создание комбобокса и его строку
(оставь только настройки воркеров и OCR-пула, которые остаются продвинутыми):

Было:
```python
mt_group = SettingsGroup("Многопоточность")

self._processing_mode_combo = QComboBox()
self._processing_mode_combo.setFixedWidth(160)
self._processing_mode_combo.addItems(["Один поток", "Pipeline", "Process Pool"])
mode_idx = {"single_thread": 0, "pipeline": 1, "process_pool": 2}.get(
    self._settings.processing_mode, 0
)
self._processing_mode_combo.setCurrentIndex(mode_idx)
self._processing_mode_combo.setToolTip( ... )
mt_group.add_row(
    "Режим обработки",
    "ℹ️ Process Pool: предпросмотр работает, результаты сохраняются",
    self._processing_mode_combo,
)

self._workers_spin = QSpinBox()
...
```

Стало:
```python
mt_group = SettingsGroup("Многопоточность (дополнительные параметры)")

self._workers_spin = QSpinBox()
...
```

`self._workers_spin.setEnabled(...)` и подписка
`self._processing_mode_combo.currentIndexChanged.connect(lambda idx: self._workers_spin.setEnabled(idx == 2))`
оставь без изменений — они по-прежнему корректно работают, т.к. `self._processing_mode_combo`
это тот же атрибут `self`, просто созданный раньше, в другом месте метода.

`mt_group` **оставь** в списке `self._advanced_only_widgets` (детальные параметры воркеров/OCR —
это по-прежнему продвинутая настройка), а `mode_group` **не добавляй** в этот список — она
должна быть видна всегда.

### Критерии приёмки
- В «Простом режиме» на странице настроек видна группа «Режим обработки» с выпадающим списком
  из трёх пунктов, значение сохраняется через `_collect_settings()`/`_save()` как и раньше
  (там уже читается `self._processing_mode_combo.currentIndex()` — код трогать не нужно).
- В «Расширенном режиме» появляется дополнительно группа «Многопоточность (дополнительные
  параметры)» с воркерами/OCR-пулом, без дублирования селектора режима.
- `_reset()` по-прежнему корректно сбрасывает `self._processing_mode_combo` (код `_reset()`
  трогать не нужно — он уже обращается к этому атрибуту напрямую).

---

## ЗАДАЧА 2 — Баг «обработка завершается сама»

### Диагноз (наиболее вероятная причина, проверено по коду)

`processing/detector_thread.py`, метод `DetectorThread._process_loop()`: весь код обработки
ОДНОГО кадра (детекция, трекинг, OCR-очередь, запись в `result_queue`, обновление UI) идёт
одним сплошным блоком внутри `while not self._stop:` **без `try/except`**. `run()` оборачивает
вызов `_process_loop()` в:

```python
try:
    self._process_loop()
except Exception as e:
    self.error.emit(str(e))
finally:
    ...
    self.finished_work.emit()
```

То есть **любое** необработанное исключение на **одном** кадре (например: деление на ноль в
`SignHandler`/`Turn`, некорректные координаты в `Converter`/pyproj, `IndexError` в геометрии
поворотов и т.д.) убивает весь `while`-цикл целиком. Обработка при этом не «падает» с ошибкой,
которую пользователь точно заметит — `finally` вызывает `finalize_remaining()` и
`finished_work.emit()`, `ProcessingController._on_detector_finished()` эмитит `finished`,
`MainWindow._on_finish()` показывает «Обработка завершена» зелёным цветом. Пользователь видит
штатное завершение, хотя реально обработана только часть видео. Единственный след — строка
`self.error.emit(str(e))`, которая просто добавляется в лог-консоль (без traceback, легко
потерять среди сотен info-строк).

Второй, менее вероятный, но тоже реальный кандидат: `processing/video_reader.py`,
`VideoReaderThread._read_all_videos()` — цикл чтения кадра прерывается, если
`cap.get(cv2.CAP_PROP_FRAME_COUNT)` (метаданные `total_frames_in_video`) занижены (частая
ситуация для GoPro/MSMF-бэкенда, см. `docs/SOLUTION_GOPRO_MSMF.md`), либо если `cap.grab()`
разово не удался (могут быть кратковременные сбои чтения multi-stream MP4). Оба случая сейчас
трактуются как «конец файла» без какой-либо попытки повтора.

Третий баг (не про самозавершение, а про **зависание** — обратная сторона той же проблемы):
`processing/detector_process_pool.py`, `ResultAggregatorThread.run()` — `finished_work.emit()`
вызывается только в «счастливом» пути (внутри `try`, не в `finally`). Если исключение долетает
до внешнего `except Exception as e:`, `finished_work` никогда не эмитится, и UI бесконечно
висит в состоянии «обработка идёт», хотя воркер-поток агрегатора уже мёртв.

### Изменения

#### 2.1 `processing/detector_thread.py`

Раздели `_process_loop()` на диспетчер и обработчик одного кадра, оберни вызов обработчика
кадра в `try/except`, чтобы ошибка на одном кадре не убивала весь прогон:

```python
def _process_loop(self) -> None:
    from core.turn import Turn
    turn = Turn()

    self._frame_errors = 0  # BLOCK STAB-1: счётчик кадров, пропущенных из-за ошибок
    last_position_update = 0

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
    current_second = int(raw.abs_frame_number / config.VIDEO_FPS)
    if current_second != last_position_update:
        last_position_update = current_second
        try:
            from server.map_server import emit_position
            emit_position(current_second)
        except Exception:
            pass

    # Получаем скорость для умного skipping
    speed = self._gpx.get_speed(raw.gps_index)

    if self._skipper.is_stationary(speed):
        if self._should_emit_preview():
            self._emit_frame(raw.image)
        return turn, last_position_update

    self._skipper.calc_skip_interval(speed)
    config.CURRENT_EFFECTIVE_SKIP = self._skipper.current_skip

    if not self._skipper.should_process():
        if self._should_emit_preview():
            self._emit_frame(raw.image)
        return turn, last_position_update

    tracked_map = self._sign_handler.get_tracked_signs_map()

    with profiler.measure("detector_find_rectangles"):
        detections_raw = self._detector.detect_with_tracking(
            raw.image, tracked_map, skip_ocr=self._use_pipeline
        )
        detections = [
            [list(d.box), d.color, d.cnn_class, d.yolo_class, d.cnn_class, d.text, d.is_side]
            for d in detections_raw
        ]

    self._skipper.update_activity(len(detections))

    with profiler.measure("build_detected_signs"):
        detected = self._build_detected(detections, raw)

    with profiler.measure("sign_handler_tracking"):
        turn = self._sign_handler.check_the_data_to_add(detected or None, turn)

    if self._use_pipeline and self._sign_handler.signs:
        for tracked_sign in self._sign_handler.signs:
            if self._detector.needs_ocr(tracked_sign.best_cnn, tracked_sign.best_yolo):
                if tracked_sign.should_run_ocr(raw.abs_frame_number):
                    self._submit_ocr_task(tracked_sign, raw.image)
                    tracked_sign.mark_ocr_requested(raw.abs_frame_number)
                    self._ocr_calls_total += 1
                else:
                    self._ocr_calls_skipped += 1

    if self._sign_handler.result_signs:
        logger.debug(f"Добавляю {len(self._sign_handler.result_signs)} знаков в очередь")

    remaining = []
    for sign in self._sign_handler.result_signs:
        try:
            self._result_q.put(sign, timeout=0.1)
        except queue.Full:
            logger.warning(
                f"result_queue переполнена (размер={self._result_q.qsize()})! "
                f"Знак {sign.best_cnn} отложен и будет отправлен повторно."
            )
            remaining.append(sign)

    self._sign_handler.result_signs = remaining
    if remaining:
        logger.warning(f"[SignLoss-Guard] {len(remaining)} знаков ожидают повторной отправки")

    if self._controller and hasattr(self._controller, 'save_checkpoint'):
        self._controller.save_checkpoint()

    if self._should_emit_preview():
        with profiler.measure("draw_boxes_and_emit"):
            annotated = self._draw_boxes(raw.image, detections)
            self._emit_frame(annotated)

    self._update_stats(len(detections))

    for det in detected:
        self.sign_detected.emit(det.number_sign, raw.video_name, 0.0)

    return turn, last_position_update
```

> ВАЖНО: я объединил ветку `if self._use_pipeline: ... else: ...` вокруг
> `detect_with_tracking(...)` в одну строку `skip_ocr=self._use_pipeline`, т.к. в оригинале обе
> ветки были идентичны и отличались только литералом `skip_ocr`. Поведение не меняется —
> проверь, что это действительно так в актуальной версии файла перед заменой (сравни с
> исходником), и если код успел разойтись сильнее — сохрани обе ветки как есть, просто добавь
> обёртку try/except вокруг вызова `_process_single_frame`.

Также обнови `finally` в `run()` — заверни вызов `finalize_remaining()` в свой `try/except`,
чтобы ошибка при финализации не мешала выполнить остаток `finally` (остановку OCR-воркера и
обязательный `finished_work.emit()`), и добавь `logger.exception(...)` во внешний catch:

```python
try:
    self._process_loop()
except Exception as e:
    logger.exception(f"[DetectorThread] Необработанная ошибка в _process_loop: {e}")
    self.error.emit(str(e))
finally:
    if self._sign_handler:
        logger.info("[DetectorThread] Финализация оставшихся активных знаков...")
        try:
            self._sign_handler.finalize_remaining()
        except Exception as e:
            logger.exception(f"[DetectorThread] Ошибка финализации активных знаков: {e}")

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
                    f"отправке: {lost}"
                )
            self._sign_handler.result_signs.clear()

    if self._ocr_worker:
        logger.info("[DetectorThread] Останавливаем OCR Worker...")
        if self._using_ocr_pool:
            self._ocr_worker.stop(wait=True)
        else:
            self._ocr_worker.stop()
            if hasattr(self._ocr_worker, 'wait'):
                self._ocr_worker.wait(3000)
        logger.info("[DetectorThread] OCR Worker остановлен")

    self.finished_work.emit()
```

#### 2.2 `processing/detector_process_pool.py` — `ResultAggregatorThread.run()`

Замени метод целиком:

```python
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

            try:
                result = future.result(timeout=10.0)
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
```

#### 2.3 `processing/video_reader.py` — устойчивость к «преждевременному концу видео»

Добавь константы в класс `VideoReaderThread`:

```python
class VideoReaderThread(QThread):
    ...
    GRAB_RETRY_ATTEMPTS = 3        # BLOCK STAB-3
    GRAB_RETRY_DELAY_S  = 0.05
    FRAME_COUNT_SAFETY_MARGIN = 1.02  # запас на неточность cv2 CAP_PROP_FRAME_COUNT
```

В `_read_all_videos()` найди блок:

```python
                # Выходим если прошли весь файл (только если знаем длину)
                if use_frame_limit and local_frame >= total_frames_in_video:
                    video_logger.info(f"[VIDEO {video_idx}] END (limit reached): frames_read={frames_read}, local_frame={local_frame}/{total_frames_in_video}\n")
                    logger.info(f"[VIDEO {video_idx}] Завершено по лимиту: прочитано {frames_read} кадров, local_frame={local_frame}")
                    break
```

Замени условие на:

```python
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
```

Дальше найди блок с `cap.grab()`:

```python
                with profiler.measure("video_grab_frame"):
                    grabbed = cap.grab()
                
                # Логируем первые 50 кадров для диагностики
                if local_frame < 50:
                    video_logger.debug(f"  Frame {local_frame}: grabbed={grabbed}")
                
                if not grabbed:
                    current_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
                    video_logger.info(f"[VIDEO {video_idx}] END (grab failed): frames_read={frames_read}, local_frame={local_frame}/{total_frames_in_video}, grabbed={grabbed}")
                    video_logger.info(f"  CAP_PROP_POS_FRAMES: {current_pos}")
                    video_logger.info(f"  CAP_PROP_FRAME_COUNT: {cap.get(cv2.CAP_PROP_FRAME_COUNT)}")
                    video_logger.info(f"  isOpened: {cap.isOpened()}\n")
                    logger.info(f"[VIDEO {video_idx}] Завершено: не удалось захватить кадр {local_frame}, прочитано {frames_read} кадров")
                    break
```

Замени на:

```python
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
                    current_pos = cap.get(cv2.CAP_PROP_POS_FRAMES)
                    video_logger.info(f"[VIDEO {video_idx}] END (grab failed after {self.GRAB_RETRY_ATTEMPTS} retries): frames_read={frames_read}, local_frame={local_frame}/{total_frames_in_video}")
                    video_logger.info(f"  CAP_PROP_POS_FRAMES: {current_pos}")
                    video_logger.info(f"  CAP_PROP_FRAME_COUNT: {cap.get(cv2.CAP_PROP_FRAME_COUNT)}")
                    video_logger.info(f"  isOpened: {cap.isOpened()}\n")
                    logger.info(f"[VIDEO {video_idx}] Завершено: не удалось захватить кадр {local_frame} после повторов, прочитано {frames_read} кадров")
                    break
```

### Критерии приёмки
- Синтетический тест: временно вставить в `SignHandler.check_the_data_to_add()` намеренный
  `raise ValueError("test")` на, скажем, 20-м вызове — обработка ДОЛЖНА продолжиться (в логе —
  строка `[DetectorThread] Ошибка обработки кадра ...`), финальный GeoJSON должен содержать
  знаки, найденные и до, и после «сбойного» кадра, а не обрываться на нём.
- Обработка полного тестового видео (после отката тестового `raise`) по-прежнему находит то же
  число знаков, что и до изменений (регрессионный прогон, сравнить с бейзлайном).
- В `roadscan.log` при обычном прогоне без ошибок НЕ появляется новых warning/error-строк.
- Process Pool режим: если искусственно уронить один worker (например, временно бросить
  исключение внутри `_worker_process_frame`), UI всё равно получает сигнал `finished` и не
  виснет.

---

## ЗАДАЧА 3 — Видеоплеер на карте (`templates/map.html`)

### Диагноз

1. **Мёртвый JS-код ломает Live-трекинг позиции.** Функции `vcToggle()`, `vcStep()`, `vcSeek()`,
   `vcSetTime()` обращаются к DOM-элементам `#vc-play`, `#video-slider`, `#video-time` —
   в текущей разметке этих элементов **нет** (остался только нативный `<video id="map-video"
   controls>` и `#video-time-display`). `vcSetTime()` вызывается из `jumpToFrame()` и из
   обработчика `socket.on("position", seconds => {...})`. `document.getElementById(...)`
   возвращает `null`, обращение к `.textContent`/`.value` на `null` кидает `TypeError`, который
   обрывает выполнение оставшейся части функции. В обработчике `position` это означает, что
   **`updatePositionMarker(seconds)` вообще перестаёт вызываться** — маркер текущего положения
   на карте не двигается во время Live-обработки. В `jumpToFrame()` это гасит toast-уведомление
   об успехе (перехватывается общим `.catch()`, показывается «Ошибка перехода к кадру» вместо
   реального результата).
2. **Дублирующаяся функция форматирования времени.** Есть `fmtTime()` (используется в мёртвом
   коде и в `jumpToFrame`) и почти идентичная `formatTime()` (используется в `loadVideoForSign`
   и обработчике `timeupdate`) — держать две копии одной и той же логики опасно (легко забыть
   поправить одну при правке другой).
3. **API-базовый URL не совпадает с origin страницы.** `const API = \`http://localhost:${PORT}/api\`;`
   — захардкожен `localhost`, при этом сама страница карты открывается по
   `http://127.0.0.1:{MAP_PORT}/` (см. `ui/widgets/map_page.py::_load_map()`). Для `fetch()`
   разница обычно не критична (плюс приложение передаёт Chromium флаг
   `--disable-web-security`), но `<video>`-элемент со стриминговым Range-контентом более
   чувствителен к cross-origin поведению — лучше сразу убрать любую двусмысленность.
4. **Возможный кодек.** В коде уже есть диагностическая функция `testVideoCodec()` и проверка
   `video.canPlayType(...)` перед загрузкой — это сигнал, что с кодеками уже сталкивались.
   GoPro-камеры (основной сценарий использования проекта, см. `docs/SOLUTION_GOPRO_MSMF.md`)
   часто пишут видео в HEVC/H.265 при высоких разрешениях — встроенный в QtWebEngine Chromium
   обычно **не поддерживает HEVC** без проприетарного лицензирования. Если исходное видео в
   HEVC, `canPlayType` вернёт пустую строку и видео не будет воспроизводиться — при этом текущее
   сообщение об ошибке не объясняет пользователю, что делать.

### Изменения

**3.1. Origin.** Найди:

```javascript
const PORT = location.port || 3000;
const API  = `http://localhost:${PORT}/api`;
```

Замени на:

```javascript
const PORT = location.port || 3000;
// BLOCK STAB-4: используем тот же hostname, что и у самой страницы карты
// (см. MapPage._load_map(): страница грузится с 127.0.0.1), а не
// захардкоженный localhost — это устраняет любую двусмысленность
// same-origin для <video>-стриминга и fetch()-запросов.
const API  = `${location.protocol}//${location.hostname}:${PORT}/api`;
```

**3.2. Убрать дублирование `fmtTime`/`formatTime`.** Оставь только `formatTime()` (та, что уже
используется в рабочем видеоплеере), удали `fmtTime()`, и замени оба места её использования:

- В `jumpToFrame()`: `toast(\`Прыжок к ${fmtTime(seconds)}\`);` → `toast(\`Прыжок к ${formatTime(seconds)}\`);`
  и `document.getElementById("stat-pos").textContent = fmtTime(seconds);` →
  `document.getElementById("stat-pos").textContent = formatTime(seconds);`
- В обработчике `socket.on("position", ...)`: аналогично заменить `fmtTime` на `formatTime`.

**3.3. Переписать блок видео-контролов.** Найди весь блок:

```javascript
// ── Video controls (локальный таймер — реальный плеер в PyQt) ──────
function vcToggle() { ... }
function vcStep(delta) { ... }
function vcSeek(val) { ... }
function vcSetTime(s) { ... }
function fmtTime(s) { ... }
```

Замени на:

```javascript
// ── Video controls ──────────────────────────────────────────────────
// BLOCK STAB-4: ИСПРАВЛЕНИЕ КРИТИЧЕСКОГО БАГА.
// Раньше эти функции обращались к #vc-play / #video-slider / #video-time —
// элементов с такими id больше нет в разметке (заменены на нативный
// <video controls>). getElementById(...) возвращал null, а обращение к
// .textContent/.value на null выбрасывало TypeError. vcSetTime()
// вызывается из jumpToFrame() и из socket.on("position", ...) — это
// исключение обрывало остаток функции, из-за чего в Live-режиме маркер
// позиции на карте (updatePositionMarker) вообще переставал обновляться.
// vcToggle/vcStep/vcSeek были рассчитаны на кастомный слайдер, которого
// больше нет — они нигде не вызываются из текущей разметки, поэтому
// удалены как мёртвый код.
function vcSetTime(s) {
  vcSeconds = s;

  const timeDisplay = document.getElementById("video-time-display");
  if (timeDisplay) {
    const video = document.getElementById("map-video");
    const duration = video && !isNaN(video.duration) ? video.duration : 0;
    timeDisplay.textContent = `${formatTime(s)} / ${formatTime(duration)}`;
  }

  // Если сейчас Live-режим и видео уже загружено — подтягиваем
  // currentTime реального плеера к позиции обработки (но не мешаем,
  // если пользователь сам сейчас перематывает).
  const video = document.getElementById("map-video");
  if (video && liveMode && !video.seeking && !isNaN(video.duration)) {
    if (Math.abs(video.currentTime - s) > 2) {
      try { video.currentTime = s; } catch (e) { /* видео могло быть ещё не готово */ }
    }
  }
}
```

(функцию `formatTime()` в конце файла не трогай — она остаётся единственной).

**3.4. Понятное сообщение при неподдерживаемом кодеке.** В `loadVideoForSign()` найди:

```javascript
    } catch (err) {
      console.error(`[loadVideoForSign] Ошибка проверки доступности:`, err);
      videoStatus.textContent = `Видео недоступно: ${err.message}`;
      videoStatus.style.display = "block";
      video.style.display = "none";
      return;
    }
```

Замени на:

```javascript
    } catch (err) {
      console.error(`[loadVideoForSign] Ошибка проверки доступности:`, err);
      const codecHint = (err.message || '').includes('H.264')
        ? ' Похоже, видео закодировано не в H.264 (например, HEVC/H.265 — типичная настройка '
          + 'GoPro при высоком разрешении). Встроенный плеер поддерживает только H.264+AAC. '
          + 'Решение: перекодируйте файл командой '
          + 'ffmpeg -i input.mp4 -c:v libx264 -c:a aac -movflags +faststart output.mp4'
        : '';
      videoStatus.textContent = `Видео недоступно: ${err.message}.${codecHint}`;
      videoStatus.style.display = "block";
      video.style.display = "none";
      return;
    }
```

И добавь в CSS-правило `#video-status` свойство `white-space: pre-line;`, чтобы длинное
сообщение с командой ffmpeg переносилось по словам аккуратно (сейчас там нет явного
`white-space`, значит применится обычный `normal` — это не критично, но лучше явно задать).

**3.5. Очистка неиспользуемых переменных.** `let vcPlaying = false; let vcInterval = null;`
становятся полностью мёртвыми после удаления `vcToggle` — удали обе строки (переменная
`vcSeconds` остаётся, т.к. используется в `vcSetTime`/`jumpToFrame`).

### Критерии приёмки
- Запустить обработку видео, открыть вкладку «Карта», включить Live-режим — маркер позиции
  (`.pos-marker`) должен двигаться по треку каждую секунду, в консоли браузера (F12) не должно
  быть `TypeError` в обработчике `position`.
- Кликнуть на знак на карте, дождаться загрузки видео в правой панели — работает как раньше.
- Нажать «⏩ К кадру» — появляется корректный toast «Прыжок к mm:ss» (не «Ошибка перехода»).
- Если тестовое видео в HEVC (проверить через `testVideoCodec()` кнопку 🔍) — пользователь видит
  внятное сообщение с готовой командой ffmpeg, а не голое «видео недоступно».

---

## ЗАДАЧА 4 — Чёрные области в светлой теме (Processing / Error Editor)

### Диагноз

**4a. Корневая причина, из-за которой светлая тема вообще плохо проявляется.**
`main.py`, функция `main()`:

```python
theme_manager.set_theme(Theme.DARK, app)
```

Это вызывается **безусловно** при каждом запуске, ДО создания `MainWindow`, и полностью
перезаписывает тему, уже восстановленную конструктором `ThemeManager.__init__()` из
персистентных `QSettings` (`_load_saved_theme()`). То есть даже если пользователь выбрал и
сохранил светлую тему в прошлый раз — при следующем запуске всё равно будет тёмная, пока он
вручную не переключит её снова в текущей сессии.

**4b. Виджеты не обновляются при смене темы.** `ui/widgets/processing_page.py` и
`ui/widgets/error_editor_page.py` красят множество элементов через
`widget.setStyleSheet(f"...{theme_manager.tokens[...]}...")` —f-строка вычисляется ОДИН РАЗ
в момент создания виджета (то есть на теме, активной при конструировании — а конструирование
происходит на старте `MainWindow.__init__`, когда тема всегда DARK из-за 4a). Ни `ProcessingPage`,
ни `ErrorEditorPage` не подписаны на `theme_manager.theme_changed` — единственный виджет,
который это делает — `Sidebar` (`_on_theme_changed`). Значит, при переключении на светлую тему
через настройки эти конкретные элементы остаются перекрашены в тёмные цвета — отсюда «чёрные»
области.

Конкретно затронутые виджеты:

- `ProcessingPage`: `video_header`, `self._frame_info`, `self.video_label` (и плейсхолдер, и
  область реального кадра), `self._pct_lbl`, `self._eta_lbl`, мини-статы в `_make_mini_stat()`,
  `log_header`, `self._clear_btn`, **и особенно** `self.log_console` — у него уже стоит
  `setObjectName("LogConsole")` (для этого objectName в `modern_styles.py` уже есть корректная,
  тема-зависимая CSS-запись `#LogConsole {...}`!), но сразу следом идёт `setStyleSheet(...)` с
  захардкоженными на момент создания цветами, который эту глобальную стилизацию перекрывает.
- `ErrorEditorPage`: топбар, бейджи счётчиков, панель фильтров, `self._filter_combo` (тоже
  дублирует уже существующее глобальное правило `QComboBox {}`), навбар списка,
  `frame_card` (уже имеет `setObjectName("Card")`, но следом инлайново перекрашивается заново),
  заголовок предпросмотра кадра, `self._frame_label` (сама область превью кадра — самый заметный
  «чёрный ящик»), мета-лейблы (`_meta_label`/`_meta_val`).

**4c. Отсутствующие токены темы.** В `ui/themes/modern_light.py` вообще нет ключей `video_bg` /
`video_controls` (они есть только в `modern_dark.py`). В `modern_styles.py` уже определено
неиспользуемое нигде правило `#VideoLabel { background-color: {t.get('video_bg', '#000000')}; ...}`
— то есть если бы кто-то сегодня повесил `objectName("VideoLabel")` на реальный виджет, в
светлой теме он всё равно получил бы чёрный фон через дефолт `'#000000'` в `.get(...)`.

> Важно: то, что «канвас» видео/кадра остаётся тёмным независимо от темы приложения — это
> **осознанное и правильное** решение (так делают почти все видеоплееры, включая светлые темы
> YouTube/VLC), а не баг сам по себе. Баг — в том, что (1) это нигде явно не задекларировано
> токеном для светлой темы, и (2) вся ОКРУЖАЮЩАЯ хром-обвязка (заголовки, подписи, лог, мета-
> информация) тоже случайно осталась тёмной, хотя обязана следовать теме приложения.

### Изменения

#### 4.1 Исправить сброс темы при старте — `main.py`

Найди:

```python
        logger.info("Применение темы оформления...")
        theme_manager.set_theme(Theme.DARK, app)
```

Замени на:

```python
        logger.info("Применение темы оформления...")
        # BLOCK STAB-6: раньше тема ВСЕГДА принудительно сбрасывалась на
        # тёмную при каждом запуске, независимо от того, что пользователь
        # выбрал и сохранил в Настройках в прошлый раз. ThemeManager уже
        # восстановил последнюю сохранённую тему в своём конструкторе
        # (_load_saved_theme()) — здесь нужно её ПРИМЕНИТЬ, а не перезаписать.
        theme_manager.apply(app)
```

#### 4.2 Синхронизировать комбобокс темы в настройках с реальным состоянием

Файл `ui/widgets/settings_page.py`. Найди:

```python
        self._theme_combo.setCurrentIndex(
            0 if self._settings.theme == "dark" else 1
        )
```

Замени на:

```python
        # BLOCK STAB-6: читаем ЖИВОЕ состояние ThemeManager, а не
        # AppSettings.theme — это два независимых хранилища (см. диагноз
        # в PROMPT_FIX_UX_STABILITY_THEME.md, задача 4), и после фикса
        # main.py именно theme_manager.current отражает реально применённую
        # сейчас тему.
        self._theme_combo.setCurrentIndex(
            0 if theme_manager.current == Theme.DARK else 1
        )
```

#### 4.3 Добавить недостающие токены — `ui/themes/modern_light.py`

Найди:

```python
    # === Progress & Charts === #
    "progress_bg":      "#e5e7eb",
    "progress_fill":    "#0969da",
    
    # === Scrollbar === #
```

Вставь между ними:

```python
    # === Progress & Charts === #
    "progress_bg":      "#e5e7eb",
    "progress_fill":    "#0969da",

    # === Video Preview === #
    # Канвас видео/кадра осознанно остаётся тёмным в ОБЕИХ темах (как у
    # большинства видеоплееров) — но значение должно быть явно задано для
    # каждой темы, а не подразумеваться дефолтом '#000000' в коде.
    "video_bg":         "#0a0a0a",
    "video_controls":   "#1a1a1a",

    # === Scrollbar === #
```

#### 4.4 `ui/themes/modern_styles.py` — новые objectName-правила

Найди существующее правило (в самом низу файла):

```css
/* ── Video Preview ──────────────────────────────────────────────── */
#VideoLabel {{
    background-color: {t.get('video_bg', '#000000')};
    border-radius: 8px;
    border: 1px solid {t['border_default']};
}}
```

Замени на:

```css
/* ── Video Preview ──────────────────────────────────────────────── */
#VideoLabel {{
    background-color: {t.get('video_bg', '#0a0a0a')};
    /* Текст поверх видео-канваса — намеренно НЕ зависит от темы
       приложения (канвас всегда тёмный), поэтому это литерал, а не
       токен из t[...]. Не переводи это в токен из соображений
       «единообразия» — тогда в светлой теме текст станет
       нечитаемым на тёмном фоне. */
    color: #9aa4af;
    border-radius: 8px;
    border: 1px solid {t['border_default']};
}}
```

Сразу под ним добавь новый блок правил (используются в задачах 4.5/4.6 ниже):

```css
/* ── Preview headers (переиспользуются в Processing и Error Editor) ── */
#PreviewHeader {{
    background-color: {t['bg_tertiary']};
    border-radius: 8px 8px 0px 0px;
}}

#PreviewFrameInfo {{
    color: {t['text_tertiary']};
    font-size: 10px;
    background: transparent;
}}

#PreviewEta {{
    color: {t['text_tertiary']};
    font-size: 11px;
    background: transparent;
}}

#ProgressPercent {{
    color: {t['text_primary']};
    font-size: 32px;
    font-weight: 200;
    letter-spacing: -1px;
    background: transparent;
}}

#MiniStatValue {{
    color: {t['text_primary']};
    font-size: 18px;
    font-weight: 300;
    background: transparent;
}}

#MiniStatLabel {{
    color: {t['text_tertiary']};
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.8px;
    background: transparent;
}}

#ClearLogBtn {{
    color: {t['text_tertiary']};
    font-size: 10px;
    background: transparent;
    border: none;
    text-decoration: underline;
}}

/* ── Error Editor ─────────────────────────────────────────────────── */
#EditorTopbar {{
    background-color: {t['bg_secondary']};
    border-bottom: 1px solid {t['border_subtle']};
}}

#EditorFilterBar {{
    background-color: {t['bg_tertiary']};
    border-bottom: 1px solid {t['border_subtle']};
}}

#EditorNavBar {{
    background-color: {t['bg_tertiary']};
    border-top: 1px solid {t['border_subtle']};
}}

#EditorNavLabel {{
    color: {t['text_tertiary']};
    font-size: 11px;
    background: transparent;
}}

#SignListView {{
    background: {t['bg_secondary']};
    border: none;
}}
#SignListView::item:selected {{
    background: {t['accent_subtle']};
}}

#MetaValueBig {{
    color: {t['text_primary']};
    font-size: 20px;
    font-weight: 300;
    background: transparent;
}}

#MetaValue {{
    color: {t['text_primary']};
    font-size: 12px;
    font-weight: 400;
    background: transparent;
}}
```

> Проверь, в `build_modern_qss()` или в `_build_modern_qss_part2()` физически находится хвост
> файла с f-строкой — вставляй новый блок в тот же метод, что и уже существующее правило
> `#VideoLabel` (обе части объединяются конкатенацией строк в `build_modern_qss()`, поэтому
> важно только не разорвать f-строку).

#### 4.5 `ui/widgets/processing_page.py`

Замени инлайн-стили на `objectName` (глобальный QSS сам обновится на смену темы — подписка на
`theme_changed` для этой страницы не нужна):

| Было (инлайн) | Стало |
|---|---|
| `video_header.setStyleSheet(f"background: {theme_manager.tokens['bg_tertiary']}; border-radius: 8px 8px 0px 0px;")` | `video_header.setObjectName("PreviewHeader")` |
| `self._frame_info.setStyleSheet(f"color: {theme_manager.tokens['text_tertiary']}; font-size: 10px; background: transparent;")` | `self._frame_info.setObjectName("PreviewFrameInfo")` |
| `self._pct_lbl.setStyleSheet(f"color: {theme_manager.tokens['text_primary']}; font-size: 32px; font-weight: 200; letter-spacing: -1px; background: transparent;")` | `self._pct_lbl.setObjectName("ProgressPercent")` |
| `self._eta_lbl.setStyleSheet(f"color: {theme_manager.tokens['text_tertiary']}; font-size: 11px; background: transparent;")` | `self._eta_lbl.setObjectName("PreviewEta")` |
| `log_header.setStyleSheet(f"background: {theme_manager.tokens['bg_tertiary']};")` | `log_header.setObjectName("PreviewHeader")` |
| `self._clear_btn.setStyleSheet(f"color: {theme_manager.tokens['text_tertiary']}; font-size: 10px; background: transparent; border: none; text-decoration: underline;")` | `self._clear_btn.setObjectName("ClearLogBtn")` |

`self.log_console` — **удали** блок `self.log_console.setStyleSheet(...)` целиком. Оставь
только `self.log_console.setObjectName("LogConsole")` (эта строка уже есть) — глобальное правило
`#LogConsole` в `modern_styles.py` уже полностью корректно и тема-зависимо.

`_make_mini_stat(self, value, label)` — замени тело:

```python
def _make_mini_stat(self, value: str, label: str):
    card = QWidget()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(10, 10, 10, 10)
    layout.setSpacing(2)

    val_lbl = QLabel(value)
    val_lbl.setObjectName("MiniStatValue")

    lbl_lbl = QLabel(label.upper())
    lbl_lbl.setObjectName("MiniStatLabel")

    layout.addWidget(val_lbl)
    layout.addWidget(lbl_lbl)
    return card, val_lbl
```

`self.video_label` — задай `setObjectName("VideoLabel")` один раз при создании (рядом с
`self.video_label = QLabel()`), и упрости `_show_placeholder()`:

```python
def _show_placeholder(self):
    self.video_label.setText("Видео не запущено")
    # Фон/цвет текста задаются глобальным QSS-правилом #VideoLabel
    # (см. ui/themes/modern_styles.py) — оно теперь одинаково корректно
    # работает в тёмной и светлой темах.
```

(объект `self.video_label` создаётся в `__init__` — добавь туда
`self.video_label.setObjectName("VideoLabel")` сразу после `self.video_label = QLabel()`, до
вызова `self._show_placeholder()`).

#### 4.6 `ui/widgets/error_editor_page.py`

Аналогичные замены:

| Было | Стало |
|---|---|
| `bar.setStyleSheet(f"background: {t['bg_secondary']}; border-bottom: 1px solid {t['border_subtle']};")` (в `_build_topbar`) | `bar.setObjectName("EditorTopbar")` |
| `sep.setStyleSheet(f"background: {t['border_subtle']};")` (разделитель в топбаре) | `sep.setObjectName("Separator")` |
| `filter_bar.setStyleSheet(f"background: {t['bg_tertiary']}; border-bottom: 1px solid {t['border_subtle']};")` | `filter_bar.setObjectName("EditorFilterBar")` |
| `self._filter_combo.setStyleSheet(...)` | удалить — глобальное правило `QComboBox {}` уже применяется автоматически |
| `self._list_view.setStyleSheet(f"QListView {{...}} QListView::item:selected {{...}}")` | `self._list_view.setObjectName("SignListView")`, стиль удалить (правило добавлено в 4.4) |
| `nav_bar.setStyleSheet(f"background: {t['bg_tertiary']}; border-top: 1px solid {t['border_subtle']};")` | `nav_bar.setObjectName("EditorNavBar")` |
| `self._lbl_nav.setStyleSheet(f"color: {t['text_tertiary']}; font-size: 11px; background: transparent;")` | `self._lbl_nav.setObjectName("EditorNavLabel")` |
| `frame_card.setStyleSheet(f"background: {t['bg_secondary']}; border-bottom: 1px solid {t['border_subtle']};")` (после `setObjectName("Card")`) | удалить — `#Card` уже покрывает фон/границу |
| `fh.setStyleSheet(f"background: {t['bg_tertiary']};")` | `fh.setObjectName("PreviewHeader")` (переиспользуем правило из 4.5) |
| `self._lbl_frame_info.setStyleSheet(f"color: {t['text_tertiary']}; font-size: 10px; background: transparent;")` | `self._lbl_frame_info.setObjectName("PreviewFrameInfo")` |
| `self._frame_label.setStyleSheet(f"background: {t['bg_primary']};")` (в `_build_detail_panel`) | `self._frame_label.setObjectName("VideoLabel")` |
| `vsep.setStyleSheet(f"background: {t['border_subtle']};")` | `vsep.setObjectName("Separator")` |

В методе `_load_frame()` найди ДВА места, где на ошибку/отсутствие данных делается:

```python
            self._frame_label.setText("Нет данных о кадре")
            self._frame_label.setStyleSheet(
                f"background: {t['bg_primary']}; color: {t['text_tertiary']};"
            )
```

и аналогично `"Видео не найдено"` / `"Не удалось открыть видео"` — **удали** вызовы
`setStyleSheet(...)` в обоих местах, оставь только `.setText(...)` (фон/цвет теперь задаёт
глобальное правило `#VideoLabel`, применённое один раз через `setObjectName`).

`_meta_val()` — замени тело:

```python
def _meta_val(self, text: str, big: bool = False) -> QLabel:
    lbl = QLabel(text)
    lbl.setObjectName("MetaValueBig" if big else "MetaValue")
    return lbl
```

`_tb_badge()` и бейджи счётчиков — эти два лейбла (`self._lbl_total`, `self._lbl_low_conf`)
красятся семантическим цветом (нейтральный / «ошибка»), который нельзя выразить одним
статическим objectName-правилом без потери смысла — оставь их управляемыми кодом, но вынеси
перекраску в отдельный метод и вызывай его и при создании, и при смене темы:

```python
def _restyle_badges(self) -> None:
    t = theme_manager.tokens
    self._lbl_total.setStyleSheet(
        f"color: {t['text_tertiary']}; font-size: 11px; font-weight: 600;"
        "background: transparent; padding: 0 4px;"
    )
    self._lbl_low_conf.setStyleSheet(
        f"color: {t['error']}; font-size: 11px; font-weight: 600;"
        "background: transparent; padding: 0 4px;"
    )
```

В `_build_topbar()` замени:

```python
        self._lbl_total    = self._tb_badge("0 знаков", t["text_tertiary"])
        self._lbl_low_conf = self._tb_badge("0 < 50%", t["error"])
```

на:

```python
        self._lbl_total    = self._tb_badge("0 знаков")
        self._lbl_low_conf = self._tb_badge("0 < 50%")
```

и упрости `_tb_badge`, убрав параметр `color` (просто `QLabel(text)` без стиля), затем в конце
`_build_topbar()` вызови `self._restyle_badges()`.

Наконец, в `ErrorEditorPage.__init__` (в самом конце) добавь:

```python
        theme_manager.theme_changed.connect(self._on_theme_changed)
```

и метод:

```python
    def _on_theme_changed(self, _theme_name: str) -> None:
        """
        Большая часть стилизации переведена на objectName + глобальный QSS
        и обновляется автоматически. Здесь досчитываем только то, что
        принципиально не выражается статическим QSS: цветные бейджи
        счётчиков (зависят и от темы, и от семантики "обычный"/"ошибка"),
        и перекраску карточки уверенности текущего выбранного знака.
        """
        self._restyle_badges()
        if self._current_rec is not None:
            self._show_record(self._current_rec)
```

`ProcessingPage` подписку на `theme_changed` добавлять не нужно — после миграции на
`objectName` там не остаётся ничего, что требовало бы ручного пересчёта.

### Критерии приёмки
- Запустить приложение — тема при старте соответствует последней сохранённой (не всегда DARK).
- Переключить тему на «Светлая» в Настройках, перейти на вкладку «Обработка» — заголовок
  предпросмотра, счётчики, лог-консоль, проценты прогресса становятся светлыми/читаемыми
  (видео-канвас намеренно остаётся тёмным, текст на нём — светло-серым, читаемым).
- Перейти в «Редактор ошибок», загрузить GeoJSON — топбар, панель фильтров, список знаков,
  панель метаданных читаемы в светлой теме; область превью кадра остаётся тёмной с читаемым
  текстом состояния («Нет данных о кадре» и т.п.).
- Переключить тему туда-обратно несколько раз без перезапуска — никаких «залипших» тёмных
  участков не остаётся.

---

## ЗАДАЧА 5 — Рекомендации по дальнейшему развитию проекта (бэклог, не обязательно к выполнению сейчас)

Ниже — приоритизированный список технического долга, обнаруженного при анализе. Не требует
немедленной реализации, но стоит завести как тикеты:

1. **Единый источник истины для темы.** Сейчас есть ДВА независимых хранилища: собственный
   `QSettings("RoadScanner", "Theme")` внутри `ThemeManager` и поле `AppSettings.theme` (через
   `QSettings("Signer", "RoadScanner")`), синхронизируемые только частично и только в момент
   явного нажатия «Сохранить» в настройках. Стоит сделать `AppSettings.theme` единственным
   источником и убрать дублирующее хранилище в `ThemeManager`.
2. **Базовый класс/миксин для тема-зависимых виджетов.** Паттерн «баг из задачи 4» (инлайн-стиль
   с застывшими токенами) наверняка воспроизводится и в `DashboardPage`/`MapPage`
   (`_MapPlaceholder` создаёт `self._icon`/`self._title` с инлайн-цветом один раз, без
   подписки на `theme_changed`). Стоит завести `ThemedWidget`-миксин с методом
   `_apply_theme()`, который вызывается и в `__init__`, и по сигналу — вместо повторения
   одного и того же паттерна вручную в каждом файле.
3. **Консолидация огромного количества постмортем-документов в `docs/`.** Десятки файлов вида
   `CRASH_FIX_*.md`, `BUGFIXES_*.md`, `PROFILING_*.md` описывают историю разовых фиксов и местами
   противоречат друг другу (например, `BATCHING_FAILURE_ANALYSIS.md` про откат батчинга vs
   `tests/test_performance_optimizations.py`, который проверяет НАЛИЧИЕ батч-методов). Нужен один
   `CHANGELOG.md` + несколько ADR (Architecture Decision Records) вместо десятков разрозненных
   md-файлов.
4. **Завершить миграцию `print()` → `logging`.** `docs/LOGGING_MIGRATION_GUIDE.md` фиксирует, что
   миграция сделана лишь частично (`main.py`, `ui/main_window.py`); в `configs/settings.py`,
   `core/osm_snap.py`, `processing/processing_controller.py` (частично) и других местах остались
   голые `print()`.
5. **Глобальное мутируемое состояние `configs/config.py`.** Индексы обработки (`INDEX_OF_FRAME`,
   `INDEX_OF_VIDEO` и т.д.) хранятся как модульные глобальные переменные — что уже создаёт
   проблемы при переходе на `process_pool` (требуется ручная сериализация через `frame_data`
   dict). Стоит инкапсулировать это в явный `ProcessingContext`, передаваемый параметром, а не
   читаемый из глобального модуля — это одновременно упростит тестирование и уберёт риск гонок
   между режимами обработки.
6. **CI и автоматизированные тесты.** Много «тестов» в `tests/`/`scripts/` — это самописные
   скрипты с `print("PASS"/"FAIL")` без pytest/CI-интеграции. Стоит перевести всё на `pytest`,
   добавить GitHub Actions (lint + pytest + `mypy` — типизация в коде уже активно используется,
   но не проверяется статически).
7. **Единый источник данных по знакам.** `configs/sign_data.py` (Python-словари) и `signs.json`
   (XML→JSON дамп) описывают частично одни и те же знаки в двух разных форматах — стоит выбрать
   один источник истины (рекомендуется JSON/YAML, т.к. он проще для нетехнического
   редактирования) и генерировать второй артефакт автоматически, либо явно задокументировать,
   для чего нужен именно `signs.json`, если он не используется кодом активно (это стоит
   проверить — по предоставленным файлам не видно импорта `signs.json` в коде).
8. **Транскодирование видео для встроенного плеера карты.** См. задачу 3 — стоит добавить
   серверный эндпоинт, который при первом запросе видео с неподдерживаемым кодеком (HEVC и т.п.)
   выполняет разовое фоновое перекодирование в H.264 через `ffmpeg` (если он установлен в
   системе) и кэширует результат рядом с исходником, вместо того чтобы полагаться на то, что
   пользователь сам разберётся с кодеком.
9. **Изоляция инференса моделей от Qt-процесса.** Множество документов (`CRASH_FIX_*`,
   `docs/CRASH_FIX_v1.3.3.md`) описывают борьбу с крашами `0xC0000409` от совместного
   использования PyTorch/OpenMP и Qt WebEngine в одном процессе через переменные окружения.
   Более надёжное архитектурное решение — вынести инференс в постоянно живущий отдельный
   процесс (аналогично уже существующему `DetectorProcessPool`, но как постоянный сервис, а не
   ad-hoc пул) и общаться с ним через IPC/gRPC, что снимет весь класс подобных проблем в
   принципе, а не только откладывает их через тюнинг переменных окружения.
10. **Юнит-тесты для новых участков задачи 2 и 4.** Добавить `tests/test_detector_thread_resilience.py`
    (проверка, что исключение в одном кадре не останавливает `_process_loop`) и
    `tests/test_theme_widgets.py` (структурная проверка, что виджеты Processing/ErrorEditor не
    содержат инлайн `setStyleSheet` с `theme_manager.tokens[...]`, кроме явно задокументированных
    исключений) — по аналогии с уже существующими структурными тестами в этом репозитории
    (`tests/test_performance_optimizations.py`).

---

## 6. Чек-лист перед коммитом

- [ ] `pytest tests/` проходит (там, где тесты не требуют GPU/реального видео).
- [ ] `python tests/run_geometry_tests.py`, `python tests/check_dashboard_page.py`,
      `python tests/check_socketio_config.py`, `python tests/check_eager_loading.py` — без regressions.
- [ ] Ручной прогон обработки короткого (1–2 мин) видео в режиме «Один поток» — GeoJSON
      сохраняется, число знаков разумно, обработка не завершается раньше конца файла.
- [ ] То же в режиме Process Pool — тот же результат, `finished` эмитится корректно.
- [ ] Карта: Live-режим двигает маркер позиции; клик по знаку открывает видео; «⏩ К кадру»
      показывает корректный toast.
- [ ] Настройки: в Простом режиме виден выбор режима обработки; переключение сохраняется.
- [ ] Светлая тема: ни один участок Processing/Error Editor не остаётся тёмным после
      переключения без перезапуска приложения; тема сохраняется между запусками.
- [ ] Ни одного нового `print()` не добавлено (только `logging`).
- [ ] `git diff` не затрагивает переменные окружения/потоковые ограничения в `main.py`,
      относящиеся к защите от `0xC0000409`.
