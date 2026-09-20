# Автоматическая загрузка стилей для векторных тайлов

**Дата:** 2026-09-15  
**Статус:** ✅ Реализовано

---

## Проблема

При использовании векторных тайлов от api.maps.by карта отображалась с упрощёнными generic-стилями (синие линии на тёмном фоне), так как стили сервера не загружались автоматически.

---

## Решение

Добавлена автоматическая загрузка стилей из `resources/styles/root.json` провайдера.

### Архитектура

```
Frontend (map.html)
    ↓
    1. GET /api/vector_tile_style
    ↓
Backend (map_server.py)
    ↓
    2. Извлечение base URL из tile_url
    3. Формирование style_url: base_url + /resources/styles/root.json + token
    4. Проксирование запроса к upstream
    5. Возврат JSON с CORS-заголовками
    ↓
Frontend
    ↓
    6. Парсинг Esri/ArcGIS style JSON
    7. Преобразование в Leaflet.VectorGrid формат
    8. Применение к vectorTileLayerStyles
```

---

## Реализация

### Backend: `/api/vector_tile_style`

**Файл:** `server/map_server.py`

**Функционал:**
- Извлекает base URL из `map_tile_url` (до `/tile/`)
- Формирует URL стилей: `base_url/resources/styles/root.json`
- Сохраняет query string (токен) из tile_url
- Проксирует запрос с CORS-заголовками
- Обрабатывает 404 (стили не найдены) gracefully

**Пример преобразования URL:**

```python
# Входной tile_url:
https://api.maps.by/.../tile/{z}/{y}/{x}.pbf?token=ABC*123

# Извлекается base_url:
https://api.maps.by/...

# Формируется style_url:
https://api.maps.by/.../resources/styles/root.json?token=ABC*123
```

**Безопасность:**
- Токен маскируется в логах через `_mask_token_for_log()`
- CORS-заголовки добавляются для доступа из QWebEngineView
- Кэширование: 24 часа

---

### Frontend: Загрузка стилей

**Файл:** `templates/map.html`

**Алгоритм:**

1. **Запрос стилей:**
   ```javascript
   const styleResp = await fetch('/api/vector_tile_style');
   ```

2. **Парсинг Esri/ArcGIS style JSON:**
   ```javascript
   styleData.layers.forEach(layer => {
     const paint = layer.paint;
     const layerStyle = {};
     
     // Преобразование Mapbox GL → Leaflet.VectorGrid
     if (paint['fill-color']) layerStyle.fillColor = paint['fill-color'];
     if (paint['line-color']) layerStyle.color = paint['line-color'];
     if (paint['line-width']) layerStyle.weight = paint['line-width'];
     // ... и т.д.
     
     vectorTileStyles[layer.id] = layerStyle;
   });
   ```

3. **Fallback при ошибке:**
   ```javascript
   // Если стили не загрузились → используем generic styles
   if (!vectorTileStyles || Object.keys(vectorTileStyles).length === 0) {
     vectorTileStyles = {
       '*': {  // Применяется ко всем слоям
         weight: 1,
         color: '#3d8ef0',
         fillColor: '#1c2128',
         fillOpacity: 0.3,
       }
     };
   }
   ```

4. **Применение стилей:**
   ```javascript
   const vectorLayer = L.vectorGrid.protobuf(cfg.tile_url, {
     vectorTileLayerStyles: vectorTileStyles,  // ← Динамические стили
     interactive: false,
   });
   ```

---

## Поддерживаемые стили

### Mapbox GL / Esri ArcGIS → Leaflet.VectorGrid

| Esri/Mapbox стиль | Leaflet.VectorGrid | Описание |
|-------------------|---------------------|----------|
| `paint['fill-color']` | `fillColor` | Цвет заливки полигонов |
| `paint['fill-opacity']` | `fillOpacity` | Прозрачность заливки |
| `paint['line-color']` | `color` | Цвет линий |
| `paint['line-width']` | `weight` | Толщина линий |
| `paint['line-opacity']` | `opacity` | Прозрачность линий |

**Примечание:** Более сложные стили (градиенты, выражения, zoom-based) требуют дополнительной обработки.

---

## Обработка ошибок

