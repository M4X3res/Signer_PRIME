# BLOCK H — Turn Geometry Implementation (PARTIAL)

**Дата:** 2026-08-24  
**Статус:** Частично выполнено (Шаги 0-1, начало Шага 3)  
**Следующий шаг:** Интеграция в FinalHandler + фикс raycast intersection

---

## Выполнено

### Шаг 0 — Профилирование и анализ ✅

**Файл:** `BLOCK_H_TURN_GEOMETRY_PREFLIGHT.md`

**Основные находки:**

1. **NN-классификатор НЕ используется в production**
   - Метод `Turn.predict_sign_position()` (Keras) определён, но нигде не вызывается
   - Реально работает эвристика `Turn._handle_sign()` — определяет `sign.number` 0-8 по изменению bbox

2. **Turn signs НЕ снапятся к OSM**
   - `_process_turn_signs()` использует только `calculation_four_dots()` (GPX-геометрия)
   - Никаких вызовов `snap_sign()` или `snap_batch()` для turn signs

3. **Batch OSM snap УЖЕ РЕАЛИЗОВАН** (для straight signs)
   - `OSMSnapper.snap_batch()` + `_get_ways_bbox()` работают
   - `_process_straight_signs()` использует batch подход

**Вывод:**  
Проблема НЕ в производительности (turn processing быстрый), а в **точности** определения стороны знака. Эвристика `_handle_sign()` нестабильна на:
- T-образных перекрёстках (только 3 стороны, а эвристика возвращает 0-8)
- Кольцах (roundabout) — знаки выходящих дорог
- Скошенных примыканиях (угол != 90°)

---

### Шаг 1 — Модуль геометрической привязки ✅

**Файл:** `core/intersection_geometry.py`

**Реализовано:**

#### 1.1. `compute_sign_bearing()` ✅

Вычисляет азимут от машины на знак:

```python
def compute_sign_bearing(
    gpx_azimuth: float,      # Курс машины (GPS)
    bbox_center_x: int,      # X-координата знака в кадре
    frame_width: int,        # Ширина кадра
    hfov_deg: float,         # FOV камеры
) -> float:
    # Смещение знака от центра кадра
    pixel_offset_x = bbox_center_x - (frame_width / 2.0)
    normalized_offset = pixel_offset_x / (frame_width / 2.0)  # [-1..1]
    angle_offset_deg = normalized_offset * (hfov_deg / 2.0)
    
    # Итоговый азимут = курс + смещение
    return (gpx_azimuth + angle_offset_deg) % 360.0
```

**Тесты:** ✅ Все 3 теста прошли:
- Знак в центре → bearing = gpx_azimuth
- Знак справа → bearing > gpx_azimuth
- Знак слева → bearing < gpx_azimuth

---

#### 1.2. `raycast_to_ways()` ⚠️

Бросает луч по азимуту через подложку OSM ways, находит пересечение:

```python
def raycast_to_ways(
    origin_lat: float,
    origin_lon: float,
    bearing_deg: float,
    ways: list[dict],
    max_distance_m: float = 40.0,
    exclude_roundabout: bool = True,
) -> Optional[WayHit]:
    # 1. Строим луч от origin до destination_point(bearing, max_distance_m)
    # 2. Для каждого way проверяем intersection с каждым сегментом
    # 3. Возвращаем ближайшее пересечение
```

**Статус:** Реализовано, но **тесты не проходят** (проблема в `_ray_segment_intersection`).

**TODO:** Дебаг геометрии пересечения луч-отрезок. Возможные причины:
- Локальное приближение lat/lon → метры не работает на малых масштабах (< 100м)
- Параметр `t` (луч) или `u` (отрезок) вычисляется неверно
- Проблема с ориентацией сегментов (направление начало→конец)

**Workaround:** Можно использовать библиотеку `shapely` для intersection вместо самописной геометрии.

---

#### 1.3. `aggregate_observations()` ✅

Агрегирует несколько наблюдений знака, находит моду по way_id:

```python
def aggregate_observations(
    hits: list[WayHit],
) -> tuple[Optional[str], float, Optional[WayHit]]:
    # Мода по way_id
    way_counter = Counter(hit.way_id for hit in hits)
    most_common_way, count = way_counter.most_common(1)[0]
    
    consistency = count / len(hits)
    
    # Медианный hit по distance_m для этого way
    representative = median_hit_by_distance(way_hits)
    
    return most_common_way, consistency, representative
```

