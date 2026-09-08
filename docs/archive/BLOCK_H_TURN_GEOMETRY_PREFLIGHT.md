# BLOCK H — Turn Geometry Preflight Analysis

**Дата:** 2026-08-24  
**Статус:** Анализ завершён, готовность к реализации

---

## Шаг 0 — Профилирование и анализ текущей архитектуры

### Текущая реализация (фактическое состояние кода)

#### 1. Turn Processing — ЧТО РЕАЛЬНО ПРОИСХОДИТ

**Миф из промпта:** "используется алгоритм + нейросетевой классификатор"  
**Реальность:**

```python
# core/turn.py::handle_turn()
def handle_turn(self):
    self.segment_length = len(self.frames) / 3
    for sign in self.signs:
        if len(sign.frame_numbers) > 3:
            sign.number = self._handle_sign(sign)  # ← ЭВРИСТИКА, НЕ NN

# _handle_sign() — чистая эвристика:
# - Вычисляет max_size, min_size, coeff_fr (скорость изменения размера bbox)
# - Сравнивает pixel_x[1] vs pixel_x[-2] (движение знака по кадру)
# - Учитывает turn_direction ("left"/"right")
# - Возвращает число 0-8 (позиция на повороте)
```

**Метод `predict_sign_position()` (Keras-модель) ОПРЕДЕЛЁН но НИГДЕ НЕ ВЫЗЫВАЕТСЯ!**

**Вывод:** NN-классификатора в production НЕТ. Есть только эвристика по движению bbox.

---

#### 2. OSM Snap для Turn Signs — НЕ ВЫПОЛНЯЕТСЯ

**Миф из промпта:** "живые Overpass-запросы к OSM на каждый знак при сохранении"  
**Реальность:**

```python
# core/final_handler.py::_process_turn_signs()
def _process_turn_signs(self, turns: list, ...):
    for turn in turns:
        dots = self._calc.calculation_four_dots(turn)  # ← Только геометрия из GPX
        # ...
        for sign in items:
            sign.azimuth = azimuth  # ← Берётся из calculation_four_dots, не из OSM
            x1, y1, x2, y2 = CoordinateCalculation.calculate_result_line(...)
            # НЕТ вызовов snap_sign() или snap_batch()!
```

**Вывод:** Turn signs вообще НЕ привязываются к OSM дорогам — используют только GPX-геометрию.

---

#### 3. Batch OSM Snap — УЖЕ РЕАЛИЗОВАН

**Для прямых знаков:**

```python
# core/final_handler.py::_process_straight_signs()
all_signs = [sign for items in grouped.values() for sign in items]
snap_results = self._batch_snap_signs(all_signs, ...)  # ← BATCH!

# core/osm_snap.py::OSMSnapper.snap_batch()
def snap_batch(self, points: list[tuple[float, float]], ...):
    # Вычисляем bbox всех точек
    min_lat, max_lat = min(lats), max(lats)
    # ...
    ways = self._get_ways_bbox(min_lat, max_lat, min_lon, max_lon)  # ← ОДИН запрос!
    # Снапим каждую точку к загруженным дорогам БЕЗ сетевых вызовов
```

**Вывод:** Batch-оптимизация БЛОКА D уже сделана для straight signs, но НЕ применена к turn signs.

---

### Узкие места (РЕАЛЬНЫЕ, подтверждённые кодом)

| Проблема | Влияние | Где |
|----------|---------|-----|
| Эвристика `_handle_sign()` — нестабильна на нетиповых перекрёстках | **Точность**, не скорость | `core/turn.py:93-148` |
| Turn signs не снапятся к OSM — только GPX-геометрия | **Точность** placement, conf_placement не учитывает OSM | `core/final_handler.py:239-284` |
| Нет bearing-to-sign расчёта — невозможно понять к какому way относится знак | **Точность** на многосторонних перекрёстках | Отсутствует |
| `predict_sign_position()` (Keras) — dead code | Захламляет базу, не используется | `core/turn.py:222-269` |

**КРИТИЧНО:** Проблема НЕ в производительности (turn processing быстрый, т.к. чистая геометрия), а в **точности** определения стороны.

---

### Baseline-метрики (ДО изменений)

**Производительность:**
- Turn processing не замедляет пайплайн (нет сетевых запросов, нет NN-инференса)
- Время обработки turn signs: пропорционально количеству знаков × 4 dots calculation (мгновенно)

**Точность (качественная оценка):**
- Эвристика `_handle_sign()` возвращает `number` 0-8, но:
  - Зависит от субъективных порогов (коэффициенты 150, 250, размер bbox < 100)
  - Не учитывает геометрию перекрёстка (количество сторон, углы примыкания)
  - Не привязана к реальным OSM ways — финальная координата знака может оказаться "в воздухе"

**Известные кейсы где current logic ломается:**
- T-образный перекрёсток (только 3 стороны, а эвристика возвращает 0-8)
- Кольцо (roundabout) — знаки выходящих дорог определяются неверно
- Скошенное примыкание (угол != 90°) — pixel движение не соответствует реальной стороне

---

## Рекомендация: переходить к Шагу 1

**Обоснование:**
- Промпт §2 (геометрическая привязка через bearing + raycast) решает РЕАЛЬНУЮ проблему точности
- Производительность turn processing уже хорошая — batch OSM загрузка добавится "бесплатно" (переиспользуем `snap_batch()`)
- Unified pipeline (straight + turn в одном коде) — возможен и даст упрощение архитектуры

**План корректировки:**
- Следовать Шагу 1-6 промпта, но трактовать задачу как **улучшение точности**, не скорости
- Удалить dead code `predict_sign_position()` как часть Шага 4
- Интегрировать bearing-based snap для turn signs в `_process_turn_signs()` вместо текущей логики `calculation_four_dots()`

---

## Checklist готовности

- [x] Прочитан код `core/turn.py`, `core/final_handler.py`, `core/osm_snap.py`, `core/sign_handler.py`
- [x] Определены реальные узкие места (точность, не скорость)
- [x] Подтверждено что batch OSM snap уже реализован и работает для straight signs
- [x] Подтверждено что NN-классификатор turn position — dead code
- [x] Baseline понятен: эвристика `_handle_sign()` нестабильна, turn signs не снапятся к OSM
- [x] Готовность к Шагу 1: реализация `core/intersection_geometry.py`

---

## Следующие действия

**Шаг 1:** Создать модуль `core/intersection_geometry.py` с функциями:
1. `compute_sign_bearing()` — азимут от машины на знак
2. `raycast_to_ways()` — пересечение луча с OSM ways
3. `aggregate_observations()` — мода по нескольким наблюдениям

**Цель:** Заменить эвристику `_handle_sign()` на геометрический raycast, добавить OSM snap для turn signs.
