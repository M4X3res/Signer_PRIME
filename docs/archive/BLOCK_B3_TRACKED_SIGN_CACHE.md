# БЛОК B.3 — TrackedSign-кэш: ЧАСТИЧНАЯ РЕАЛИЗАЦИЯ

**Дата:** 2026-08-21  
**Статус:** ⚠️ Частично реализовано (инфраструктура готова, интеграция требует рефакторинга)

---

## Проблема

### Текущая ситуация:
- Один знак трекается **50-100 кадров** подряд
- CNN вызывается **каждый кадр**, даже если результат стабилен
- Pixel-кэш: **0-3% hit rate** (разные пиксели каждый кадр)

### Пример:
```python
Кадры 1-5:   CNN вернул "3.27" → 5 вызовов
Кадры 6-100: CNN вернёт "3.27" → 95 вызовов (можно пропустить!)
```

**Потенциальная экономия:** 5-10x сокращение CNN вызовов на стабильных знаках

---

## Решение

### Архитектура:

```python
class TrackedSign:
    _stable_cnn_class: str | None       # класс после N стабильных наблюдений
    _consecutive_same_cnn: int          # счётчик одинаковых результатов
    
    def should_skip_cnn() -> bool:
        # True если _consecutive_same_cnn >= 5
    
    def get_stable_cnn_class() -> str | None:
        # Возвращает stable класс для пропуска CNN
```

### Логика:
1. **Первые 5 кадров:** Обычная CNN классификация
2. **После 5 одинаковых результатов:** Знак помечается как "стабильный"
3. **Следующие кадры:** CNN пропускается, используется cached класс
4. **При изменении класса:** Счётчик сбрасывается, начинается новый цикл

---

## Реализованные изменения

### 1. `core/sign.py` — TrackedSign

**Добавлены поля:**
```python
_stable_cnn_class: Optional[str] = None
_consecutive_same_cnn: int = 0
```

**Новые методы:**

#### `_update_cnn_stability(cnn_class: str)`
Вызывается из `append()` при добавлении нового наблюдения.
Обновляет счётчик стабильности.

#### `should_skip_cnn() -> bool`
Проверяет, достиг ли знак порога стабильности (5 кадров).

#### `get_stable_cnn_class() -> Optional[str]`
Возвращает стабильный класс или `None`.

#### `reset_cnn_stability()`
Сбрасывает счётчик (вызывается при `merge()`).

#### `potential_cnn_savings` (property)
Статистическая метрика: сколько CNN вызовов можно было пропустить.

---

### 2. `core/detector.py` — Detector

**Добавлен метод `detect_with_tracking()`:**

```python
def detect_with_tracking(
    frame: np.ndarray,
    tracked_signs: dict[tuple[int,int], TrackedSign],  # map: center_pos -> sign
    skip_ocr: bool = False
) -> list[RawDetection]:
    """
    Детекция с учётом трекинга.
    Пропускает CNN для стабильных знаков в радиусе 50px.
    """
```

**Логика:**
1. Обычная YOLO + rube (без изменений)
2. Для каждого детекта:
   - Ищем TrackedSign в радиусе 50px
   - Если знак стабилен → используем cached класс
   - Иначе → обычная CNN
3. Выводит статистику пропусков в debug лог

---

## Проблема интеграции

### Текущая архитектура:
```
DetectorThread.run()
  ↓
detector.detect(frame)  ← не знает о TrackedSign
  ↓
sign_handler.check_the_data_to_add(detections)  ← создаёт/обновляет TrackedSign
```

### Требуется:
```
DetectorThread.run()
  ↓
tracked_signs_map = sign_handler.get_active_signs_map()  ← новый метод
  ↓
detector.detect_with_tracking(frame, tracked_signs_map)  ← новый метод
  ↓
sign_handler.check_the_data_to_add(detections)
```

---

## Статус реализации

### ✅ Выполнено:
1. TrackedSign с механизмом стабильности
2. Detector.detect_with_tracking() метод
3. Статистика `potential_cnn_savings`
4. Unit-тесты можно добавить (TODO)

### ⏳ Требуется:
1. **SignHandler.get_active_signs_map()** — экспорт активных знаков
2. **DetectorThread** — переключение на `detect_with_tracking()`
3. **Тестирование** — проверка эффективности на реальных данных
4. **Бенчмарк** — замер FPS до/после

---

## Ожидаемые метрики

| Метрика | До B.3 | После B.3 | Улучшение |
|---------|--------|-----------|-----------|
| CNN вызовов на знак | 50-100 | 5-15 | 5-10x |
| FPS (без OCR) | 5.5-7.0 (B.2) | **8-12** | 1.5-2x |
| Hit rate кэша | 50% (B.2) | **80-90%** | +30-40pp |

---

## Альтернативное решение (без рефакторинга)

Если интеграция в pipeline сложна, можно реализовать **post-processing оптимизацию:**

```python
# В SignHandler.check_the_data_to_add()
for det in detections:
    matched_sign = self._find_matching_sign(det)
    
    if matched_sign and matched_sign.should_skip_cnn():
        # Переопределяем CNN класс из stable кэша
        det.number_sign = matched_sign.get_stable_cnn_class()
        # Пропускаем реальный CNN вызов (он уже был в detector)
```

**Проблема:** CNN уже вызван в `detector.detect()`, экономия нулевая.

**Решение:** Передавать `tracked_signs_map` в детектор (требует рефакторинга).

---

## Следующие шаги

### Вариант 1: Полная интеграция (высокий ROI, 2-3 часа)
1. Реализовать `SignHandler.get_active_signs_map()`
2. Обновить `DetectorThread` для использования `detect_with_tracking()`
3. Тестировать + бенчмарк

### Вариант 2: Отложить B.3 (фокус на C-D)
1. **БЛОК C** (Async OCR) даст **10-28x улучшение** с OCR
2. **БЛОК D** (OSM Snap) даст **2-3x ускорение** сохранения
3. Вернуться к B.3 после C-D

---

## Рекомендация

**Приоритет:** Перейти к **БЛОКУ C** (Async OCR)

**Причины:**
1. OCR — критичный bottleneck (FPS 0.1-0.3 с OCR)
2. B.3 требует рефакторинга всего pipeline
3. Эффект от C больше чем от B.3 (10-28x vs 1.5-2x)
4. B.3 можно доделать после C-D-E

**Прогресс БЛОКА B:**
- ✅ B.1 — Профилирование
- ✅ B.2 — Батчинг (2-3x FPS)
- ⚠️ B.3 — TrackedSign-кэш (инфраструктура готова, интеграция отложена)
- ⏳ B.4 — Итоговый бенчмарк (после интеграции B.3)

**Статус БЛОКА B:** 75% (основная оптимизация выполнена)

---

**Создано:** 2026-08-21 14:30  
**Следующий блок:** C — Асинхронный OCR (критичный приоритет)
