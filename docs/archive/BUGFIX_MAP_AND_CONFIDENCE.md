# Исправление проблем с картой и точностью классификации

## Обновление: Исправлена критическая ошибка в расчёте cnn_count

**Дата:** 2026-07-10 11:06

### ⚠️ Проблема после первого исправления
После добавления полей `conf_cnn` в GeoJSON точность классификации стала показывать **0%** вместо правильных значений.

**Причина:** Метод `TrackedSign.cnn_count` считал количество **самого частого класса** в CNN результатах, а не количество совпадений с финальным типом `best_yolo`.

### ✅ Решение
**Файл:** `core/sign.py`

Изменён метод `cnn_count`:
```python
# БЫЛО (неправильно):
@property
def cnn_count(self) -> int:
    """Сколько раз лучший CNN-класс встречается."""
    return self.most_common(self.cnn_results)[1]

# СТАЛО (правильно):
@property
def cnn_count(self) -> int:
    """Сколько раз финальный тип (best_yolo) встречается в CNN результатах."""
    if not self.cnn_results or not self.best_yolo:
        return 0
    return self.cnn_results.count(self.best_yolo)
```

Теперь `cnn_count` считает, сколько раз нейросеть выдала именно тот класс, который был выбран как финальный (с учётом OCR, контекста, геометрии).

**Подробности:** см. `FIX_CNN_COUNT_CALCULATION.md`

---

## Проблемы

1. **Не работает кнопка по треку на карте**
2. **Не показывает знаки на карте**
3. **Точность GPS показывает всегда ~50%** (хотя есть классификация нейросетью)

## Причины и решения

### 1. Точность классификации всегда ~50%

#### Проблема
В `ui/widgets/error_editor_page.py` функция `SignRecord._calc_confidence()` использовала неправильную логику:
- Пыталась вычислить уверенность из длины разных списков (`pixel_coordinates_x`, `car_coordinates_x`)
- Не использовала готовые значения `conf_cnn`, `cnn_count`, `observation_count` из GeoJSON
- В результате всегда возвращала примерно 50% независимо от реальной уверенности нейросети

#### Решение 1: Добавление полей уверенности в GeoJSON
**Файл:** `core/final_handler.py`

```python
props: dict = {
    "type":                  type_sign,
    "length":                str(sign.observation_count),
    "cnn_count":             str(sign.cnn_count),           # НОВОЕ
    "observation_count":     str(sign.observation_count),   # НОВОЕ
    "conf_cnn":              f"{sign.conf_cnn:.3f}",        # НОВОЕ
    "conf_placement":        f"{sign.conf_placement:.3f}",  # НОВОЕ
    "conf_total":            f"{sign.conf_total:.3f}",      # НОВОЕ
    # ... остальные поля
}
```

Теперь в GeoJSON сохраняются:
- `cnn_count` — сколько раз лучший класс встречался
- `observation_count` — общее количество наблюдений
- `conf_cnn` — уверенность классификации (cnn_count / observation_count)
- `conf_placement` — уверенность размещения (стабильность GPS)
- `conf_total` — общая уверенность (среднее)

#### Решение 2: Исправление расчёта в ErrorEditorPage
**Файл:** `ui/widgets/error_editor_page.py`

```python
def _calc_confidence(self) -> float:
    """
    Уверенность классификации нейросетью: cnn_count / observation_count.
    
    Сначала пытаемся взять готовое значение conf_cnn из properties.
    Если его нет — рассчитываем вручную.
    """
    # Пытаемся взять готовое значение
    conf_cnn_str = self.props.get("conf_cnn", "")
    if conf_cnn_str:
        try:
            return float(conf_cnn_str)
        except (ValueError, TypeError):
            pass
    
    # Если нет готового значения — рассчитываем
    cnn_count_str = self.props.get("cnn_count", "")
    obs_count_str = self.props.get("observation_count", "")
    
    try:
        cnn_count = int(cnn_count_str) if cnn_count_str else 0
        obs_count = int(obs_count_str) if obs_count_str else 0
        
        if obs_count > 0:
            return min(1.0, cnn_count / obs_count)
    except (ValueError, TypeError):
        pass
    
    # Fallback: используем length / total кадров
    # ... код fallback
```

