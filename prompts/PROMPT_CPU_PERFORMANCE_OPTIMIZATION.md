# PROMPT: Оптимизация производительности RoadScanner при отсутствии GPU (CPU-only)

**Аудитория:** ИИ-агент с доступом к кодовой базе RoadScanner (Signer PRIME).
**Цель:** максимально ускорить пайплайн детекции/трекинга/OCR знаков на машинах **без CUDA**,
не ухудшив точность и не сломав GPU-путь и существующую функциональность.

Документ написан в том же формате, что и другие agent-промпты в этом репозитории
(см. `BLOCK_H_TURN_GEOMETRY_*.md`, `BLOCK_C_ASYNC_OCR_IMPLEMENTATION.md`,
`AGENT_PROMPT_EXECUTION_REPORT*.md`) — следуй той же дисциплине: preflight → блок → тест → отчёт.

---

## 0. Контекст

RoadScanner обрабатывает видео с видеорегистратора: `VideoReaderThread` читает кадры →
`DetectorThread` прогоняет их через `Detector` (YOLO bbox → YOLO rube-классификация →
CNN точная классификация → опционально OCR через EasyOCR) → `SignHandler` трекает знаки
между кадрами → `FinalHandler` сохраняет результат в GeoJSON.

Есть настройка `AppSettings.use_cuda` (`configs/settings.py`) и `_resolve_device()`
(`configs/sign_models.py`), которые уже корректно откатываются на `"cpu"`, если CUDA
недоступна. **Проблема не в том, что CPU-путь не работает — а в том, что он работает
гораздо медленнее, чем мог бы**, потому что несколько частей пайплайна:
- либо жёстко ограничивают параллелизm CPU (`torch.set_num_threads(1)` в трёх местах),
- либо делают избыточную работу на каждый кадр без необходимости (декодирование
  пропускаемых кадров, отрисовка превью каждый кадр, повторный OCR одного и того же знака
  десятки раз),
- либо содержат уже реализованную, но не подключённую оптимизацию
  (TrackedSign CNN-skip кэш из BLOCK B.3 — см. `BLOCK_B3_TRACKED_SIGN_CACHE.md`).

Ниже — приоритизированный список блоков работ. **Каждый блок делай отдельным коммитом
и отдельным разделом отчёта.** Не смешивай блоки друг с другом.

---

## 1. Критические ограничения (что нельзя ломать)

1. **GPU-путь не должен измениться.** Все правки должны быть либо нейтральны для
   `use_cuda=True` + доступной CUDA, либо явно применяться только когда
   `torch.cuda.is_available() == False` / `settings.use_cuda == False`.
2. **Формат GeoJSON и его поля (`conf_cnn`, `conf_placement`, `conf_total`, `SEM250`,
   `MVALUE`, `absolute_frame_numbers` и т.д.) не должны измениться** — потребители
   (карта, редактор ошибок) на них завязаны.
3. **Никакой деградации точности классификации/OCR "по умолчанию".** Любая оптимизация,
   которая теоретически может изменить результат (троттлинг OCR, пропуск CNN, снижение
   `imgsz`, ONNX/OpenVINO backend) — **за отдельным флагом в `AppSettings`**, включённым
   по умолчанию только если она безопасна (см. критерии приёмки в каждом блоке), и с
   возможностью отката к текущему поведению одним изменением настройки.
4. **Крах `0xC0000409` (STATUS_STACK_BUFFER_OVERRUN) — конфликт OpenMP-рантаймов на
   Windows — уже случался и был исправлен** (`torch.set_num_threads(1)`,
   `KMP_DUPLICATE_LIB_OK=TRUE`, `OMP_NUM_THREADS=1` в `main.py`, см.
   `BUGFIX_VIDEO_FOLDER_CRASH_0xC0000409.md`, `BUGFIX_SETTINGS_CRASH_0xC0000409.md`).
   Любые изменения потоковой модели (БЛОК 5) обязаны включать длительный
   (≥30 минут, ≥5000 кадров) прогон на реальном Windows CPU-only окружении, прежде чем
   считаться завершёнными.
5. **Регрессионное тестирование обязательно для блоков, способных изменить результат
   детекции** (1, 3, 4, 5, 7): используй/расширь `scripts/test_detector_regression.py`
   (сохранение baseline → сравнение после правок) и `scripts/benchmark_detector.py`
   (замер FPS до/после).
6. Каждый блок фиксируется отдельным отчётом `CPU_OPT_BLOCK_<N>_<NAME>.md` по аналогии
   с существующими `BLOCK_*.md` в корне репозитория, плюс итоговый сводный
   `CPU_OPT_SUMMARY.md` (см. БЛОК 10).

---

## 2. Приоритизация блоков

| Блок | Название | Ожидаемый эффект | Сложность | Риск |
|---|---|---|---|---|
| 0 | Baseline-профилирование | — (обязателен перед всем) | низкая | нет |
| 1 | `grab()`/`retrieve()` вместо `read()` для пропускаемых кадров | высокий | низкая | низкий |
| 2 | Троттлинг UI-превью, независимый от детекции | средний-высокий | низкая | низкий |
| 3 | Подключить TrackedSign CNN-skip кэш (`detect_with_tracking`) | высокий | средняя | низкий |
| 4 | Троттлинг/переиспользование OCR на уровне TrackedSign | очень высокий (видео с текстовыми знаками) | средняя | средний |
| 5 | Пересмотр бюджета CPU-потоков (torch/OMP/MKL) | высокий | средняя | **высокий** |
| 6 | Диагностика/фикс `processing_mode` и корректности Process Pool | средний (+ критично для корректности) | средняя-высокая | средний |
| 7 | (опционально) ONNX/OpenVINO backend для YOLO на CPU | очень высокий | высокая | средний |
| 8 | Авто-профиль "CPU Performance Mode" + автодетект отсутствия GPU | средний (UX + защита от плохих дефолтов) | низкая | низкий |
| 9 | Методология бенчмарков / регрессии | — (инструмент) | низкая | нет |
| 10 | Итоговая документация | — | низкая | нет |

Рекомендуемый порядок выполнения: **0 → 1 → 2 → 3 → 4 → 6 → 8 → 9 → (5 и 7 отдельными
итерациями с расширенным тестированием) → 10.**

---

## БЛОК 0 — Baseline-профилирование (обязательный preflight)

**Цель:** зафиксировать текущие цифры ДО любых изменений, чтобы потом доказать эффект.

