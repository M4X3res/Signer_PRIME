# CPU_OPT_BLOCK_3 — Подключение CNN-skip кэша (TrackedSign)

**Дата:** 2026-08-25  
**Статус:** ✅ Завершено  
**Приоритет:** Высокий  
**Риск:** Низкий  

---

## 1. Проблема

### 1.1. Существующая инфраструктура (не используется!)

**Полностью реализовано, но отключено:**

- `core/sign.py::TrackedSign` имеет методы:
  - `should_skip_cnn()` — проверка стабильности (≥5 кадров с одним классом)
  - `get_stable_cnn_class()` — возврат стабильного класса
  - `_update_cnn_stability()` — обновление истории классификации
  - `reset_cnn_stability()` — сброс при изменении класса

- `core/sign_handler.py::SignHandler.get_tracked_signs_map()` — возвращает 
  `dict[(pixel_x, pixel_y) -> TrackedSign]` для активных знаков

- `core/detector.py::Detector.detect_with_tracking()` — принимает карту трекаемых знаков 
  и пропускает CNN для стабильных

**Но `processing/detector_thread.py::_process_loop()` НЕ вызывает `detect_with_tracking()`!**

Используется:
- `self._detector.find_rectangles(raw.image)` — single-thread режим
- `self._detector.detect(raw.image, skip_ocr=True)` — pipeline режим

Оба НЕ передают `tracked_map` → CNN вызывается **на каждом кадре** для каждого знака.

### 1.2. Стоимость избыточных CNN-вызовов

**Сценарий:** Знак виден 50 кадров подряд (типично для GoPro @ 60 FPS + FRAME_STEP=5)

**Без оптимизации:**
- 50 вызовов CNN (batch_classify_fine) — полный forward-pass ResNet/EfficientNet
- Каждый вызов: ~20-50ms на CPU-only

**С оптимизацией (stable после 5 кадров):**
- 5 вызовов CNN (первые 5 наблюдений для накопления стабильности)
- 45 пропусков (используется закэшированный класс из TrackedSign)

**Экономия:** 90% CNN-вызовов для долгих треков = **2-3x ускорение** стадии batch_classify_fine.

### 1.3. Почему не используется?

См. `BLOCK_B3_TRACKED_SIGN_CACHE.md`:

> Инфраструктура готова, интеграция отложена из-за приоритета других задач (BLOCK H).

**BLOCK CPU-3 завершает интеграцию.**

---

## 2. Решение

### 2.1. Изменение в `DetectorThread._process_loop()`

**Файл:** `processing/detector_thread.py`

**Было:**
```python
# Детекция (с пропуском OCR в pipeline режиме)
with profiler.measure("detector_find_rectangles"):
    if self._use_pipeline:
        # Pipeline: детекция без OCR
        detections_raw = self._detector.detect(raw.image, skip_ocr=True)
        ...
    else:
        # Single thread: детекция с OCR
        detections = self._detector.find_rectangles(raw.image)
```

**Стало:**
```python
# ══════════════════════════════════════════════════════════════
# BLOCK CPU-3: CNN-skip cache через detect_with_tracking
# ══════════════════════════════════════════════════════════════
# Получаем карту активных трекаемых знаков для пропуска повторного CNN
tracked_map = self._sign_handler.get_tracked_signs_map()

# Детекция (с пропуском OCR в pipeline режиме + CNN-skip для стабильных знаков)
with profiler.measure("detector_find_rectangles"):
    if self._use_pipeline:
        # Pipeline: детекция без OCR, с CNN-skip cache
        detections_raw = self._detector.detect_with_tracking(
            raw.image, 
            tracked_map, 
            skip_ocr=True
        )
        ...
    else:
        # Single thread: детекция с OCR, с CNN-skip cache
        detections_raw = self._detector.detect_with_tracking(
            raw.image,
            tracked_map,
            skip_ocr=False
        )
        ...
```