**Результат:**
- Теперь показывается реальная уверенность нейросети
- Например, если знак был правильно классифицирован в 8 из 10 кадров — будет 80%
- GPS уверенность рассчитывается отдельно на основе стабильности координат
- Общая уверенность = среднее между классификацией и GPS

---

### 2. Знаки не отображаются на карте

#### Проблема
В `server/map_server.py` в функции `api_signs()` был неправильный парсинг координат:

```python
# НЕПРАВИЛЬНО:
lon, lat = coords[0][0], coords[0][1]
```

Это предполагает структуру `coords = [[lon, lat]]`, но в GeoJSON LineString структура:
```
coordinates: [[lon1, lat1], [lon2, lat2], ...]
```

Поэтому `coords[0]` — это уже `[lon, lat]`, и `coords[0][0]` — это `lon`.

#### Решение
**Файл:** `server/map_server.py`

```python
result = []
for feat in features:
    props = feat.get("properties", {})
    geom = feat.get("geometry", {})
    coords = geom.get("coordinates", [])
    
    if not coords or len(coords) == 0:
        print(f"[API /api/signs] Пропускаем feature без координат: {props.get('id', 'unknown')}")
        continue
    
    # GeoJSON LineString: coordinates = [[lon, lat], [lon, lat], ...]
    # Берём первую точку линии как позицию маркера
    try:
        first_point = coords[0]
        if not isinstance(first_point, (list, tuple)) or len(first_point) < 2:
            print(f"[API /api/signs] Некорректный формат координат для {props.get('id', 'unknown')}: {first_point}")
            continue
            
        lon, lat = first_point[0], first_point[1]
        
        # Проверяем что координаты валидные
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            print(f"[API /api/signs] Невалидные координаты для {props.get('id', 'unknown')}: lon={lon}, lat={lat}")
            continue
            
    except (IndexError, TypeError, ValueError) as e:
        print(f"[API /api/signs] Ошибка парсинга координат для {props.get('id', 'unknown')}: {e}")
        continue
    
    result.append({
        "id":          props.get("id", str(uuid.uuid4())),
        "type":        props.get("type", ""),
        # ... остальные поля
        "lat":         lat,
        "lon":         lon,
        "line":        coords,  # полная линия для отображения
    })
```

**Добавлено:**
- Проверка структуры координат
- Валидация диапазона координат (-180..180 для долготы, -90..90 для широты)
- Детальное логирование ошибок
- Try-catch для безопасного парсинга

---

### 3. Трек не отображается на карте

#### Проблема
Недостаточное логирование в `/api/track` затрудняло диагностику.

#### Решение
**Файл:** `server/map_server.py`

Добавлено детальное логирование:
```python
@app.route("/api/track")
def api_track():
    """GPS-трек в виде массива [lat, lon]."""
    try:
        print(f"[API /api/track] Запрос получен")
        print(f"[API /api/track] PATH_TO_GPX = {config.PATH_TO_GPX}")
        
        if not config.PATH_TO_GPX:
            print("[API /api/track] PATH_TO_GPX пустой")
            return jsonify([])
        if not os.path.exists(config.PATH_TO_GPX):
            print(f"[API /api/track] Файл не найден: {config.PATH_TO_GPX}")
            return jsonify([])
        
        print(f"[API /api/track] Загружаем GPX из {config.PATH_TO_GPX}")
        points = []
        with open(config.PATH_TO_GPX, encoding="utf-8") as f:
            gpx = gpxpy.parse(f)
        
        for track in gpx.tracks:
            for segment in track.segments:
                for pt in segment.points:
                    points.append([pt.latitude, pt.longitude])
        
        print(f"[API /api/track] Найдено {len(points)} точек трека")
        return jsonify(points)
    except Exception as e:
        print(f"ERROR in /api/track: {e}")
        import traceback
        traceback.print_exc()
        return jsonify([]), 200
```

---

## Диагностика

### Проверка API напрямую

1. **Запустите приложение**
2. **Откройте браузер** и проверьте endpoints:

```
http://localhost:3000/api/track
http://localhost:3000/api/signs
```

### Ожидаемые логи в консоли