### Шаги
1. На машине без GPU (или с временно `settings.use_cuda = False`, чтобы гарантированно
   гонять CPU-путь даже если физическая GPU есть) прогони:
   ```bash
   .venv\Scripts\python.exe scripts\benchmark_detector.py --video <test.mp4> --frames 300
   .venv\Scripts\python.exe scripts\benchmark_detector.py --video <test.mp4> --frames 300 --with-ocr
   ```
2. Включи `config.ENABLE_PROFILING = True` (или `enable_profiling()` из
   `core/profiler.py`) и обработай через `main.py` реальное тестовое видео
   (≥2000 кадров, с GPX, желательно с городскими/текстовыми знаками и участком с
   поворотами/перекрёстками) в **single_thread** и в **pipeline** режимах.
3. Зафиксируй в `CPU_OPT_BLOCK_0_BASELINE.md`:
   - FPS (детекция без OCR, детекция с OCR, полный прогон через `main.py`);
   - разбивку `profiler.get_report()` по стадиям
     (`yolo_bbox_detection`, `batch_classify_rube`, `batch_classify_fine`,
     `ocr_read_text`, `draw_boxes_and_emit`, `video_read_frame`, `sign_handler_tracking`);
   - число ядер/потоков тестовой машины (`os.cpu_count()`), наличие AVX2/MKL;
   - итоговое число знаков в GeoJSON (для последующего regression-сравнения);
   - `test_detector_regression.py --save-baseline` на 50-100 кадрах с текстовыми и
     обычными знаками — сохрани `regression_baseline.json`, он понадобится для
     проверки блоков 1, 3, 4, 5, 7.

**Не переходи к следующим блокам, пока этот отчёт не готов.**

---

## БЛОК 1 — Декодирование видео: `grab()` вместо `read()` для пропускаемых кадров

### Проблема
Файл: `processing/video_reader.py`, метод `VideoReaderThread._read_all_videos()`.

```python
with profiler.measure("video_read_frame"):
    ret, image = cap.read()
...
local_frame += 1
frame_counter += 1
if frame_counter % step != 0:
    continue   # ← кадр уже ПОЛНОСТЬЮ декодирован, хотя сейчас будет выброшен
```

`cap.read()` = `cap.grab()` (взять следующий кадр из потока) + `cap.retrieve()`
(полное декодирование + цветовое преобразование в BGR-массив). При `FRAME_STEP=5`
(дефолт) **4 из 5 кадров декодируются полностью впустую** — это чистые CPU-циклы,
которые нигде не используются. На CPU-only машине (нет NVDEC) это особенно дорого,
т.к. декодирование конкурирует за те же ядра, что и инференс.

### Что сделать
Переставь порядок: сначала дешёвый `grab()`, полное декодирование (`retrieve()`) —
только если кадр действительно нужен обработке.

```python
while True:
    if self._stop:
        break
    while self._paused:
        time.sleep(0.05)

    step = max(1, int(config.FRAME_STEP))

    if use_frame_limit and local_frame >= total_frames_in_video:
        break

    with profiler.measure("video_grab_frame"):
        grabbed = cap.grab()

    if not grabbed:
        # конец файла / ошибка чтения — та же диагностика, что раньше на read()==False
        ...
        break

    local_frame += 1
    frame_counter += 1

    if frame_counter % step != 0:
        continue  # НЕ вызываем retrieve() — экономим декодирование

    with profiler.measure("video_retrieve_frame"):
        ret, image = cap.retrieve()

    if not ret or image is None:
        break

    # ... остальной код (frame_in_video, gps_index, RawFrame, put в очередь) без изменений
```

### Важные нюансы
- **Особый случай GoPro/MSMF-бэкенд.** Комментарий в коде явно предупреждает:
  `"FFMPEG падает на ~44 кадре из-за множественных потоков в MP4"`, поэтому
  используется `cv2.CAP_MSMF`. Нужно **проверить на реальном GoPro-файле**, что
  `grab()`/`retrieve()` с MSMF-бэкендом ведёт себя так же стабильно, как и раньше
  использовавшийся паттерн "читать каждый кадр подряд". Если возникают дропы/сдвиги —
  добавь feature-флаг `AppSettings.fast_frame_skip: bool = True` с безопасным откатом
  на старый способ (`cap.read()` каждый кадр) при `False`.
- Сохрани всю существующую диагностику/логирование в `video_debug.log`
  (первые 50 кадров, прогресс каждые 100 кадров, причины завершения) — просто
  адаптируй условия `ret`/`image` под `grabbed`/`retrieve()`.
- Не трогай логику prefetch следующего видео (`_prefetch_next_video`) — она не связана
  с этим изменением.
- Добавь в `core/profiler.py` два новых замера: `video_grab_frame` (дешёвый, для
  пропущенных кадров) и `video_retrieve_frame` (декодирование, для обрабатываемых).
  Это позволит наглядно показать экономию в отчёте.

### Критерии приёмки
- При `FRAME_STEP=5` суммарное время `video_read_frame`-эквивалента (grab+retrieve)
  заметно ниже, чем было `video_read_frame` в baseline (ожидание: пропорционально
  доле пропускаемых кадров).
- **Регрессия обязательна:** байты `image`-массива для каждого ОБРАБАТЫВАЕМОГО кадра
  идентичны байтам, которые давал старый `cap.read()` на той же позиции — это
  проверяется побайтовым/хэш-сравнением на 200+ кадрах (см. `compute_frame_hash()`
  в `test_detector_regression.py`, тот же принцип, но сравнивай кадры до подачи в
  детектор, а не только итоговые детекции).
- Итоговый GeoJSON на тестовом видео идентичен baseline (число знаков, типы, координаты).
- 30-минутный прогон на GoPro-видео без дропов/крашей/рассинхрона с GPX
  (`INDEX_OF_GPS`/`gps_index` логика не должна сместиться).

---

## БЛОК 2 — Троттлинг UI-превью, независимый от логики пропуска детекции

### Проблема
Файл: `processing/detector_thread.py`, метод `_process_loop()`.

`self._emit_frame(raw.image)` / `self._emit_frame(annotated)` вызывается **на каждой
итерации цикла**, включая кадры, которые:
- пропущены из-за низкой скорости (`speed < MIN_SPEED_KMH`);
- пропущены умным frame-skipping (`_should_process_frame() == False`).