| Сценарий | Поведение |
|----------|-----------|
| Стили успешно загружены | ✅ Применяются оригинальные стили сервера |
| HTTP 404 (стили не найдены) | ⚠️ Используется fallback (generic styles) |
| Timeout / Network error | ⚠️ Используется fallback |
| Некорректный JSON | ⚠️ Используется fallback |
| Неожиданный формат | ⚠️ Используется fallback |

**Важно:** Ошибки загрузки стилей **не блокируют** отображение карты.

---

## Логирование

### Backend
```
[vector_tile_style] GET https://api.maps.by/.../resources/styles/root.json?token=***XYZ
[vector_tile_style] Upstream HTTP 200 for https://api.maps.by/...?token=***XYZ
```

### Frontend
```
[loadTileLayer] Attempting to load vector tile styles...
[loadTileLayer] Processing 42 style layers...
[loadTileLayer] Styles loaded successfully: 42 layers
```

**Fallback:**
```
[loadTileLayer] Styles not available (HTTP 404), using fallback
[loadTileLayer] Using default fallback styles
```

---

## Тестирование

### Сценарий 1: Стили доступны

**URL:**
```
https://api.maps.by/.../tile/{z}/{y}/{x}.pbf?token=ABC*123
```

**Ожидается:**
- ✅ Запрос `/api/vector_tile_style` → HTTP 200
- ✅ Парсинг `root.json`
- ✅ Применение стилей к слоям
- ✅ Карта отображается с оригинальными цветами провайдера

---

### Сценарий 2: Стили недоступны (404)

**URL:**
```
https://custom-server.com/tiles/{z}/{x}/{y}.pbf
```

**Ожидается:**
- ⚠️ Запрос `/api/vector_tile_style` → HTTP 404
- ⚠️ Console: "Styles not available (HTTP 404), using fallback"
- ✅ Карта отображается с generic styles
- ✅ Функционал не нарушен

---

### Сценарий 3: Timeout

**Условие:** Медленная сеть / провайдер не отвечает

**Ожидается:**
- ⚠️ Timeout после 10 секунд
- ⚠️ Console: "Failed to load styles, using fallback"
- ✅ Карта отображается с generic styles

---

## Совместимость

| Провайдер | URL стилей | Статус |
|-----------|-----------|--------|
| api.maps.by (Esri) | `.../resources/styles/root.json` | ✅ Поддерживается |
| Mapbox | Mapbox API | ⚠️ Требует адаптации |
| OpenMapTiles | Mapbox GL compatible | ⚠️ Требует адаптации |
| Пользовательские | Зависит от сервера | ⚠️ Fallback к generic |

---

## Ограничения

1. **Простые стили только:** Поддерживаются базовые свойства (`color`, `fillColor`, `weight`). Сложные выражения, фильтры, zoom-based стили требуют доп. обработки.

2. **Esri/ArcGIS формат:** Endpoint рассчитан на структуру `.../resources/styles/root.json`. Другие провайдеры могут использовать иные пути.

3. **Статичные стили:** Стили применяются один раз при загрузке. Динамическое изменение стилей (например, при смене темы) не реализовано.

---

## Дальнейшие улучшения

### Возможные доработки:

1. **Поддержка Mapbox style spec:**
   - Парсинг `sprite`, `glyphs`
   - Обработка `zoom` expressions
   - Поддержка `filter`

2. **Кэширование стилей:**
   - Сохранение в localStorage
   - Избежание повторных запросов

3. **UI настройка:**
   - Кнопка "Обновить стили"
   - Выбор между оригинальными/generic стилями

4. **Продвинутая диагностика:**
   - Показ в UI: "Стили загружены: 42 слоя"
   - Предупреждение при fallback

---

## Итог

✅ **Реализовано:**
- Автоматическая загрузка стилей с сервера
- Проксирование с CORS-заголовками
- Преобразование Esri/Mapbox → Leaflet
- Graceful fallback при ошибках
- Маскирование токена в логах

✅ **Совместимость:**
- api.maps.by — полностью поддерживается
- Другие провайдеры — работает fallback
- Существующий функционал не нарушен

✅ **Безопасность:**
- Токен не раскрывается в логах
- CORS корректно настроен
- Timeout 10 секунд