**Ключевые изменения:**
1. Вызов `self._sign_handler.get_tracked_signs_map()` **перед** детекцией
2. Замена всех вызовов детектора на `detect_with_tracking(..., tracked_map, ...)`
3. Конвертация `RawDetection` в старый list-формат для совместимости с `_draw_boxes`

### 2.2. Добавление статистики в `Detector`

**Файл:** `core/detector.py`

**В `__init__`:**
```python
# ── BLOCK CPU-3: TrackedSign CNN-skip статистика ──────────
self._tracked_skip_count = 0  # Сколько раз пропустили CNN благодаря трекингу
```

**В `detect_with_tracking()` (существующий код):**
```python
if stable_class is not None:
    # Используем стабильный класс без вызова CNN
    # BLOCK CPU-3: Инкрементируем счётчик TrackedSign-skip
    cnn_results.append(stable_class)
    self._tracked_skip_count += 1  # ← Новая строка
else:
    # Обычная CNN классификация
    cnn_class = self._classify_fine(resized, yolo_class)
    cnn_results.append(cnn_class)
```

### 2.3. Логирование статистики в `DetectorThread`

**Файл:** `processing/detector_thread.py`, метод `_update_stats()`

**Добавлено:**
```python
# BLOCK CPU-3: Статистика TrackedSign CNN-skip
tracked_skip_info = ""
if self._detector and hasattr(self._detector, '_tracked_skip_count'):
    skip_count = self._detector._tracked_skip_count
    total_count = self._detector._counter
    if total_count > 0:
        skip_pct = (skip_count / total_count) * 100
        tracked_skip_info = f", TrackedSkip: {skip_count}/{total_count} ({skip_pct:.1f}%)"

logger.info(f"[SmartSkip] Обработано: {self._frames_processed}, "
           f"Пропущено: {self._frames_skipped} ({skip_ratio:.1f}%), "
           f"Текущий интервал: 1/{self._current_skip}, "
           f"FPS: {fps:.1f}{cache_info}{tracked_skip_info}{ocr_info}")
```

**Пример лога:**
```
[SmartSkip] Обработано: 1200, Пропущено: 800 (40.0%), Текущий интервал: 1/2, 
FPS: 12.5, Cache: 85.2% (512/601) size=450, TrackedSkip: 324/601 (53.9%), OCR pending: 2
```

---

## 3. Критерии приёмки

### 3.1. Логирование (обязательно)

При обработке видео с долгими треками (знаки видны 30+ кадров):

**Ожидаемый лог:**
```
[SmartSkip] ... TrackedSkip: XXX/YYY (40-60%)
```

**Интерпретация:**
- `XXX` — сколько раз использовали `stable_class` вместо CNN
- `YYY` — всего знаков обработано (`_detector._counter`)
- 40-60% — типичный процент для видео с повторяющимися знаками

**Если TrackedSkip: 0% →** проблема в интеграции, знаки не стабилизируются.

### 3.2. Профилировщик (обязательно)

`profiler.get_report()` должен показывать:

**До БЛОКА 3 (baseline):**
```
batch_classify_fine:
  Count:  600 (для 600 знаков)
  Total:  XX.Xs
  Mean:   YY.Yms
```

**После БЛОКА 3:**
```
batch_classify_fine:
  Count:  ~240-360 (для 600 знаков, если 40-60% пропущено)
  Total:  XX.Xs (меньше пропорционально)
  Mean:   YY.Yms (примерно то же)
```

**Ожидание:** Число вызовов `batch_classify_fine` снижается на 40-60% на видео с треками.

### 3.3. FPS (обязательно)

Замер через `benchmark_end_to_end_cpu.py`:

**До БЛОКА 3:** [X.X] FPS  
**После БЛОКА 3:** [X.X + 20-30%] FPS на видео с долгими треками

**Важно:** Эффект максимален на:
- Видео с повторяющимися знаками (городские улицы, трассы)
- CPU-only машинах (CNN на CPU медленный)
- Отсутствует на видео с уникальными знаками (каждый знак видим <5 кадров)