Каждый вызов `_emit_frame()` — это `cv2.cvtColor(BGR2RGB)` + создание `QImage` +
`QPixmap.fromImage(...).scaled(960, 540, ...)` на **полном разрешении кадра**
(1920×1080 и выше для GoPro). При 60 fps исходного видео это может означать
десятки таких преобразований в секунду только ради UI, который физически не может
показать больше ~15-20 кадров в секунду и часто вообще может быть свёрнут/не виден.

### Что сделать
1. Добавь в `AppSettings`:
   ```python
   preview_fps_limit: float = 12.0  # макс. частота обновления превью в UI, кадр/сек
   ```
2. В `DetectorThread.__init__`/`run()` сохрани `self._preview_min_interval = 1.0 /
   settings.preview_fps_limit` и `self._last_emit_time = 0.0`.
3. Добавь метод:
   ```python
   def _should_emit_preview(self) -> bool:
       now = time.monotonic()
       if now - self._last_emit_time < self._preview_min_interval:
           return False
       self._last_emit_time = now
       return True
   ```
4. Оберни **все** места вызова `_emit_frame(...)` в `_process_loop()` проверкой
   `if self._should_emit_preview(): self._emit_frame(...)`. Для ветки с полноценной
   детекцией (`annotated = self._draw_boxes(raw.image, detections); self._emit_frame
   (annotated)`) — саму отрисовку `_draw_boxes()` тоже перенеси под тот же `if`,
   чтобы не тратить CPU на рисование боксов, которые не будут показаны.
5. **Важно:** троттлинг влияет только на UI-превью. Детекция, трекинг, сохранение
   знаков в очередь результатов и вся остальная логика цикла должны выполняться
   **на каждом обрабатываемом кадре без изменений** — троттлится только вызов
   `_emit_frame`/`_draw_boxes`.

### Критерии приёмки
- `profiler.get_report()` показывает сокращение суммарного времени
  `draw_boxes_and_emit` пропорционально `preview_fps_limit` относительно реальной
  частоты кадров видео.
- Итоговый FPS обработки (детекция+трекинг) в логах `[SmartSkip] ... FPS: X.X` растёт.
- Визуально: превью на странице "Обработка" остаётся плавным (не залипает,
  не выглядит как один статичный кадр).
- Отсутствие превью-кадра не влияет на `sign_detected`/`stats_updated` сигналы —
  они должны эмититься с той же частотой, что и раньше.

---

## БЛОК 3 — Подключить TrackedSign CNN-skip кэш в реальный пайплайн

### Проблема
Инфраструктура для пропуска повторного CNN-инференса на уже стабильно
распознанных знаках **полностью реализована**, но **не используется**:

- `core/sign.py::TrackedSign` уже содержит `_update_cnn_stability()`,
  `should_skip_cnn()`, `get_stable_cnn_class()`, `reset_cnn_stability()`
  (порог стабильности `STABILITY_THRESHOLD = 5` кадров подряд с одинаковым классом).
- `core/sign_handler.py::SignHandler.get_tracked_signs_map()` уже возвращает
  `dict[(pixel_x, pixel_y) -> TrackedSign]` для активных знаков.
- `core/detector.py::Detector.detect_with_tracking()` уже реализован и умеет
  принимать эту карту и пропускать CNN для стабильных знаков.

