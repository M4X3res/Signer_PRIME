# Исправление порядка инициализации SignRecord

## Проблема

После предыдущих исправлений в `ui/widgets/error_editor_page.py` был неправильный порядок инициализации полей в классе `SignRecord`.

### Что было не так

```python
def __init__(self, feature: dict):
    # ... базовые поля ...
    
    # ❌ Вызываем _calc_gps_confidence()
    self.gps_confidence: float = self._calc_gps_confidence()
    
    # ... расчёт total_confidence ...
    
    # ❌ Создаём _abs_frames ПОСЛЕ использования
    self._abs_frames: list[int] = self._parse_int_list(...)
```

**Проблема:** В методе `_calc_gps_confidence()` есть fallback код, который обращается к `self._abs_frames`:

```python
def _calc_gps_confidence(self) -> float:
    # ...
    obs_count = len(self._abs_frames)  # ❌ AttributeError!
```

Если `conf_placement` отсутствует в GeoJSON (старые файлы), происходит ошибка `AttributeError: 'SignRecord' object has no attribute '_abs_frames'`.

---

## Решение

Изменён порядок инициализации: **сначала создаём все необходимые поля, потом вызываем методы расчёта**.

### Правильный порядок

```python
def __init__(self, feature: dict):
    # 1. Базовые поля из properties
    self.feature = feature
    self.props = feature.get("properties", {})
    self.id = self.props.get("id", "")
    self.type = self.props.get("type", "")
    # ... и т.д.
    
    # 2. Координаты кадра (нужны для fallback расчётов)
    self._abs_frames: list[int] = self._parse_int_list(
        self.props.get("absolute_frame_numbers", "")
    )
    self._frame_numbers: list[int] = self._parse_int_list(
        self.props.get("frame_numbers", "")
    )
    
    # 3. Bbox (может использоваться в расчётах)
    self.bbox: Optional[tuple] = self._parse_median_bbox()
    
    # 4. Расчёты уверенности (ТЕПЕРЬ могут использовать _abs_frames)
    self.confidence: float = self._calc_confidence()
    self.gps_confidence: float = self._calc_gps_confidence()
    self.total_confidence: float = ...
    
    # 5. Изменения пользователя
    self.new_type: str = self.type
    self.new_text: str = self.text
    self.modified: bool = False
    self.deleted: bool = False
```

---

## Зависимости между полями

### _calc_confidence() требует:
- ✅ `self.props` — для чтения conf_cnn, cnn_count, observation_count
- ✅ `self._frame_numbers` — для fallback расчёта (если нет готовых значений)

### _calc_gps_confidence() требует:
- ✅ `self.props` — для чтения conf_placement
- ✅ `self.azimuth` — для fallback расчёта
- ✅ `self._abs_frames` — для fallback расчёта (количество наблюдений)
- ✅ `self.feature` — для fallback расчёта (geometry coordinates)

### _parse_median_bbox() требует:
- ✅ `self.props` — для чтения pixel_coordinates_x, y, w, h
- ✅ Методы `_parse_int_list()` — статические, не требуют полей

---

## Правило инициализации

**Общее правило:** Инициализируйте поля в порядке зависимостей:

1. **Простые поля** (напрямую из словаря)
2. **Вспомогательные структуры** (списки, которые используются дальше)
3. **Вычисляемые поля** (которые могут использовать пункты 1-2)
4. **Поля состояния** (флаги, изменения пользователя)

---

## Тестирование

### Тест 1: Новый GeoJSON с полями уверенности
```python
feature = {
    "properties": {
        "type": "3.24",
        "conf_cnn": "0.850",
        "conf_placement": "0.782",
        "conf_total": "0.816",
        "absolute_frame_numbers": "[100, 161, 222]",
        "frame_numbers": "[0, 61, 122]"
    },
    "geometry": {...}
}

record = SignRecord(feature)
# ✅ Должно работать без ошибок
# ✅ record.confidence == 0.850
# ✅ record.gps_confidence == 0.782
# ✅ record.total_confidence == 0.816
```

### Тест 2: Старый GeoJSON без полей уверенности
```python
feature = {
    "properties": {
        "type": "3.24",
        # НЕТ conf_cnn, conf_placement, conf_total
        "absolute_frame_numbers": "[100, 161, 222]",
        "frame_numbers": "[0, 61, 122]",
        "length": "3"
    },
    "geometry": {
        "coordinates": [[27.5, 53.9], [27.51, 53.91]]
    }
}

record = SignRecord(feature)
# ✅ Должно работать без ошибок (fallback расчёт)
# ✅ record._abs_frames доступен в _calc_gps_confidence()
# ✅ record.confidence рассчитан по fallback
# ✅ record.gps_confidence рассчитан по fallback
```

---

## Изменённые файлы

- **`ui/widgets/error_editor_page.py`** — изменён порядок инициализации в `SignRecord.__init__()`

---

## Влияние изменения

### ✅ Положительное
- Исправлена потенциальная ошибка `AttributeError` при загрузке старых GeoJSON
- Код более логичный и понятный (зависимости явные)
- Fallback расчёты работают корректно

### ⚠️ Внимание
- Никаких изменений в поведении для новых GeoJSON (с полями уверенности)
- Для старых GeoJSON теперь fallback расчёт работает правильно

---

## Совместимость

### Новые GeoJSON (с conf_cnn, conf_placement, conf_total)
- ✅ Используются готовые значения из properties
- ✅ Fallback код не выполняется
- ✅ Быстро и точно

### Старые GeoJSON (без полей уверенности)
- ✅ Fallback расчёт работает корректно
- ✅ Не возникает AttributeError
- ⚠️ Менее точные метрики (нет OSM snap, детальной стабильности)

**Рекомендация:** Для точных метрик перезапустите обработку с новым кодом.

---

## Итоговый порядок инициализации

```python
SignRecord.__init__():
    1. feature, props          # Исходные данные
    2. id, type, code, ...     # Простые поля из props
    3. _abs_frames, _frame_numbers  # Списки координат
    4. bbox                    # Медианный bbox
    5. confidence              # Уверенность CNN (может использовать _frame_numbers)
    6. gps_confidence          # Уверенность GPS (может использовать _abs_frames)
    7. total_confidence        # Общая уверенность
    8. new_type, new_text, ... # Изменения пользователя
```

Этот порядок гарантирует что все необходимые поля доступны на момент их использования.
