# Диагностика: Знаки не показываются на карте и в редакторе

## Дата: 2026-07-10 09:08

### Добавлено подробное логирование

#### 1. Редактор ошибок (ui/widgets/error_editor_page.py)

**В load_geojson():**
```
[ErrorEditor] load_geojson вызван, target = путь
[ErrorEditor] Загружаем GeoJSON из путь
[ErrorEditor] Найдено N features в GeoJSON
[ErrorEditor] Создано N SignRecord объектов
[ErrorEditor] Выбран первый элемент, всего записей: N
```

**В SignListModel.load():**
```
[SignListModel] Загружено N записей
[SignListModel] Диапазон уверенности: 0.123 - 0.987
[SignListModel] Первые 3 знака:
  [0] 3.24 - confidence: 0.123, gps: 0.145, total: 0.134
  [1] 1.1 - confidence: 0.234, gps: 0.256, total: 0.245
  [2] 2.4 - confidence: 0.345, gps: 0.367, total: 0.356
```

**Что это показывает:**
- Сколько знаков найдено в GeoJSON
- Сколько успешно загружено в модель
- Как они отсортированы (от наименее уверенных к наиболее)
- Значения confidence для первых 3 знаков

#### 2. Карта (templates/map.html)

**В loadSigns():**
```
[loadSigns] Обработано знаков: N
[loadSigns] Первый знак: {id: "...", type: "3.24", lat: 53.902, lon: 27.561, ...}
[loadSigns] Координаты первого знака: lat=53.902, lon=27.561
```

**В renderMarkers():**
```
[renderMarkers] Знак 0: type=3.24, lat=53.902, lon=27.561, id=abc-123
[renderMarkers] Знак 1: type=1.1, lat=53.903, lon=27.562, id=def-456
[renderMarkers] Знак 2: type=2.4, lat=53.904, lon=27.563, id=ghi-789
[renderMarkers] Отрендерено маркеров: 11
[renderMarkers] Текущий центр карты: LatLng(53.9, 27.5)
[renderMarkers] Текущий zoom: 15
[renderMarkers] Видимые границы карты: LatLngBounds(...)
[renderMarkers] Границы знаков: [53.902, 27.561] - [53.910, 27.570]
[renderMarkers] Центрируем карту на 11 знаков
```

**Что это показывает:**
- Координаты первых 3 знаков
- Текущее положение и масштаб карты
- Границы видимой области
- Границы знаков
- Центрируется ли карта автоматически

## Сценарии диагностики

### Сценарий 1: Редактор пустой

**Проверьте логи Python:**
```
[MainWindow] Обновление редактора запланировано
[MainWindow] Перезагрузка редактора...
[ErrorEditor] load_geojson вызван, target = C:\...\output.geojson
[ErrorEditor] Найдено 11 features в GeoJSON
[ErrorEditor] Создано 11 SignRecord объектов
[SignListModel] Загружено 11 записей
```

**Если видите:**
- `[ErrorEditor] target пустой` → PATH_TO_GEOJSON не установлен
- `[ErrorEditor] Файл не существует` → Проблема в пути или файл не сохранился
- `[ErrorEditor] Найдено 0 features` → GeoJSON пустой
- `[ErrorEditor] Создано 0 SignRecord объектов` → В features нет поля "type"

**Решение:**
1. Проверьте что PATH_TO_GEOJSON установлен на Dashboard
2. Откройте GeoJSON файл в текстовом редакторе
3. Убедитесь что есть массив "features" с элементами
4. Проверьте что у каждого feature есть "properties" → "type"

### Сценарий 2: Карта пустая (маркеры не видны)

**Проверьте логи браузера (F12 → Console):**
```
[loadSigns] Обработано знаков: 11
[loadSigns] Координаты первого знака: lat=53.902, lon=27.561
[renderMarkers] Отрендерено маркеров: 11
[renderMarkers] Текущий центр карты: LatLng(53.9, 27.5)
[renderMarkers] Границы знаков: [53.902, 27.561] - [53.910, 27.570]
```