Но `processing/detector_thread.py::_process_loop()` вызывает только
`self._detector.find_rectangles(raw.image)` (single-thread) или
`self._detector.detect(raw.image, skip_ocr=True)` (pipeline) — **ни разу не
`detect_with_tracking`**. См. также `BLOCK_B3_TRACKED_SIGN_CACHE.md`, где это
прямо названо незавершённой интеграцией ("инфраструктура готова, интеграция
отложена").

Каждый CNN-forward-pass — это реальная нейросеть на CPU; знак, который трекается
50-100 кадров подряд, сейчас классифицируется CNN **все 50-100 раз**, хотя после
5 стабильных кадров результат почти наверняка не изменится.

### Что сделать
1. В `_process_loop()`, перед вызовом детектора, получи карту трекаемых знаков:
   ```python
   tracked_map = self._sign_handler.get_tracked_signs_map()
   ```
2. Замени вызовы детектора:
   - **Pipeline-режим:**
     ```python
     detections_raw = self._detector.detect_with_tracking(
         raw.image, tracked_map, skip_ocr=True
     )
     detections = [
         [list(d.box), d.color, d.cnn_class, d.yolo_class, d.cnn_class, d.text, d.is_side]
         for d in detections_raw
     ]
     ```
   - **Single-thread режим:** либо добавь в `Detector` метод
     `find_rectangles_with_tracking(frame, tracked_map)` (аналог `find_rectangles`,
     но вызывающий `detect_with_tracking`), либо инлайни ту же трансформацию
     `RawDetection → old-format list`, что уже делает `find_rectangles()`.
     **Не дублируй код** — вынеси общую трансформацию `RawDetection → list-формат`
     в приватный статический метод `Detector._to_legacy_format(detections)` и
     используй его и в `find_rectangles()`, и в новом методе.
3. Добавь счётчик в `Detector` (или используй уже существующий `_cnn_cache` со
   статистикой) для нового вида пропуска — например `self._tracked_skip_count`,
   инкрементируемый внутри `detect_with_tracking()` при каждом
   `stable_class is not None`. Залогируй его в `DetectorThread._update_stats()`
   рядом с существующей строкой про CNN-кэш:
   ```python
   logger.info(f"[TrackedSkip] Пропущено CNN благодаря трекингу: "
               f"{self._detector._tracked_skip_count}/{self._detector._counter} "
               f"({pct:.1f}%)")
   ```

### Критерии приёмки
- **Regression-тест обязателен**: прогони `test_detector_regression.py --compare`
  против baseline из БЛОКА 0. Итоговый список детекций (`yolo_class`, `cnn_class`,
  `box`, `is_side`) должен совпадать с baseline **на кадрах, где знак ещё не
  накопил 5 стабильных наблюдений**; на кадрах после стабилизации допустимо, что
  вместо нового CNN-вызова используется закэшированный класс — но так как это тот
  же самый класс, который CNN бы всё равно вернула (иначе кэш не был бы "стабильным"
  по определению накопленной истории), финальный результат по знаку в GeoJSON
  (`best_cnn`, `cnn_count`, `conf_cnn`) должен остаться прежним.
- Заметное снижение суммарного времени в профилировщике на стадии
  `batch_classify_fine`/CNN-инференса на видео с длинными треками одного знака
  (например, участок с несколькими знаками, которые видны 30+ кадров).
- Лог `[TrackedSkip]` показывает ненулевой процент пропусков на длинном видео.
- Знаки, которые появляются кратковременно (< 5 наблюдений), обрабатываются
  строго как раньше (без изменений в логике).

---

## БЛОК 4 — Троттлинг и переиспользование OCR на уровне TrackedSign

### Проблема (самая дорогая на CPU без GPU)
EasyOCR — самая тяжёлая операция в пайплайне на CPU (CRAFT-детектор текста +
распознавание). Сейчас OCR запускается **заново на каждый кадр**, где виден
текстовый знак, без какого-либо переиспользования уже полученного результата:

- **Pipeline-режим** (`processing/detector_thread.py::_process_loop`):
  ```python
  if self._use_pipeline and detected:
      for det_sign in detected:
          if self._detector.needs_ocr(det_sign.best_cnn, det_sign.best_yolo):
              self._submit_ocr_task(det_sign, raw.image)
  ```
  `detected` — это **свежие, ещё не привязанные к трекингу** `DetectedSign` за
  ТЕКУЩИЙ кадр (объект `SignHandler.check_the_data_to_add()` привязывает их к
  `TrackedSign` только строкой ниже). Проверки "у соответствующего TrackedSign уже
  есть текст" или "OCR недавно запускался для этого знака" — **нет вообще**.
  Знак, видимый 30 кадров, порождает 30 отдельных задач в `OCRPool`/`OCRWorkerThread`.

- **Single-thread режим** (`core/detector.py::Detector._read_text()` /
  `detect()`): то же самое — `_read_text()` вызывается синхронно для каждого
  подходящего детекта каждого кадра, без исключений.

Это уже было замечено в `BLOCK_C_ASYNC_OCR_IMPLEMENTATION.md` как TODO C.2
("Throttling OCR per TrackedSign") — **но не реализовано**.

`FinalHandler._build_feature()` в итоге всё равно берёт
`sign.most_common(sign.text_results)[0]` при `len(text_results) > 4` — то есть
избыточные OCR-вызовы после 4-5 успешных распознаваний **не влияют на финальный
результат вообще**, это чистая трата CPU.

### Что сделать

1. **Добавить троттлинг на уровне `TrackedSign`** (`core/sign.py`):
   ```python
   # ── OCR оптимизация (BLOCK CPU-4) ──────────────────────────────
   _last_ocr_abs_frame: int = -10_000
   _ocr_call_count: int = 0

   OCR_MIN_INTERVAL_FRAMES = 8       # не чаще раза в N обработанных кадров
   OCR_MAX_CALLS_PER_SIGN = 6        # после этого числа успешных вызовов — хватит

   def should_run_ocr(self, current_abs_frame: int) -> bool:
       """
       Решает, нужно ли запускать OCR для этого наблюдения.
       False если: уже достаточно непустых text_results, ИЛИ слишком рано
       после предыдущего вызова.
       """
       non_empty = sum(1 for t in self.text_results if t)
       if non_empty >= self.OCR_MAX_CALLS_PER_SIGN:
           return False
       if self._ocr_call_count >= self.OCR_MAX_CALLS_PER_SIGN * 2:
           # защита от знака, который постоянно даёт разный/пустой текст
           return False
       if current_abs_frame - self._last_ocr_abs_frame < self.OCR_MIN_INTERVAL_FRAMES:
           return False
       return True

   def mark_ocr_requested(self, current_abs_frame: int) -> None:
       self._last_ocr_abs_frame = current_abs_frame
       self._ocr_call_count += 1
   ```
   Числа `OCR_MIN_INTERVAL_FRAMES`/`OCR_MAX_CALLS_PER_SIGN` вынеси в `AppSettings`
   (`ocr_throttle_interval_frames: int = 8`, `ocr_max_calls_per_sign: int = 6`),
   чтобы их можно было потюнить/откатить без правки кода.

2. **Pipeline-режим:** решение об OCR нужно принимать **после** привязки детекции
   к `TrackedSign`, а не до. Самый чистый вариант — переместить вызов
   `_submit_ocr_task` из места ДО `self._sign_handler.check_the_data_to_add(...)`
   на место ПОСЛЕ него, и слать OCR не по «сырым» `detected`, а по
   `self._sign_handler.signs` (актуальные активные `TrackedSign`), проверяя
   `sign.should_run_ocr(raw.abs_frame_number)` для тех, чей `best_yolo`/`best_cnn`
   попадает под `needs_ocr()`. Так как один `TrackedSign` может не иметь
   "свежего" необрезанного изображения текущего кадра под рукой, потребуется
   либо:
   - (а) сохранить последний bbox/crop у `TrackedSign` на момент этого кадра
     (уже есть `pixel_x[-1]`, `pixel_y[-1]`, `widths[-1]`, `heights[-1]` —
     используй их для вырезки crop из `raw.image`), либо
   - (б) продолжать посылать OCR по объектам `detected` (как сейчас), но **до
     отправки** искать соответствующий `TrackedSign` (по совпадению
     `best_yolo`/близости пикселей — переиспользуй тот же радиус поиска, что и
     в `SignHandler.get_tracked_signs_map()`/`detect_with_tracking`) и проверять
     `should_run_ocr()` на нём. Вариант (б) проще и меньше меняет существующий
     код — **предпочтителен**, если не появится веских причин для (а).
3. **Single-thread режим:** аналогично — `Detector.detect()`/`detect_with_tracking()`
   не должен сам решать "троттлить или нет" (Detector должен оставаться
   "чистым" относительно трекинга по возможности), поэтому:
   - либо прокинь `tracked_map` в `_read_text()`/`detect_with_tracking()` и
     проверяй `TrackedSign.should_run_ocr()` там же, где уже проверяется
     `stable_class` (единая точка входа с БЛОКОМ 3 — раз уж карта трекинга там
     уже есть),
   - либо, если это слишком сильно всё связывает, вынеси OCR-решение в
     отдельный шаг `DetectorThread`/`SignHandler` по аналогии с pipeline-режимом.
   Выбери вариант, который меньше дублирует код между режимами — в идеале
   троттлинг-проверка **одна** и переиспользуется в single-thread и pipeline.
4. После фактического вызова OCR (успешного submit/выполнения) — вызови
   `sign.mark_ocr_requested(current_abs_frame)`.

### Критерии приёмки
- Добавь счётчик суммарных вызовов OCR (`self._ocr_calls_total` в
  `DetectorThread`/`OCRPool`/`OCRWorkerThread`) и залогируй его в конце обработки
  видео: `"[OCR] Всего вызовов: N, знаков с текстом: M, среднее на знак: N/M"`.
  На тестовом видео с городскими/текстовыми знаками (несколько знаков, видимых
  20-40+ кадров) число вызовов должно упасть **минимум в 3 раза** относительно
  baseline из БЛОКА 0.
- **Регрессия по содержимому текста обязательна:** финальные значения
  `properties.SEM250`/`MVALUE` в GeoJSON на тестовом видео с текстовыми/городскими
  знаками должны совпадать с baseline (или быть эквивалентно корректными —
  если в baseline текст был получен из большего числа наблюдений, но итоговое
  значение через `most_common()` то же самое, это ОК; если текст стал ПУСТЫМ там,
  где раньше был непустой — это регрессия, чинить пороги).
- Знаки, которые видны **менее `OCR_MIN_INTERVAL_FRAMES` кадров**, всё ещё
  получают хотя бы одну попытку OCR (не должно быть знаков, которые вообще
  никогда не пытались распознать текст).
- FPS в pipeline-режиме на видео с большим количеством городских/текстовых знаков
  заметно растёт (меньше задач в очереди `OCRPool`/`OCRWorkerThread`,
  `pending_count`/`OCR pending:` в логах ниже, чем в baseline).

---

## БЛОК 5 — Пересмотр бюджета CPU-потоков (torch / OMP / MKL) — ОСТОРОЖНО

⚠️ **Самый рискованный блок. Делай последним из "быстрых" блоков, за отдельным
settings-флагом, с максимально консервативным тестированием.**

### Проблема
`torch.set_num_threads(1)` жёстко прописан в трёх местах:
- `processing/detector_thread.py::DetectorThread.run()`
- `processing/detector_pool.py::DetectorWorker.run()`
- `processing/detector_process_pool.py::_worker_process_frame()`

Плюс, судя по `BUGFIX_VIDEO_FOLDER_CRASH_0xC0000409.md`, в `main.py` (не был в
предоставленном контексте — **обязательно прочитай его первым делом в этом блоке**)
устанавливается:
```python
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["QT_OPENGL"] = "software"
```

Всё это было сделано для устранения краха `STATUS_STACK_BUFFER_OVERRUN
(0xC0000409)` — конфликта нескольких копий OpenMP-рантайма (`libiomp5md.dll`)
между PyTorch/MKL и другими библиотеками на Windows.

**Гипотеза (требует проверки, не факт):** `KMP_DUPLICATE_LIB_OK=TRUE` уже сам по
себе устраняет краш, разрешая одновременную загрузку дублирующихся OpenMP-рантаймов
— это стандартный (хоть и "грязный") воркэраунд именно для этой проблемы. Если
это так, то `OMP_NUM_THREADS=1` и `torch.set_num_threads(1)` — избыточная
перестраховка, которая **сжигает почти весь потенциал многоядерного CPU** для
матричного инференса YOLO (свёртки/матмулы в PyTorch на CPU опираются на
многопоточный MKL/oneDNN — с 1 потоком используется буквально одно ядро из
4-16+ доступных).

### Пошаговый план (обязательно в этом порядке, с проверкой на каждом шаге)

1. **Прочитай `main.py` целиком.** Задокументируй в отчёте: какие переменные
   окружения выставляются, в каком порядке относительно импорта `torch`/`cv2`,
   есть ли там что-то ещё связанное с потоками (`cv2.setNumThreads`,
   `MKL_NUM_THREADS`, `OPENBLAS_NUM_THREADS` и т.п.).
2. Добавь в `AppSettings`:
   ```python
   cpu_inference_threads: int = 0  # 0 = авто (max(1, cpu_count - 1))
   ```
   и вспомогательную функцию (например, в новом `core/cpu_utils.py`):
   ```python
   def resolve_thread_count(settings, num_process_workers: int = 1) -> int:
       import os
       if settings.cpu_inference_threads > 0:
           base = settings.cpu_inference_threads
       else:
           base = max(1, (os.cpu_count() or 4) - 1)
       # если это один из N параллельных процессов — делим бюджет, чтобы не
       # создавать oversubscription (N процессов * K потоков > физических ядер)
       return max(1, base // max(1, num_process_workers))
   ```
3. Замени во всех трёх местах `torch.set_num_threads(1)` на
   `torch.set_num_threads(resolve_thread_count(settings, num_process_workers=...))`
   — для `DetectorThread`/`DetectorWorker` (один процесс) `num_process_workers=1`;
   для `_worker_process_frame` (ProcessPoolExecutor) `num_process_workers` = число
   реально запущенных воркеров пула (нужно прокинуть это значение в
   сериализуемую задачу или прочитать из `config`/settings внутри воркера).
4. **НЕ трогай `OMP_NUM_THREADS`/`main.py` на этом шаге.** Сначала протестируй
   эффект только от `torch.set_num_threads()` — PyTorch может частично управлять
   собственным пулом потоков независимо от `OMP_NUM_THREADS`, заданного при
   старте процесса, в зависимости от сборки. Прогони бенчмарк (см. БЛОК 9) и
   посмотри профилировщик: если `yolo_bbox_detection`/`batch_classify_*` заметно
   ускорились — уже хорошо, дальше можно не идти.
5. **Только если после шага 3-4 профилировщик показывает, что MKL всё ещё
   упирается в 1 поток** (например, через `torch.get_num_threads()` в логах при
   старте и явно медленный CNN/YOLO инференс несмотря на настройку) — тогда
   осторожно вынеси `OMP_NUM_THREADS` в переменную окружения, зависящую от
   настройки (устанавливать это нужно **до** первого импорта `torch`/`numpy`/
   `cv2`, то есть в самом начале `main.py`, читая значение из `AppSettings`, что
   означает чтение настроек должно происходить раньше импорта тяжёлых библиотек
   — учти это при интеграции). Не ставь значение выше `min(4, cpu_count)` без
   отдельного явного согласования — риск повторения краха растёт с числом
   потоков.
6. Добавь в `SettingsPage` (`ui/widgets/settings_page.py`), рядом с уже
   существующей группой "Диагностика системы" (`_cuda_toggle`, кнопка "Проверить
   GPU"), новый `QSpinBox` для `cpu_inference_threads` (диапазон `0-32`, суффикс
   `"потоков (0=авто)"`) с tooltip, явно предупреждающим:
   > "Экспериментально. Если приложение начинает падать или вести себя нестабильно
   > после изменения — верните значение в 1 и перезапустите."
7. **Длительное тестирование (обязательно, не пропускать):**
   - ≥30 минут непрерывной обработки реального видео (≥5000 кадров) на
     Windows-машине без GPU, с `cpu_inference_threads` = авто.
   - Тот же прогон с `cpu_inference_threads = 1` (эквивалент старого поведения) —
     как контроль/откат.
   - Мониторинг: отсутствие крашей, отсутствие роста потребления памяти сверх
     ожидаемого, стабильный FPS без деградации со временем.
   - Если хотя бы один прогон завершился крашем `0xC0000409` (или похожим) —
     **откатывай `OMP_NUM_THREADS`-часть немедленно**, оставляй только
     "безопасную" часть (шаг 3-4, только `torch.set_num_threads`), и явно
     задокументируй это ограничение в отчёте.

### Критерии приёмки
- FPS на CPU-only машине заметно выше, чем в baseline из БЛОКА 0 (профилировщик
  показывает сокращение времени в стадиях, связанных с матричным инференсом).
- Никаких новых крашей за 30+ минут стабильной работы.
- При `cpu_inference_threads=1` (или `use_cuda`/GPU-путь) поведение и
  производительность **идентичны текущим** — regression-safe fallback.
- Изменение задокументировано с явным указанием: было ли безопасно поднимать
  `OMP_NUM_THREADS`, или пришлось откатить и оставить только
  `torch.set_num_threads`.

---

## БЛОК 6 — Диагностика и исправление привязки `processing_mode` / корректности Process Pool

### Проблема (требует подтверждения на старте блока, изложено с высокой, но не
### 100% уверенностью, т.к. `main.py` не был доступен при анализе)

1. `ProcessingController.start()` (`processing/processing_controller.py`)
   ветвится по **`configs.config.PROCESSING_MODE`** (модульная глобальная
   переменная, дефолт `"single_thread"`, определена в `configs/config.py`):
   ```python
   if config.PROCESSING_MODE == "process_pool":
       self._start_process_pool()
   elif config.PROCESSING_MODE == "single_thread":
       self._start_detector()
   else:
       self._start_detector()
   ```
   При этом выбор пользователя в UI (`SettingsPage._processing_mode_combo`)
   сохраняется в **`AppSettings.processing_mode`** (через `QSettings`) и
   используется **только** внутри `DetectorThread.run()`:
   ```python
   self._use_pipeline = settings.processing_mode == "pipeline"
   ```
   В предоставленных файлах **не найдено кода**, который синхронизирует
   `config.PROCESSING_MODE = settings.processing_mode` перед стартом обработки.
   Если такой синхронизации действительно нет нигде (в т.ч. в `main.py`) —
   выбор "Pipeline" или "Process Pool" в Settings **никогда не переключает**
   реальный маршрут в `ProcessingController`, и всегда используется
   `_start_detector()` (single_thread путь), внутри которого
   `settings.processing_mode` уже используется корректно только для
   pipeline-ветки OCR.

2. Даже если синхронизация есть и `_start_process_pool()` вызывается,
   `ProcessingController._on_process_pool_frame()` явно содержит:
   ```python
   def _on_process_pool_frame(self, processed_frame):
       # TODO: Интегрировать SignHandler здесь
       # Пока просто пробрасываем как есть
       self.frame_ready.emit(processed_frame)
   ```
   То есть детекции из `DetectorProcessPool` **никогда не попадают** в
   `SignHandler` → не создаются `TrackedSign` → `get_result_signs()` вернёт
   пустой список → **`FinalHandler` сохранит пустой GeoJSON**, даже если видео
   реально содержало знаки. UI при этом покажет "обработка идёт" и кадры с
   рамками (`frame_ready`), создавая ложное впечатление, что всё работает.

3. Отдельно: `AppSettings.process_pool_workers` (настраивается в UI, `0=авто`)
   **нигде не передаётся** в `DetectorProcessPool.__init__` — количество
   воркеров там определяется независимой эвристикой
   `_detect_optimal_workers()`, читающей `config.N_WORKERS`, который нигде не
   устанавливается из `settings.process_pool_workers`.

### Что сделать
1. **Диагностика (обязательный первый шаг):** прочитай `main.py` и весь путь
   от старта приложения до `ProcessingController.start()` (в т.ч.
   `MainWindow._on_start()`/`_on_multiple()`), явно ответь в отчёте на вопрос:
   "Синхронизируется ли `config.PROCESSING_MODE` из `AppSettings.processing_mode`
   где-либо?" Приведи конкретную строку/файл, если да; если нет — это
   подтверждённый баг.
2. Если синхронизации нет — добавь её в `ProcessingController._reset_config()`
   (вызывается в начале `start()`):
   ```python
   def _reset_config(self) -> None:
       from configs.settings import get_app_settings
       settings = get_app_settings()
       config.PROCESSING_MODE = settings.processing_mode
       ...
   ```
3. Реши судьбу `process_pool`-режима одним из двух способов — выбери по
   объёму работы, который реально можешь выполнить в рамках задачи:

   **(a) Полная интеграция (предпочтительно, если позволяет время):**
   Заверши `_on_process_pool_frame()`: пересобери `SignHandler`/`Turn` внутри
   `ProcessingController` (аналогично тому, как это уже сделано в
   `DetectorPool._aggregator_loop()` в `processing/detector_pool.py`, где есть
   рабочий пример — `_build_detected_signs()`, вызов
   `self._sign_handler.check_the_data_to_add(...)`, обновление
   `config.INDEX_OF_*`). Прокинь `settings.process_pool_workers` в
   `DetectorProcessPool.__init__`, убери зависимость от `config.N_WORKERS`.
   После интеграции сделай полный regression-тест (см. критерии приёмки).

   **(b) Safe-guard без полной интеграции (минимум, обязательно если (a) не
   успеваешь):** заблокируй выбор "Process Pool" в `SettingsPage`, когда
   `torch.cuda.is_available() == False` — задизейбль
   `self._processing_mode_combo` пункт "Process Pool" (или серым цветом +
   tooltip: "Экспериментально, на данный момент не сохраняет знаки — не
   выбирайте без GPU"), либо, если пользователь всё же его выбрал, в
   `ProcessingController.start()` добавь явную проверку и лог-предупреждение
   + фолбэк на `pipeline`/`single_thread`, чтобы никогда не завершать
   обработку молча с пустым результатом.
4. В любом случае — исправь БЛОК 6.1 (синхронизация `config.PROCESSING_MODE`),
   это правится независимо от выбора (a)/(b) и само по себе является багом.

### Критерии приёмки
- Явный ответ в отчёте: была ли синхронизация `PROCESSING_MODE`, и исправлена ли.
- Если выбран путь (a): обработка одного и того же тестового видео в
  `single_thread` и в `process_pool` даёт **идентичный** (или объяснимо
  минимально отличающийся, например из-за иного порядка обработки при
  многопроцессности) набор знаков в GeoJSON — не пустой список.
- Если выбран путь (b): пользователь физически не может выбрать
  "Process Pool" на машине без GPU (или получает явное недвусмысленное
  предупреждение до старта обработки), и режим больше не может привести к
  "тихой" потере всех результатов.
- `settings.process_pool_workers` реально влияет на число процессов, если
  режим используется.

---

## БЛОК 7 (опционально, наибольший потенциальный выигрыш) — ONNX/OpenVINO backend для YOLO на CPU

**Помечай этот блок как отдельную итерацию/эпик, не делай впопыхах вместе с
остальными — он меняет способ загрузки моделей и требует отдельного,
тщательного regression-тестирования.**

### Идея
`ultralytics.YOLO` при инференсе на CPU через нативный PyTorch заметно медленнее,
чем через:
- **ONNX Runtime** (`model.export(format="onnx")`, затем `YOLO("model.onnx")`) —
  обычно 1.5-2.5x на CPU за счёт оптимизированного графа и лучшего использования
  векторных инструкций;
- **OpenVINO IR** (`model.export(format="openvino")`, `YOLO("model_openvino_model/")`)
  — на процессорах Intel часто ещё быстрее (2-4x), OpenVINO специально
  оптимизирован под инференс на CPU Intel.

### Что сделать
1. Добавь `AppSettings.cpu_backend: Literal["pytorch", "onnx", "openvino"] = "pytorch"`.
2. Добавь скрипт `scripts/export_models_for_cpu.py`, который для каждой модели в
   `configs/sign_models.py` (`model_side_detect`, `rube_modal`, все модели в
   `model_dict`, `sub_models`, `model_lane_detect`, `model_lane_segment`)
   выполняет `YOLO(path).export(format=<backend>, imgsz=..., dynamic=False)` и
   сохраняет рядом с оригинальным `.pt` (например,
   `CNN_side/best.onnx` / `CNN_side/best_openvino_model/`).
3. В `configs/sign_models.py::_LazyModel._load()` добавь логику выбора файла в
   зависимости от `settings.cpu_backend` (только когда `_resolve_device() ==
   "cpu"` — GPU-путь всегда остаётся на `.pt` + CUDA, т.к. ONNX/OpenVINO на CPU
   быстрее, а на GPU обычно нет смысла менять):
   ```python
   def _load(self):
       if self._model is None:
           from configs.settings import get_app_settings
           settings = get_app_settings()
           self._device = _resolve_device()
           path = self._path_fn()
           if self._device == "cpu" and settings.cpu_backend != "pytorch":
               exported = _resolve_exported_path(path, settings.cpu_backend)
               if exported is not None:
                   path = exported
               else:
                   logger.warning(f"Экспортированная модель для {path} не найдена, "
                                   f"используется PyTorch .pt (запустите "
                                   f"scripts/export_models_for_cpu.py)")
           from ultralytics import YOLO
           self._model = YOLO(path)
           if self._device != "cpu":
               self._model.to(self._device)
   ```
4. Добавь селектор backend'а в Settings UI рядом с `_cuda_toggle`, доступный
   только когда CUDA недоступна (или всегда, но с пометкой "актуально для CPU").
5. **Регрессионное тестирование обязательно и особенно строгое**: экспорт в
   ONNX/OpenVINO может незначительно менять числовую точность (иное
   квантование/округление операций) — допустимы **только минимальные** различия
   в bbox-координатах (единицы пикселей) и confidence (сотые доли), но
   **классификационный результат** (`yolo_class`, `cnn_class`) должен совпадать
   с `.pt`-baseline на тестовом наборе кадров как минимум в 98%+ случаев.
   Прогони `test_detector_regression.py --compare` с ослабленным (но
   зафиксированным и обоснованным) порогом сравнения именно для этого блока.

### Критерии приёмки
- FPS на CPU-only машине заметно выше (замер через `benchmark_detector.py`),
  ожидаемо 1.5-3x в зависимости от backend'а и CPU.
- Точность классификации на регрессионном наборе не хуже 98% совпадений с
  PyTorch-baseline.
- Fallback на `.pt`, если экспортированной модели нет на диске (не должно быть
  жёсткого краха, если пользователь не запускал экспорт-скрипт).
- GPU-путь (`use_cuda=True` + доступная CUDA) полностью не затронут.

---

## БЛОК 8 — Авто-профиль "CPU Performance Mode" + автодетект отсутствия GPU

### Идея
Сейчас пользователю без GPU нужно вручную знать и включить: `use_cuda=False`
(и так сработает автоматически по факту недоступности CUDA, но явно не выставлено),
`processing_mode="pipeline"`, `ocr_use_process_pool=True`,
`ocr_pool_workers=1`, а после БЛОКов 1-6 ещё и новые настройки (`fast_frame_skip`,
`preview_fps_limit`, `ocr_throttle_interval_frames`, `cpu_inference_threads`,
`cpu_backend`). Это слишком много ручной настройки для обычного пользователя.

### Что сделать
1. При первом запуске приложения (или по кнопке в Settings) — определи
   `gpu_available = torch.cuda.is_available()`.
2. Если `gpu_available == False` и пользователь **ещё не менял настройки
   вручную** (например, флаг `AppSettings._user_customized: bool = False`,
   выставляемый в `True` при любом ручном сохранении из UI) — примени
   рекомендованный набор дефолтов для CPU:
   ```python
   processing_mode = "pipeline"
   ocr_use_process_pool = True
   ocr_pool_workers = 1
   fast_frame_skip = True
   preview_fps_limit = 10.0
   ocr_throttle_interval_frames = 8
   ocr_max_calls_per_sign = 6
   cpu_inference_threads = 0  # авто
   ```
3. Добавь в `SettingsPage` кнопку "⚡ Оптимизировать для CPU" (рядом с
   "🔍 Проверить GPU"), которая применяет этот же набор дефолтов по явному
   запросу пользователя в любой момент (не только при первом запуске), с
   диалогом подтверждения, перечисляющим, что именно изменится.
4. Не переопределяй настройки, если GPU доступна — в этом случае поведение
   должно остаться прежним (GPU-ориентированные дефолты).

### Критерии приёмки
- На чистой установке без GPU приложение "из коробки" использует
  CPU-оптимизированные настройки без необходимости лезть в Settings.
- Explicit "Оптимизировать для CPU" кнопка работает по запросу и не трогает
  настройки, не относящиеся к CPU-оптимизации (пороги confidence,
  дедупликация и т.д. остаются как были).
- На машине с доступной GPU поведение приложения не меняется вообще.

---

## БЛОК 9 — Методология бенчмарков и регрессионного тестирования

Расширь существующие скрипты, чтобы результаты всех блоков были сравнимы и
воспроизводимы:

1. `scripts/benchmark_detector.py`:
   - добавь флаг `--force-cpu` (временно выставляет `settings.use_cuda = False`
     на время замера, независимо от реального железа — чтобы можно было
     сравнивать CPU-путь даже на машине с GPU, для быстрой итерации при
     разработке блоков);
   - добавь замер `end-to-end` через реальный `ProcessingController`/`main.py`
     сценарий (не только `Detector.detect()` в изоляции), чтобы учитывать
     эффект БЛОКов 1, 2, 4, 6 (декодирование, превью, OCR, режимы), которые
     `Detector.detect()` в изоляции не покрывает.
2. `scripts/test_detector_regression.py`: уже поддерживает `--save-baseline`/
   `--compare`; убедись, что baseline из БЛОКА 0 сохранён под понятным именем
   (`regression_baseline_pre_cpu_opt.json`) и переиспользуется во всех
   последующих блоках, а не перезаписывается.
3. Добавь новый скрипт `scripts/benchmark_end_to_end_cpu.py`, который:
   - принимает тестовое видео + GPX;
   - прогоняет полный `ProcessingController` цикл (start → дождаться finished);
   - замеряет: общее время, средний FPS, итоговое число знаков в GeoJSON,
     пиковое потребление памяти (через `psutil`, если доступен, иначе
     пропустить с предупреждением);
   - сохраняет результат в JSON с меткой времени и git-коммитом (если доступен
     `git rev-parse HEAD`) для сравнения между итерациями блоков.
4. Каждый блок 1-8, который трогает производительность, должен приложить к
   своему отчёту таблицу "до/после" на основе этого скрипта.

---

## БЛОК 10 — Итоговая документация

По завершении всех выполненных блоков создай `CPU_OPT_SUMMARY.md` со
структурой, аналогичной существующим `BLOCK_H_QUICK_SUMMARY.md`/
`BLOCK_H_COMPLETION.md`:

1. Таблица блоков: статус (✅/⚠️/❌), затраченное время, эффект (FPS до/после
   на эталонном видео), риск, что осталось TODO.
2. Итоговая сравнительная таблица FPS/времени полной обработки эталонного
   видео: baseline (БЛОК 0) → после каждого применённого блока → финальный
   результат.
3. Список настроек, добавленных в `AppSettings`, с дефолтами и кратким
   описанием (пригодится для `settings_page.py` UI-текстов и для
   экспорта/импорта настроек, который уже поддерживает `to_dict()`/`from_dict()`
   — проверь, что новые поля туда автоматически подхватываются, так как
   `to_dict()` использует `asdict(self)` по всем полям dataclass — новые поля
   должны попасть туда без дополнительных правок).
4. Явный список того, что **не было сделано** и почему (например, если БЛОК 7
   не успел, или БЛОК 6 сделан только как safe-guard (b), а не полная
   интеграция (a)) — с рекомендацией по приоритету для следующей итерации.
5. Инструкция для пользователя: "Как получить максимальную производительность
   на компьютере без GPU" — 3-5 практических шагов (нажать "Оптимизировать для
   CPU", при необходимости прогнать `scripts/export_models_for_cpu.py` и
   переключить backend, и т.д.).

---

## Приложение А — Быстрая шпаргалка по файлам

| Область | Файлы |
|---|---|
| Чтение видео / декодирование | `processing/video_reader.py` |
| Основной цикл детекции (single/pipeline) | `processing/detector_thread.py` |
| Устаревший QThread-пул (для справки, не основной путь) | `processing/detector_pool.py` |
| ProcessPoolExecutor-пул (незавершённая интеграция) | `processing/detector_process_pool.py` |
| Оркестрация обработки | `processing/processing_controller.py` |
| Детектор (YOLO/CNN, батчинг, кэш) | `core/detector.py` |
| Трекинг знаков между кадрами | `core/sign_handler.py`, `core/sign.py` |
| OCR (синхронный + пулы) | `processing/ocr_worker.py`, `processing/ocr_pool.py`, `core/detector.py::_read_text/_ocr*` |
| Ленивая загрузка моделей / device resolution | `configs/sign_models.py` |
| Настройки приложения | `configs/settings.py`, `ui/widgets/settings_page.py` |
| Глобальное состояние обработки | `configs/config.py` |
| Бенчмарки / регрессия | `scripts/benchmark_detector.py`, `scripts/test_detector_regression.py` |
| Профилировщик | `core/profiler.py` |

## Приложение Б — Чего категорически не делать в рамках этой задачи

- Не переписывай архитектуру трекинга (`SignHandler`, `Turn`, bearing-geometry
  из BLOCK H) — она не является узким местом для CPU и уже стабилизирована.
- Не меняй пороги confidence (`conf_side`, `conf_rube`, `conf_cnn`) как способ
  "ускорить" обработку — это меняет точность, а не производительность, и не
  входит в задачу.
- Не удаляй legacy-код без явного запроса в конкретном блоке (например,
  `_process_turn_signs_legacy`, `DetectorPool` в `detector_pool.py`) — они
  либо используются как fallback, либо решение об их удалении требует
  отдельного согласования вне рамок этой задачи.
- Не меняй формат/содержимое GeoJSON-полей.
- Не трогай `core/osm_snap.py`/`core/intersection_geometry.py` — это
  сетевая/геометрическая логика, не связанная с CPU-инференсом.