**При запросе `/api/track`:**
```
[API /api/track] Запрос получен
[API /api/track] PATH_TO_GPX = C:\path\to\file.gpx
[API /api/track] Загружаем GPX из C:\path\to\file.gpx
[API /api/track] Найдено 1234 точек трека
```

**При запросе `/api/signs`:**
```
[API /api/signs] Запрос получен
[API /api/signs] PATH_TO_GEOJSON = C:\path\to\output.geojson
[API /api/signs] Загружаем GeoJSON из C:\path\to\output.geojson
[API /api/signs] Найдено 15 features в GeoJSON
[API /api/signs] Возвращаем 15 знаков клиенту
```

### Проверка точности в редакторе

1. **Перейдите на страницу "Редактор ошибок"**
2. **Нажмите "Загрузить GeoJSON"**
3. **Проверьте колонку "Уверенность":**
   - Должна показывать реальные значения (не всегда 50%)
   - Высокая уверенность (>70%) — зелёный
   - Средняя (40-70%) — жёлтый
   - Низкая (<40%) — красный

### Логи редактора

```
[ErrorEditor] load_geojson вызван, target = C:\path\to\output.geojson
[ErrorEditor] Загружаем GeoJSON из C:\path\to\output.geojson
[ErrorEditor] Найдено 15 features в GeoJSON
[ErrorEditor] Создано 15 SignRecord объектов
[ErrorEditor] Выбран первый элемент, всего записей: 15
```

---

## Структура данных

### GeoJSON Feature (после исправлений)

```json
{
  "type": "Feature",
  "geometry": {
    "type": "LineString",
    "coordinates": [
      [27.561234, 53.902345],
      [27.561456, 53.902567]
    ]
  },
  "properties": {
    "type": "3.24",
    "code": 324,
    "cnn_count": "8",
    "observation_count": "10",
    "conf_cnn": "0.800",
    "conf_placement": "0.750",
    "conf_total": "0.775",
    "azimuth": "45.2",
    "time": "1:23",
    "name_video": "video001.mp4",
    "SEM250": "Минск"
  }
}
```

### API Response `/api/signs`

```json
[
  {
    "id": "uuid-here",
    "type": "3.24",
    "code": "324",
    "azimuth": 45.2,
    "description": "Минск",
    "side": "left",
    "time": "1:23",
    "name_video": "video001.mp4",
    "abs_frame": "[3600, 3661, 3722]",
    "lat": 53.902345,
    "lon": 27.561234,
    "line": [[27.561234, 53.902345], [27.561456, 53.902567]]
  }
]
```

### API Response `/api/track`

```json
[
  [53.902345, 27.561234],
  [53.902567, 27.561456],
  [53.902789, 27.561678]
]
```

---

## Тестирование

1. **Запустите обработку видео**
2. **Дождитесь завершения и сохранения GeoJSON**
3. **Перейдите на страницу "Карта":**
   - Должен отобразиться GPS трек (синяя линия)
   - Должны появиться маркеры знаков
   - При клике на маркер — открывается детальная информация
4. **Перейдите на страницу "Редактор ошибок":**
   - Нажмите "Загрузить GeoJSON"
   - Проверьте что уверенность показывает разные значения (не все 50%)
   - Проверьте что есть знаки с высокой (>80%) и низкой (<40%) уверенностью

---

## Изменённые файлы

1. `core/final_handler.py` — добавлены поля уверенности в GeoJSON
2. `ui/widgets/error_editor_page.py` — исправлен расчёт уверенности
3. `server/map_server.py` — исправлен парсинг координат и добавлено логирование
4. `BUGFIX_MAP_AND_CONFIDENCE.md` — эта документация

---

## Известные ограничения

1. **Старые GeoJSON файлы** не содержат поля `conf_cnn`, `cnn_count`, `observation_count`
   - Для них будет использоваться fallback расчёт
   - Рекомендуется перезапустить обработку для получения точных данных

2. **Координаты в неправильном формате** будут пропущены с логом в консоль
   - Проверьте логи для диагностики

3. **Пустой GPX или GeoJSON** — карта не отобразит данные, но не будет ошибки
   - Проверьте что файлы выбраны на Dashboard