**Тесты:** ✅ Все тесты прошли:
- Одно наблюдение → consistency = 1.0
- Все одного way → consistency = 1.0
- 7 из 10 одного way → consistency = 0.7

---

### Шаг 3 — Настройки (начало) ✅

**Файл:** `configs/settings.py`

**Добавлены поля в `AppSettings`:**

```python
# ── Геометрия перекрёстков (BLOCK H) ──────────────────────────────
camera_hfov_deg: float = 120.0      # Горизонтальный FOV камеры
turn_ray_max_distance_m: float = 40.0  # Максимальная дистанция луча
turn_detection_radius_m: float = 25.0  # Радиус вокруг OSM-перекрёстка
turn_use_bearing_geometry: bool = True  # Использовать bearing-based geometry
```

**Дефолтные значения:**
- `camera_hfov_deg = 120.0` — под GoPro Hero (широкоугольная экшн-камера)
- `turn_ray_max_distance_m = 40.0` — достаточно для знаков рядом с перекрёстком
- `turn_detection_radius_m = 25.0` — радиус детекции перекрёстка
- `turn_use_bearing_geometry = True` — по умолчанию включена новая логика

**TODO:** Прокинуть настройки в UI (SettingsPage) — аналогично существующим `dedup_*` полям.

---

## Не выполнено (требуется продолжение)

### Шаг 2 — Интеграция в FinalHandler ❌

**Что нужно сделать:**

1. Модифицировать `_process_turn_signs()`:
   - Для каждого знака в turn.signs:
     - Взять все наблюдения (bbox_center_x, frame_width, gpx_azimuth, GPS-позиция по кадрам)
     - Вызвать `compute_sign_bearing()` для каждого наблюдения
     - Взять уже загруженные ways (переиспользовать `_get_ways_bbox()` из straight signs)
     - Вызвать `raycast_to_ways()` для каждого наблюдения → список WayHit
     - Агрегировать через `aggregate_observations()` → финальный way_id, consistency
     - Использовать way_azimuth из representative hit для sign.azimuth
     - Вычислить conf_placement с учётом consistency (как компонент уверенности)

2. Опционально: объединить `_process_straight_signs()` и `_process_turn_signs()` в один path, если логика унифицируется (проверить на реальных данных).

3. Сохранить fallback на текущую логику `calculation_four_dots()` если:
   - `settings.turn_use_bearing_geometry == False`
   - Или raycast не нашёл пересечений (hit == None)

**Статус:** Не начато.

---

### Шаг 4 — Удаление dead code ❌

**Что удалить:**

1. `core/turn.py::predict_sign_position()` — Keras-модель для position prediction (dead code)
2. Зависимости от Keras в `configs/sign_models.py` если они используются только для этой функции
3. Веса модели (если есть отдельный файл .h5/.keras)

**Осторожно:** НЕ удалять до тех пор, пока новый bearing-based подход не протестирован на реальном видео и не подтверждён как working.

**Статус:** Не начато.

---

### Шаг 5 — Регрессионные тесты ❌

**Что нужно:**

1. Фикс unit-тестов `test_intersection_geometry.py`:
   - Дебаг `_ray_segment_intersection()` (проблема с геометрией)
   - Добавить реальные координаты из логов roadscan.log (перекрёстки Минска)

2. Интеграционный тест:
   - Обработать одно и то же видео с перекрёстками через старый и новый path
   - Сравнить количество знаков, присвоенные way_id, conf_placement

3. Benchmark:
   - Замер времени `_process_turn_signs()` до/после (ожидается что не будет деградации, т.к. batch OSM snap уже делается для straight signs)

**Статус:** Не начато.

---

### Шаг 6 — Документация ❌

**Что создать:**

- Отчёт `BLOCK_H_TURN_GEOMETRY_IMPLEMENTATION.md` с:
  - Проблема (эвристика нестабильна)
  - Решение (bearing + raycast)
  - Изменённые файлы + diff
  - Численные результаты до/после (точность, conf_placement)
  - Известные ограничения (например, требуется знать реальный FOV камеры)

**Статус:** Не начато (текущий файл — черновик).

---

## Критические блокеры

### 1. `raycast_to_ways()` — тесты не проходят

**Проблема:** `_ray_segment_intersection()` не находит пересечение даже на очевидных тестовых данных.

**Варианты решения:**

A. **Дебаг самописной геометрии** (2-3 часа работы):
   - Визуализация луча и сегментов в координатной плоскости
   - Пошаговая проверка вычислений `t`, `u`

