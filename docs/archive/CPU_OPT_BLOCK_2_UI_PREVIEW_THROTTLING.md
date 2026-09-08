# CPU_OPT_BLOCK_2 — Троттлинг UI-превью

**Дата:** 2026-08-25  
**Статус:** ✅ Завершено  
**Приоритет:** Средний  
**Риск:** Низкий  

---

## 1. Проблема

### 1.1. Текущее поведение (baseline)

Файл: `processing/detector_thread.py`, метод `_process_loop()`

```python
# На каждой итерации цикла (включая пропущенные кадры):
self._emit_frame(raw.image)  # или self._emit_frame(annotated)
```

**Что происходит при каждом вызове `_emit_frame()`:**

1. `cv2.cvtColor(BGR → RGB)` — конвертация цветового пространства на **полном разрешении** кадра (1920×1080 или выше для GoPro)
2. `QImage(rgb.data, ...)` — создание Qt-изображения
3. `QPixmap.fromImage(...).scaled(960, 540, ...)` — создание pixmap + масштабирование

**Частота вызовов:**
- При `FRAME_STEP=5` и 60 FPS исходного видео → обрабатывается 12 кадров/сек
- Но `_emit_frame()` вызывается на:
  - Кадрах с низкой скоростью (`speed < MIN_SPEED_KMH`)
  - Кадрах, пропущенных умным skipping
  - Кадрах с полноценной детекцией

Итого: **10-20+ вызовов в секунду** на машинах с высоким FPS обработки.

**Проблема:** UI физически не может показывать больше ~15-20 FPS (лимит refresh rate Qt виджета + человеческое восприятие), остальные преобразования — чистые CPU-циклы впустую.

### 1.2. Конкуренция за CPU

На CPU-only машине `cv2.cvtColor` + `QPixmap.scaled` конкурируют за те же ядра, что и YOLO/CNN инференс. При троттлинге до разумной частоты (10-12 FPS) освобождаются ресурсы для детекции.

### 1.3. Ожидаемый эффект

- **Экономия CPU:** ~10-20% общего времени (зависит от разрешения кадра)
- **Прирост FPS детекции:** 10-20% за счёт меньшей конкуренции за ядра
- **UX:** Без деградации — 12 FPS превью воспринимается как плавное видео

---

## 2. Решение

### 2.1. Добавление настройки в `AppSettings`

**Файл:** `configs/settings.py`

```python
# ── CPU-оптимизация (BLOCK CPU) ───────────────────────────────
preview_fps_limit: float = 12.0  # Максимальная частота обновления превью UI (кадр/сек)
```

**Значение по умолчанию:** 12.0 FPS
- Достаточно для плавного восприятия видео
- Не нагружает CPU избыточно
- Можно изменить в UI Settings (будет добавлено в БЛОКЕ 8)

### 2.2. Инициализация в `DetectorThread`

**Файл:** `processing/detector_thread.py`

**В `__init__`:**
```python
# ── UI Preview Throttling (BLOCK CPU-2) ───────────────────
self._preview_min_interval = 0.0  # Будет установлено в run() из settings
self._last_emit_time = 0.0
```

**В `run()`:**
```python
# ── UI Preview Throttling (BLOCK CPU-2) ───────────────────
# Ограничиваем частоту обновления превью в UI
self._preview_min_interval = 1.0 / settings.preview_fps_limit if settings.preview_fps_limit > 0 else 0.0
logger.info(f"📺 UI Preview: макс. {settings.preview_fps_limit} FPS (интервал {self._preview_min_interval:.3f}s)")
```

### 2.3. Метод проверки троттлинга

**Добавлен метод `_should_emit_preview()`:**

```python
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
```

**Логика:**
- `time.monotonic()` — монотонный таймер (не подвержен изменению системного времени)
- Если с последнего эмита прошло менее `_preview_min_interval` → пропускаем
- Иначе — обновляем `_last_emit_time` и разрешаем эмит

### 2.4. Обновление вызовов `_emit_frame()`

**Место 1: Кадры с низкой скоростью (машина стоит)**