**Сравните координаты:**
- Если центр карты далеко от знаков → Нужно центрировать вручную
- Если zoom слишком большой/маленький → Нужно изменить масштаб

**Проверьте видимость:**
```javascript
// В консоли браузера выполните:
console.log("Знаков загружено:", signsData.length);
console.log("Маркеров на карте:", Object.keys(markers).length);
console.log("Первый маркер:", Object.values(markers)[0]);
console.log("Маркер на карте?", map.hasLayer(Object.values(markers)[0]));
```

**Ручная центрация:**
```javascript
// В консоли браузера:
if (Object.keys(markers).length > 0) {
  const bounds = Object.values(markers).map(m => m.getLatLng());
  map.fitBounds(bounds, { padding: [50, 50] });
}
```

### Сценарий 3: Координаты некорректные

**Если в логах видите:**
```
[loadSigns] Координаты первого знака: lat=0, lon=0
```
или
```
[loadSigns] Координаты первого знака: lat=null, lon=undefined
```

**Проблема в API или GeoJSON:**
1. Откройте http://localhost:3000/api/signs в браузере
2. Проверьте что в JSON есть поля `lat` и `lon`
3. Откройте GeoJSON файл напрямую
4. Проверьте что у geometry есть coordinates

**Пример правильной структуры GeoJSON:**
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [
          [27.561, 53.902],  // [lon, lat] - первая точка
          [27.562, 53.903]   // [lon, lat] - вторая точка
        ]
      },
      "properties": {
        "id": "abc-123",
        "type": "3.24",
        "azimuth": "45.5",
        ...
      }
    }
  ]
}
```

**API должен возвращать:**
```json
[
  {
    "id": "abc-123",
    "type": "3.24",
    "lat": 53.902,  // широта (Y)
    "lon": 27.561,  // долгота (X)
    ...
  }
]
```

### Сценарий 4: Трек перекрывает знаки

**Если в логах видите:**
```
[renderMarkers] Трек виден, не центрируем на знаки
```

**Решение:**
1. Нажмите кнопку "Трек" чтобы скрыть его
2. Или нажмите "По треку" чтобы показать всё
3. Или выполните в консоли:
   ```javascript
   map.removeLayer(trackLine);
   const bounds = Object.values(markers).map(m => m.getLatLng());
   map.fitBounds(bounds, { padding: [50, 50] });
   ```

## Проверочный чек-лист

После запуска обработки проверьте:

### Python консоль:
- [ ] `[FinalHandler] Сохранено N знаков → путь`
- [ ] `[MainWindow] Редактор перезагружен успешно`
- [ ] `[ErrorEditor] Создано N SignRecord объектов`
- [ ] `[SignListModel] Загружено N записей`
- [ ] `[MapServer] emit_processing_finished вызван`

### Браузерная консоль (F12):
- [ ] `[loadSigns] Обработано знаков: N`
- [ ] `[loadSigns] Координаты первого знака: lat=..., lon=...`
- [ ] `[renderMarkers] Отрендерено маркеров: N`
- [ ] `[renderMarkers] Центрируем карту на N знаков`

### Редактор:
- [ ] Список знаков не пустой
- [ ] Знаки отсортированы (наименее уверенные сверху)
- [ ] При клике показывается превью кадра
- [ ] Счётчики показывают правильное количество

### Карта:
- [ ] Счётчик "Знаков: N" показывает > 0
- [ ] Маркеры видны на карте
- [ ] При клике на маркер открывается панель деталей
- [ ] Трек и маркеры видны одновременно

## Следующие шаги

1. **Запустите обработку заново**
2. **Откройте консоль Python** - проверьте логи редактора
3. **Откройте браузер → F12** - проверьте логи карты
4. **Перейдите на вкладку "Редактор"** - проверьте список знаков
5. **Перейдите на вкладку "Карта"** - проверьте маркеры

Если проблема сохраняется:
- Отправьте логи из Python консоли (секция [ErrorEditor] и [SignListModel])
- Отправьте логи из браузера (секция [loadSigns] и [renderMarkers])
- Отправьте скриншот редактора
- Отправьте скриншот карты с открытым DevTools

С этими данными точно определим причину!
