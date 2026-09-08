# ✅ ИСПРАВЛЕНО: Координаты "Африка" → Беларусь

**Дата:** 2026-08-24  
**Проблема:** Знаки сохранялись с координатами в Африке (экватор) вместо Беларуси  
**Причина:** GPS координаты конвертировались дважды из WGS84 в EPSG:32635

---

## Проблема

### Симптомы
```json
// GeoJSON содержит неправильные координаты:
{
  "type": "Feature",
  "geometry": {
    "coordinates": [[22.5117, 0.00034], [22.5118, 0.00035]]
    //              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
    //              Это экватор/Африка, НЕ Беларусь!
  }
}
```

**Ожидалось:** `lon≈27.5, lat≈53.9` (Беларусь)  
**Получилось:** `lon≈22.5, lat≈0.0` (Африка/экватор)

---

### Причина

**Двойная конвертация координат:**

1. **GPXHandler** возвращает координаты в **WGS84** (lat/lon):
   ```python
   # core/gpx_handler.py
   def get_current_coordinate(self, index: int) -> tuple[float, float]:
       pt = self.get_point(index)
       return (pt.latitude, pt.longitude)  # WGS84!
   ```

2. **DetectorThread** сохранял их **БЕЗ конвертации**:
   ```python
   # processing/detector_thread.py (БЫЛО)
   lat, lon = self._gpx.get_current_coordinate(raw.gps_index)
   # lat=53.9, lon=27.5 (WGS84)
   
   DetectedSign(
       latitude=lat,   # ❌ Сохраняет WGS84 как EPSG:32635!
       longitude=lon,  # ❌
       ...
   )
   ```

3. **FinalHandler** пытался конвертировать **ПОВТОРНО**:
   ```python
   # core/final_handler.py
   # Думает что car_x/car_y в EPSG:32635, но там WGS84!
   lat, lon = converter.coordinateConverter(
       sign.car_x[-1],  # 53.9 (широта WGS84)
       sign.car_y[-1],  # 27.5 (долгота WGS84)
       "epsg:32635",    # ❌ НО ЭТО УЖЕ WGS84!
       "epsg:4326"      # → мусорные координаты
   )
   ```

**Результат:** Координаты испортились при "конвертации" WGS84 → WGS84 как будто это EPSG:32635 → WGS84.

---

## Исправление

### 1. Конвертация при создании DetectedSign

**Файл:** `processing/detector_thread.py`

**Было:**
```python
lat, lon = self._gpx.get_current_coordinate(raw.gps_index)
# lat, lon в WGS84, но сохраняются как EPSG:32635
```

**Стало:**
```python
lat, lon = self._gpx.get_current_coordinate(raw.gps_index)
# Конвертируем из WGS84 (lat/lon) в EPSG:32635 (x/y) для внутреннего использования
if lat != 0.0 and lon != 0.0:
    lat, lon = self._converter.coordinateConverter(
        lat, lon, "epsg:4326", "epsg:32635"
    )
```

Теперь координаты хранятся в **EPSG:32635** (метры) как и ожидалось!

---

### 2. Добавлен Converter в DetectorThread

**Файл:** `processing/detector_thread.py`

```python
# Импорт
from core.converter import Converter

# В методе run()
self._converter = Converter()  # Для конвертации GPS координат
```

---

### 3. Уточнены комментарии

**Файл:** `core/frame.py`

**Было:**
```python
latitude:  float # координата автомобиля (EPSG:32635 X)
longitude: float # координата автомобиля (EPSG:32635 Y)
```

**Стало:**
```python
latitude:  float # координата автомобиля X (EPSG:32635, метры)
longitude: float # координата автомобиля Y (EPSG:32635, метры)
```

Теперь понятно что это **не lat/lon**, а **x/y в метрах**.

---

## Как проверить

### 1. Перезапустите приложение
```bash
python main.py
```

### 2. Обработайте тот же видеофайл заново
- Processing → выберите видео
- Выберите GPX: `E:\Urban\vid\test\07,07,20211.gpx`
- Start

### 3. Проверьте координаты в GeoJSON

```bash
.venv\Scripts\python.exe scripts\diagnose_coordinates.py
```

**Ожидаемый результат:**
```
=== ПЕРВЫЙ ЗНАК ===
Координаты (GeoJSON):
  Точка 1: lon=27.565825, lat=53.916138  ✅ Беларусь!
  Точка 2: lon=27.565828, lat=53.916140

car_coordinates (из properties):
  car_x (EPSG:32635): 539933.1  ✅ В метрах!
  car_y (EPSG:32635): 5979471.2
```

### 4. Откройте GeoJSON в QGIS/uMap

- Загрузите файл: `E:\Urban\vid\test\test_new_algo.geojson`
- Убедитесь что знаки на карте **в Беларуси**, а не в Африке!

---

## Технические детали

### Система координат EPSG:32635
- **Проекция:** UTM Zone 35N
- **Единицы:** метры
- **Область:** Восточная Европа (в т.ч. Беларусь, Украина)
- **Пример:** `x=549933, y=5979471` → Минск

### Система координат EPSG:4326 (WGS84)
- **Проекция:** Географические координаты
- **Единицы:** градусы
- **Формат:** (latitude, longitude)
- **Пример:** `lat=53.9, lon=27.6` → Минск

### Порядок конвертации (правильный)
```
GPX (WGS84)
  ↓ get_current_coordinate()
  lat=53.9, lon=27.6 (градусы)
  ↓ coordinateConverter(lat, lon, "4326", "32635")
  x=549933, y=5979471 (метры)
  ↓ хранится в DetectedSign.latitude/longitude
  x=549933, y=5979471 (метры)
  ↓ хранится в TrackedSign.car_x/car_y
  x=549933, y=5979471 (метры)
  ↓ coordinateConverter(x, y, "32635", "4326")
  lat=53.9, lon=27.6 (градусы)
  ↓ записывается в GeoJSON
  [27.6, 53.9] ✅ Правильно!
```

---

## Файлы изменены

- ✅ `processing/detector_thread.py` — добавлена конвертация GPS → EPSG:32635
- ✅ `core/frame.py` — уточнены комментарии о системе координат

---

## Статус

✅ **Исправлено** — координаты теперь в правильной проекции  
✅ **Синтаксис проверен** — py_compile успешно  
⏳ **Требует тестирования** — обработайте видео заново и проверьте координаты

---

*Дата: 2026-08-24*  
*Автор: AI Agent (Kiro)*