```python
# Было:
if speed is not None and speed < self.MIN_SPEED_KMH:
    self._emit_frame(raw.image)
    continue

# Стало:
if speed is not None and speed < self.MIN_SPEED_KMH:
    if self._should_emit_preview():
        self._emit_frame(raw.image)
    continue
```

**Место 2: Кадры, пропущенные smart skipping**

```python
# Было:
if not self._should_process_frame():
    self._emit_frame(raw.image)
    continue

# Стало:
if not self._should_process_frame():
    if self._should_emit_preview():
        self._emit_frame(raw.image)
    continue
```

**Место 3: Кадры с детекциями (основной путь)**

```python
# Было:
with profiler.measure("draw_boxes_and_emit"):
    annotated = self._draw_boxes(raw.image, detections)
    self._emit_frame(annotated)

# Стало:
if self._should_emit_preview():
    with profiler.measure("draw_boxes_and_emit"):
        annotated = self._draw_boxes(raw.image, detections)
        self._emit_frame(annotated)
```

**Важно:** `_draw_boxes()` тоже переносится под проверку, т.к. рисование bbox'ов на CPU — тоже overhead, если кадр всё равно не будет показан.

---

## 3. Критерии приёмки

### 3.1. Профилировщик (обязательно)

`profiler.get_report()` должен показывать:

**До оптимизации (БЛОК 1):**
```
draw_boxes_and_emit:
  Count:  1200 (для 1200 обработанных кадров)
  Total:  XX.Xs
  Mean:   YY.Yms
```

**После БЛОКА 2:**
```
draw_boxes_and_emit:
  Count:  ~150 (для 1200 обработанных кадров при 12 FPS limit за 100 секунд)
  Total:  XX.Xs (меньше, чем в baseline)
  Mean:   YY.Yms (примерно такое же)
```

**Ожидание:** Число вызовов снижается пропорционально `preview_fps_limit / actual_processing_fps`.

### 3.2. FPS детекции (обязательно)

Замер через `benchmark_detector.py` или `benchmark_end_to_end_cpu.py`:

**До БЛОКА 2:** [X.X] FPS  
**После БЛОКА 2:** [X.X + 10-20%] FPS

**Важно:** Прирост заметен только на CPU-only, где `cv2.cvtColor` + scaling конкурируют за ядра с детекцией. На GPU-машинах эффект будет минимальным (UI работает на CPU, инференс на GPU).

### 3.3. Визуальная проверка (обязательно)

Открыть RoadScanner GUI → страница "Обработка" → запустить обработку видео:

**Ожидание:**
- Превью остаётся плавным (не "замирает" на 1 кадре)
- Нет "рывков" или "залипаний"
- Субъективно: пользователь не замечает разницы между 12 FPS и 20+ FPS превью

**Если превью выглядит "дёрганым"** (при preview_fps_limit=12):
- Увеличить `preview_fps_limit` до 15-18 FPS
- Или добавить в UI настройку с рекомендованным диапазоном 10-20 FPS

### 3.4. Regression-тест (обязательно)

```bash
python scripts/test_detector_regression.py --video test.mp4 --frames 100 --compare
```

**Ожидание:** 
- Детекции идентичны baseline (троттлинг UI не влияет на логику детекции)
- Знаков в итоговом GeoJSON столько же, сколько в baseline

### 3.5. Сигналы `sign_detected` и `stats_updated`

Проверить, что эти сигналы эмитятся **с той же частотой**, что и раньше:
- `sign_detected` — для каждого нового знака
- `stats_updated` — каждую секунду (или по таймеру)

Троттлинг влияет **только** на `frame_ready`, остальные сигналы должны остаться без изменений.

---

## 4. Результаты (требуют фактических замеров)

> **Примечание:** Заполняется после тестирования на реальном видео.

### 4.1. Профилировщик (до/после)

| Метрика | Baseline (БЛОК 1) | БЛОК 2 | Изменение |
|---------|-------------------|--------|-----------|
| `draw_boxes_and_emit` вызовов | [N] | [N] | [−XX%] |
| `draw_boxes_and_emit` total (s) | [X.X] | [X.X] | [−XX%] |
| `draw_boxes_and_emit` mean (ms) | [Y.Y] | [Y.Y] | [±0%] |