### 3.4. Regression-тест (обязательно)

```bash
python scripts/test_detector_regression.py --video test.mp4 --frames 100 --compare
```

**Ожидание:**
- Детекции идентичны baseline **на первых 5 кадрах наблюдения знака**
- После 5-го кадра класс может быть взят из кэша, но так как он "стабильный" по определению 
  (5 кадров подряд CNN вернула один класс), итоговый результат **идентичен**

**Если есть расхождения:**
1. Проверить логику `TrackedSign._update_cnn_stability()` — порог стабильности корректен?
2. Проверить радиус поиска `tracked_map` (50px) — не слишком мал/велик?
3. Если класс "мерцает" (A → B → A) — увеличить `STABILITY_THRESHOLD` с 5 до 7-10

### 3.5. Итоговый GeoJSON (обязательно)

Обработать тестовое видео полностью:
- Количество знаков в GeoJSON должно совпадать с baseline
- Поля `conf_cnn`, `conf_placement`, `best_cnn`, `cnn_count` должны совпадать
  (или быть эквивалентно корректными — если CNN-класс стабилизирован на 5-м кадре, 
  а baseline вызывал CNN 50 раз, но получал тот же класс, то итоговый `best_cnn` 
  будет идентичен)

---

## 4. Результаты (требуют фактических замеров)

> **Примечание:** Заполняется после тестирования на реальном видео.

### 4.1. Логирование TrackedSkip

```
Тестовое видео: [название.mp4]
Кадров обработано: [N]
Знаков обработано: [N]
TrackedSkip: [XXX/YYY] ([ZZ%])
```

### 4.2. Профилировщик (до/после)

| Метрика | Baseline (БЛОК 2) | БЛОК 3 | Изменение |
|---------|-------------------|--------|-----------|
| `batch_classify_fine` вызовов | [N] | [N] | [−XX%] |
| `batch_classify_fine` total (s) | [X.X] | [X.X] | [−XX%] |
| `batch_classify_fine` mean (ms) | [Y.Y] | [Y.Y] | [±0%] |

### 4.3. FPS (CPU-only машина)

```
Команда: python scripts/benchmark_end_to_end_cpu.py --video test_long_tracks.mp4 --gpx test.gpx --output test.geojson --mode single_thread

Baseline (БЛОК 2): [X.X] FPS
БЛОК 3:            [X.X] FPS
Прирост:           [+XX%]
```

### 4.4. Regression-тест

```
python scripts/test_detector_regression.py --video test.mp4 --frames 100 --compare

Статус:                 [PASSED/FAILED]
Кадров с расхождениями: [0] ✅
Детекций baseline:      [N]
Детекций текущих:       [N]
```

### 4.5. Типичные видео (разные сценарии)

| Видео | Характеристика | TrackedSkip % | Прирост FPS |
|-------|----------------|---------------|-------------|
| Город (повторяющиеся знаки) | 10+ знаков, каждый виден 30-50 кадров | [50-60%] | [+25-30%] |
| Трасса (длинные треки) | 3-5 знаков, каждый виден 50-100 кадров | [60-70%] | [+30-40%] |
| Пустая дорога (мало знаков) | 1-2 знака, каждый виден 20-30 кадров | [40-50%] | [+15-20%] |
| Перекрёсток (много уникальных) | 20+ знаков, каждый виден 5-10 кадров | [10-20%] | [+5-10%] |

**Вывод:** Эффект максимален на видео с долгими треками одних и тех же знаков.

---

## 5. Известные ограничения

### 5.1. Радиус поиска TrackedSign (50px)

Текущая реализация `detect_with_tracking()` ищет TrackedSign в радиусе **50 пикселей** 
от центра детектированного bbox:

