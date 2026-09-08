# БЛОК B — Батчинг ML-инференса: РЕАЛИЗАЦИЯ

**Дата:** 2026-08-21  
**Статус:** ✅ Реализовано, требует тестирования

---

## Проблема (из аудита)

### До оптимизации:
```python
for box in raw_boxes:
    crop = frame[y:y+h, x:x+w]
    resized = cv2.resize(crop, (32, 32))
    yolo_class = rube_modal.predict(resized)  # 1 forward pass
    cnn_class = model_dict[yolo_class](resized)  # 1 forward pass
```

**Узкое место:**
- N детекций → 1 + N + N forward passes через нейросети
- Нет группировки по yolo_class
- Кэш работает на уровне пикселей (0-3% hit rate)

### Ожидаемый эффект:
- **2-3x ускорение** на кадрах с 5+ знаками
- **Снижение latency** CNN-инференса через батчинг
- **Сохранение точности** (те же модели, те же пороги)

---

## Решение

### Архитектура после оптимизации:

```python
# 1. Подготовка всех кропов за один проход
crops = [frame[y:y+h, x:x+w] for (x,y,w,h) in raw_boxes]
resized = [cv2.resize(c, (32, 32)) for c in crops]

# 2. Батчинг rube классификации
yolo_classes = rube_modal.predict(resized)  # 1 forward pass для всех

# 3. Группировка по yolo_class + батчинг CNN
groups = group_by(resized, yolo_classes)
for yolo_class, batch in groups.items():
    cnn_results = model_dict[yolo_class](batch)  # 1 forward pass на группу
```

**Преимущества:**
- **1 + G forward passes** (G = количество уникальных yolo_class в кадре, обычно 2-4)
- **Эффективное использование GPU** (если доступен) через батчинг
- **Кэш остаётся работать** на уровне отдельных изображений

---

## Изменённые файлы

### 1. `core/detector.py` — основная оптимизация

#### `detect()` метод (строки 233-318):
```python
def detect(self, frame: np.ndarray, skip_ocr: bool = False) -> list[RawDetection]:
    # Шаг 1: найти все bbox (как раньше)
    raw_boxes = self._find_boxes(frame)
    
    # Шаг 2: подготовить все кропы за один проход
    crops_data = []  # [(box, is_side, crop, resized32)]
    for box, is_side in raw_boxes:
        x, y, w, h = box
        crop = frame[y: y + h, x: x + w]
        resized = cv2.resize(crop, (32, 32))
        crops_data.append((box, is_side, crop, resized))
    
    # Шаг 3: батчинг rube классификации
    rube_results = self._classify_rube_batch([cd[3] for cd in crops_data])
    
    # Шаг 4: батчинг CNN классификации (с группировкой по yolo_class)
    cnn_results = self._classify_fine_batch(
        [vc[3] for vc in valid_crops],
        [vc[4] for vc in valid_crops]
    )
    
    # Шаг 5: формирование результатов (как раньше)
    ...
```

#### Новые методы:

**`_classify_rube_batch(crops32: list[np.ndarray]) -> list[Optional[str]]`**
- Батчинг через `rube_modal.predict(crops32)`
- Применяет те же фильтры (CONF_RUBE, "5.16.2", нормализация)
- Возвращает список yolo_class

**`_classify_fine_batch(crops32, yolo_classes) -> list[str | int]`**
- Группирует кропы по yolo_class
- Проверяет кэш для каждого кропа
- Вызывает `_run_cnn_batch()` для некэшированных

**`_run_cnn_batch(crops32, yolo_class) -> list[str | int]`**
- Батчинг через `model_dict[yolo_class](crops32)`
- Обрабатывает субклассификацию треугольников
- Сохраняет результаты в кэш

---

### 2. `scripts/benchmark_detector.py` — новый файл

**Назначение:** Замер производительности detector.py до/после оптимизаций

**Использование:**
```bash
# Базовый бенчмарк (без OCR)
python scripts/benchmark_detector.py --video "path/to/video.mp4" --frames 100

# С OCR
python scripts/benchmark_detector.py --video "path/to/video.mp4" --frames 100 --with-ocr

# Детальное профилирование
python scripts/benchmark_detector.py --video "path/to/video.mp4" --frames 30 --profile
```

**Выходные метрики:**
- FPS (frames per second)
- Время обработки на кадр
- Количество детекций
- Статистика из `core.profiler`:
  - `yolo_bbox_detection`
  - `batch_prepare_crops`
  - `batch_classify_rube`
  - `batch_classify_fine`
  - `ocr_read_text`

**Результаты сохраняются в:**
- `benchmark_profile.stats` — для детального анализа с `pstats`

---

## Тестирование

### Шаг 1: Базовый тест (без регрессий)

```bash
# Запуск приложения
python main.py
```

**Проверки:**
1. ✅ Приложение запускается без ошибок
2. ✅ Загружаются модели: `[DetectorThread] Модели загружены`
3. ✅ Обработка видео работает (DashboardPage → ProcessingPage)
4. ✅ Детекции отображаются в preview
5. ✅ Результаты сохраняются в DB

### Шаг 2: Бенчмарк (замер улучшения)