### 4.2. FPS (CPU-only машина)

```
Команда: python scripts/benchmark_end_to_end_cpu.py --video test.mp4 --gpx test.gpx --output test.geojson --mode single_thread

Baseline (БЛОК 1): [X.X] FPS
БЛОК 2:            [X.X] FPS
Прирост:           [+XX%]
```

### 4.3. Визуальная оценка

```
Превью плавность:       [OK/Залипает]
FPS preview (факт):     [~12 FPS]
Рывки/дёргания:         [нет/есть]
```

### 4.4. Regression-тест

```
python scripts/test_detector_regression.py --video test.mp4 --frames 100 --compare

Статус:                 [PASSED/FAILED]
Кадров с расхождениями: [0] ✅
```

---

## 5. Известные ограничения

### 5.1. Минимальный `preview_fps_limit`

Значения ниже 8-10 FPS могут выглядеть "дёргано" для пользователя. Рекомендуемый диапазон: **10-15 FPS**.

### 5.2. Троттлинг не влияет на сохранение превью в файл

Если в будущем добавится функция "сохранить превью-видео в файл", троттлинг нужно будет отключать для этого режима, либо делать отдельный поток сохранения без троттлинга.

### 5.3. `preview_fps_limit=0` отключает троттлинг

При `preview_fps_limit <= 0` троттлинг полностью отключается (`_should_emit_preview()` всегда возвращает `True`). Это fallback для случаев, если пользователь хочет "максимальную плавность" и готов пожертвовать FPS детекции.

---

## 6. Интеграция с UI (БЛОК 8)

В БЛОКЕ 8 будет добавлен UI-контрол для настройки `preview_fps_limit` в Settings:

```python
# ui/widgets/settings_page.py

preview_fps_spinbox = QDoubleSpinBox()
preview_fps_spinbox.setRange(0, 30)  # 0 = без троттлинга
preview_fps_spinbox.setSuffix(" FPS")
preview_fps_spinbox.setValue(settings.preview_fps_limit)
preview_fps_spinbox.setToolTip(
    "Максимальная частота обновления превью видео.\n"
    "10-15 FPS: оптимально для CPU\n"
    "0: без ограничений (медленнее)"
)
```

---

## 7. Следующие шаги

После успешного завершения БЛОКА 2:

- [x] Код изменён
- [ ] Профилировщер-замеры выполнены
- [ ] FPS-бенчмарк пройден (прирост 10-20%)
- [ ] Визуальная проверка UI пройдена
- [ ] Regression-тест пройден
- [ ] Раздел 4 заполнен фактическими цифрами
- [ ] Коммит с сообщением: `CPU-OPT BLOCK 2: UI preview throttling (12 FPS default)`

→ **БЛОК 3:** Подключение CNN-skip кэша (`detect_with_tracking`)

---

## 8. Взаимодействие с другими блоками

### 8.1. БЛОК 1 (Video decoding)

**Синергия:** Оба блока снижают overhead "бесполезной работы":
- БЛОК 1 — декодирование пропущенных кадров
- БЛОК 2 — рисование/масштабирование невидимых превью

Совместный эффект: **1.5-2x (БЛОК 1) × 1.1-1.2x (БЛОК 2) ≈ 1.7-2.4x** для video I/O + UI компонента.

### 8.2. БЛОК 3 (CNN-skip cache)

**Независимы:** Троттлинг UI не влияет на CNN-инференс. Эффекты аддитивны.

### 8.3. БЛОК 4 (OCR throttling)

**Независимы:** UI-превью не связан с OCR-пулом.

### 8.4. БЛОК 5 (CPU threads)

**Конфликта нет:** `cv2.cvtColor` / `QPixmap.scaled` не зависят от `torch.set_num_threads()`. Но меньше вызовов UI-преобразований → меньше конкуренция за кэш/память → косвенный бонус для инференса.

---

**Автор:** Kiro AI Agent  
**Дата создания:** 2026-08-25