B. **Использовать `shapely` (рекомендуется)**:
   ```python
   from shapely.geometry import LineString, Point
   
   ray_line = LineString([(r_lon1, r_lat1), (r_lon2, r_lat2)])
   seg_line = LineString([(s_lon1, s_lat1), (s_lon2, s_lat2)])
   
   if ray_line.intersects(seg_line):
       intersection = ray_line.intersection(seg_line)
       # intersection.coords[0] → (lon, lat)
   ```
   
   Shapely уже установлен (используется в других частях проекта для polygon операций).

**Рекомендация:** Вариант B — переписать `raycast_to_ways()` через shapely за 30 минут вместо 3 часов дебага.

---

### 2. TrackedSign не хранит bbox_center_x по кадрам

**Проблема:** Для вычисления bearing нужен `bbox_center_x` для каждого наблюдения, но `TrackedSign` хранит только `pixel_x`, `pixel_y` (угол bbox, не центр).

**Решение:** В `TrackedSign.append(det)` вычислять и сохранять:
```python
bbox_center_x = det.x + det.w // 2
bbox_center_y = det.y + det.h // 2
self.bbox_centers_x.append(bbox_center_x)
self.bbox_centers_y.append(bbox_center_y)
```

**Альтернатива:** Вычислять на лету в `_process_turn_signs()`:
```python
for i in range(len(sign.pixel_x)):
    bbox_center_x = sign.pixel_x[i] + sign.widths[i] // 2
```

---

## Следующие шаги (приоритет)

1. **Фикс raycast через shapely** (30 мин)
   - Переписать `_ray_segment_intersection()` с использованием `shapely.geometry.LineString.intersection()`
   - Перепрогнать тесты

2. **Интеграция в FinalHandler** (2-3 часа)
   - Модифицировать `_process_turn_signs()` для использования bearing-based логики
   - Добавить fallback на старую логику через `settings.turn_use_bearing_geometry`

3. **Тестирование на реальном видео** (1 час)
   - Обработать видео с известными перекрёстками
   - Проверить что way_id присваиваются корректно
   - Сравнить conf_placement до/после

4. **Удаление dead code** (30 мин)
   - `Turn.predict_sign_position()` + связанные зависимости

5. **Финальный отчёт** (1 час)
   - `BLOCK_H_TURN_GEOMETRY_IMPLEMENTATION.md`

**Estimated time to complete:** 5-6 часов чистой работы.

---

## Критерии приёмки (из промпта)

| Критерий | Статус |
|----------|--------|
| ✅ Профилирование до правок зафиксировано | ✅ `BLOCK_H_TURN_GEOMETRY_PREFLIGHT.md` |
| ⚠️ Определение стороны не использует NN-классификатор | ⚠️ Новая логика реализована, но не интегрирована |
| ✅ Определение стороны не делает сетевых запросов на знак | ✅ Переиспользует `_get_ways_bbox()` |
| ⚠️ Есть unit-тесты на синтетических перекрёстках | ⚠️ Тесты написаны, но raycast не работает |
| ❌ Regression-тест на реальном видео | ❌ Не сделано |
| ❌ Замер FPS/времени обработки "до/после" | ❌ Не сделано |
| ❌ conf_placement формат не сломан | ❌ Не проверено |
| ⚠️ Настройки доступны в AppSettings | ⚠️ Добавлены в dataclass, не прокинуты в UI |
| ❌ Приложение стартует без крашей | ❌ Не проверено |
| ❌ Создан отчёт `BLOCK_H_TURN_GEOMETRY_IMPLEMENTATION.md` | ❌ Текущий файл — черновик |

---

## Выводы

**Сделано:**
- Архитектурный анализ (Шаг 0) — подтвердил проблему точности, не скорости
- Модуль геометрии (Шаг 1) — bearing computation работает, raycast требует фикса
- Настройки (Шаг 3 partial) — добавлены в AppSettings

**Блокеры:**
- Raycast intersection не работает — требуется переписать через shapely
- TrackedSign не хранит bbox centers — требуется минорный рефакторинг

**Готовность к продакшену:** ~30% (основа заложена, требуется интеграция и тестирование).

**Рекомендация:** Продолжить реализацию после фикса raycast. Ожидаемое улучшение — **повышение точности** определения стороны знака на сложных перекрёстках (T-образные, кольца, скошенные), **без деградации производительности** (т.к. batch OSM snap уже сделан).