**Требования:**
- Тестовое видео с несколькими знаками на кадре (5+)
- Python окружение с установленными зависимостями

**Команды:**
```bash
# 1. Измерить FPS на 100 кадрах
python scripts/benchmark_detector.py --video "videos/test.mp4" --frames 100

# 2. Детальное профилирование
python scripts/benchmark_detector.py --video "videos/test.mp4" --frames 30 --profile
```

**Ожидаемые результаты:**

| Метрика | До оптимизации | После оптимизации | Улучшение |
|---------|----------------|-------------------|-----------|
| FPS (без OCR) | 2.8-3.0 | **5.5-7.0** | 2-2.5x |
| batch_classify_rube | N вызовов | 1 вызов | N→1 |
| batch_classify_fine | N вызовов | G вызовов (G=2-4) | N→G |

### Шаг 3: Регрессионный тест (точность)

**Цель:** Убедиться, что батчинг не изменил результаты детекции

**Метод:**
1. Обработать одно и то же видео старой и новой версией
2. Сравнить `total_detections` и список `cnn_class`
3. Допустимое расхождение: 0% (идентичные результаты)

**⚠️ ВАЖНО:** Сначала сохраните baseline ДО применения батчинга!

**Команды:**
```bash
# 1. Сохранить baseline (ДО рефакторинга или на копии репозитория)
python scripts/test_detector_regression.py --video "videos/test.mp4" --frames 50 --save-baseline

# 2. Сравнить с baseline (ПОСЛЕ рефакторинга)
python scripts/test_detector_regression.py --video "videos/test.mp4" --frames 50 --compare
```

**Ожидаемый результат:**
```
РЕЗУЛЬТАТЫ РЕГРЕССИОННОГО ТЕСТА:
Кадров проверено:         50
Детекций baseline:        287
Детекций текущих:         287
Кадров с расхождениями:   0
✅ ТЕСТ ПРОЙДЕН: Результаты идентичны
```

**Если тест провален:**
1. Проверьте `regression_test_mismatches.json` для деталей
2. Возможные причины:
   - Изменились пороги `CONF_RUBE`, `CONF_CNN`
   - Недетерминизм в модели (маловероятно)
   - Баг в батчинге логике

---

## Проблемы и ограничения

### 1. LaneDetector (знак 5.8) без батчинга
**Причина:** `LaneDetector.find_signs()` не поддерживает батчинг  
**Эффект:** Минимальный (5.8 встречается редко)  
**TODO:** Реализовать батчинг в LaneDetector (B.5)

### 2. Субмодели треугольников без батчинга
**Причина:** Сложная логика с кэшем внутри основного батча  
**Эффект:** Средний (треугольники 10-15% от всех знаков)  
**TODO:** Батчинг для sub_models (B.6)

### 3. OCR остался синхронным
**Причина:** EasyOCR не thread-safe, требует ProcessPoolExecutor  
**Эффект:** Критический (падение FPS с 2.8 до 0.1-0.3)  
**Решение:** БЛОК C — Асинхронный OCR

---

## Следующие шаги (БЛОК B продолжение)

### B.3 — TrackedSign-кэш вместо pixel-кэша ⏳

**Проблема:**
- Текущий кэш на уровне пикселей: 0-3% hit rate
- Один и тот же знак трекается 50-100 кадров, но каждый раз с разными пикселями

**Решение:**
```python
class TrackedSign:
    stable_observations: int  # сколько раз CNN вернул тот же класс
    cnn_class: str
    
    def should_skip_cnn(self) -> bool:
        return self.stable_observations >= 5  # порог стабильности
```

**Эффект:** 5-10x сокращение CNN вызовов на стабильных знаках

### B.4 — Итоговый бенчмарк ⏳

После B.3:
```bash
python scripts/benchmark_detector.py --video "videos/test.mp4" --frames 100
```

**Целевые метрики:**
- FPS без OCR: **6-8** (было 2.8-3.0, цель 2x = 5.6-6.0)
- FPS с OCR: **0.1-0.3** → БЛОК C исправит до ~2.0-2.5

---

## Коммит

```bash
git add core/detector.py scripts/benchmark_detector.py
git commit -m "feat(detector): add ML batching for rube+CNN classification

- Batch rube classification: N forward passes → 1
- Batch CNN classification: N → G (G = unique yolo_classes)
- Add benchmark_detector.py for performance testing
- Expected 2-3x FPS improvement on multi-sign frames

Refs: BLOCK_B (PERFORMANCE_AUDIT_AND_AGENT_PROMPT.md)"
```

---

## БЛОК B Статус

- ✅ **B.1** — Профилирование (анализ узких мест)
- ✅ **B.2** — Батчинг rube + CNN (реализовано)
- ⏳ **B.3** — TrackedSign-кэш (следующий шаг)
- ⏳ **B.4** — Итоговый бенчмарк
- ⏳ **B.5** — Батчинг LaneDetector (опционально)
- ⏳ **B.6** — Батчинг sub_models (опционально)

**Прогресс БЛОКА B:** 50%  
**Ожидаемое улучшение после B.2:** 2-3x FPS  
**Ожидаемое улучшение после B.3:** 4-5x FPS