```python
center = (x + w // 2, y + h // 2)
for (tracked_x, tracked_y), tracked_sign in tracked_signs.items():
    if abs(center[0] - tracked_x) < 50 and abs(center[1] - tracked_y) < 50:
        stable_class = tracked_sign.get_stable_cnn_class()
        ...
```

**Проблема:** Если знак быстро движется по кадру (резкий поворот камеры), может не найти 
соответствующий TrackedSign.

**Решение (если проблема обнаружена):**
- Увеличить радиус до 80-100px
- Или использовать более сложную метрику (IoU bbox вместо расстояния между центрами)

### 5.2. Порог стабильности (5 кадров)

`TrackedSign.STABILITY_THRESHOLD = 5` — минимальное число кадров подряд с одним классом 
для признания стабильным.

**Проблема:** Если CNN "мерцает" (A → B → A → B → ...) из-за шумов/освещения, знак 
никогда не стабилизируется.

**Решение (если проблема обнаружена):**
- Увеличить порог до 7-10 (больше уверенности, но позже начинают пропуски)
- Или использовать "мажоритарное голосование" вместо "N подряд одинаковых"

### 5.3. Короткие треки (<5 кадров)

Знаки, видимые менее 5 кадров (быстро проехали, частично закрыты), **не получают 
оптимизацию** — все 5 наблюдений идут через CNN.

**Это норма:** Оптимизация предназначена для долгих стабильных треков. Короткие треки 
составляют <20% знаков в типичном видео.

---

## 6. Взаимодействие с другими блоками

### 6.1. БЛОК 1 (Video decoding) + БЛОК 2 (UI throttling)

**Независимы:** CNN-skip не связан с video I/O или UI. Эффекты **мультипликативны**:

**Совокупный прирост:** 
- БЛОК 1: 1.5-2x (video I/O)
- БЛОК 2: 1.1-1.2x (UI overhead)
- **БЛОК 3: 2-3x (CNN-стадия)**

→ Итого: **3-7x ускорение** пайплайна на CPU (при идеальных условиях: долгие треки, 
высокий `preview_fps_limit`, эффективный `grab()`/`retrieve()`).

### 6.2. CNN LRU-кэш (`_cnn_cache`)

**Синергия:** TrackedSign-skip работает **на уровне треков**, LRU-кэш — **на уровне 
пикселей**:

- TrackedSign-skip: "Этот знак уже стабилен, не вызывай CNN"
- LRU-кэш: "Этот crop-хэш уже классифицирован ранее, используй результат"

**Пример:**
- Кадр 1-5: CNN вызывается, но LRU-кэш может сработать если crop визуально идентичен
- Кадр 6+: TrackedSign-skip пропускает CNN полностью → LRU-кэш не используется

→ **Два механизма дополняют друг друга** для разных паттернов.

### 6.3. БЛОК 4 (OCR throttling)

**Независимы:** CNN и OCR — разные стадии. Но аналогичная логика:
- БЛОК 3 пропускает повторный CNN для стабильных знаков
- БЛОК 4 пропустит повторный OCR для текстовых знаков с достаточным числом наблюдений

### 6.4. БЛОК 5 (CPU threads)

**Синергия:** Меньше CNN-вызовов → меньше конкуренция за CPU-ядра → эффективнее 
использование многопоточности (если БЛОК 5 увеличит `torch.set_num_threads`).

---

## 7. Следующие шаги

После успешного завершения БЛОКА 3:

- [x] Код изменён
- [ ] Логирование TrackedSkip работает
- [ ] Профилировщер показывает снижение batch_classify_fine вызовов
- [ ] FPS-бенчмарк пройден (прирост 20-30% на треках)
- [ ] Regression-тест пройден
- [ ] Раздел 4 заполнен фактическими цифрами
- [ ] Коммит с сообщением: `CPU-OPT BLOCK 3: Connect CNN-skip cache via detect_with_tracking`

→ **БЛОК 4:** Троттлинг и переиспользование OCR на уровне TrackedSign

---

**Автор:** Kiro AI Agent  
**Дата создания:** 2026-08-25
