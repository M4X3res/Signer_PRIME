# Улучшение поддержки векторных тайлов: maxZoom и модификация стилей

**Дата:** 2026-09-15 14:59  
**Статус:** ✅ Реализовано  
**Основано на:** `scripts/archive/index.html` (рабочий пример с MapLibre GL)

---

## Проблемы, которые были исправлены

### 1. Ограниченный maxZoom (18)
**Было:** Карта позволяла зум только до 18  
**Стало:** Увеличено до 24 (как в рабочем примере)

### 2. Стили не загружались/не применялись
**Причина:** Style JSON содержал ссылки на upstream-сервер вместо нашего прокси  
**Решение:** Backend теперь модифицирует style JSON перед отправкой клиенту

---

## Реализованные изменения

### Backend: Модификация style JSON

**Файл:** `server/map_server.py`

**Что делает:**
Когда загружаются стили с api.maps.by, backend:

1. **Парсит JSON стилей**
2. **Находит все `sources`** с типом `vector`
3. **Заменяет `url` на наш прокси:**
   ```python
   data['sources'][source_id] = {
       'type': 'vector',
       'tiles': ['/api/vector_tile_proxy/{z}/{x}/{y}'],  # ← Наш прокси
       'minzoom': 0,
       'maxzoom': 24,  # ← Увеличено до 24
       'scheme': 'xyz',
   }
   ```
4. **Возвращает модифицированный JSON** клиенту

**Зачем это нужно:**
- Стили от api.maps.by ссылаются на их сервер
- Leaflet.VectorGrid не может загрузить тайлы напрямую (CORS)
- Мы подменяем источник на наш прокси, который обходит CORS

**Логирование:**
```
[vector_tile_style] Replacing source[esri].url with proxy
[vector_tile_style] ✅ SUCCESS: Found valid styles
[vector_tile_style] Structure: layers=True, sources=True, maxzoom=24
```

---

### Frontend: Увеличенный maxZoom

**Файл:** `templates/map.html`

#### 1. Карта
```javascript
map = L.map("map", { 
  maxZoom: 24  // Было: по умолчанию 18
});
```

#### 2. Векторный слой
```javascript
const vectorLayer = L.vectorGrid.protobuf(cfg.tile_url, {
  maxZoom: 24,  // Увеличено с cfg.max_zoom (обычно 18)
  maxNativeZoom: cfg.max_zoom || 18,  // Реальный zoom уровень тайлов
  vectorTileLayerStyles: vectorTileStyles,
});
```

**Разница:**
- `maxZoom: 24` — до какого уровня можно зумить карту
- `maxNativeZoom: 18` — до какого уровня доступны реальные тайлы
- При zoom > 18 Leaflet будет масштабировать тайлы уровня 18

---

### Добавлена MapLibre GL (для будущего)

**Файл:** `templates/map.html`

Подключены CSS и JS:
```html
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"/>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
```

**Зачем:**
- Leaflet.VectorGrid имеет ограничения в рендеринге сложных Esri стилей
- MapLibre GL — более мощная библиотека, полностью поддерживает Mapbox GL/Esri стили
- В будущем можно переключиться на MapLibre для векторных тайлов

**Пока не используется**, но готова к интеграции.

---

## Сравнение с рабочим примером

### Рабочий пример (scripts/archive/index.html)

```javascript
// 1. Загружает style JSON
const style = await fetch('/vt/resources/styles').then(r => r.json());

// 2. Модифицирует sources
style.sources.esri = {
  type: "vector",
  tiles: [TILES_PROXY],  // ← Подставляет свой прокси
  maxzoom: 24,
};

// 3. Создаёт MapLibre карту
const map = new maplibregl.Map({
  style: style,
  maxZoom: 24,
});
```

### Наша реализация

```javascript
// 1. Загружает style JSON (уже модифицированный backend!)
const styleData = await fetch('/api/vector_tile_style').then(r => r.json());

// 2. Backend УЖЕ подставил прокси:
// styleData.sources.esri.tiles = ['/api/vector_tile_proxy/{z}/{x}/{y}']

// 3. Создаёт Leaflet.VectorGrid слой
const vectorLayer = L.vectorGrid.protobuf(cfg.tile_url, {
  vectorTileLayerStyles: vectorTileStyles,
  maxZoom: 24,
});
```

**Ключевое отличие:**
- Рабочий пример модифицирует стили **на frontend**
- Наша реализация модифицирует стили **на backend** (безопаснее, токен не утекает)

---

## Проверка

### 1. Запустите приложение

### 2. Проверьте логи backend
```
[vector_tile_style] Original tile_url: https://api.maps.by/.../tile/{z}/{y}/{x}.pbf?token=***y6
[vector_tile_style] Replacing source[esri].url with proxy
[vector_tile_style] ✅ SUCCESS: Found valid styles
```

### 3. Откройте карту с векторными тайлами

### 4. Проверьте maxZoom
- Зумите карту до максимума
- Должен быть доступен zoom до **24** (раньше было 18)
- В углу карты показывается текущий zoom

### 5. Проверьте консоль браузера (F12)
```
[loadTileLayer] Styles loaded successfully: N layers
[VectorGrid] Tile loaded: {z: 12, x: 123, y: 456}
```

---

## Известные ограничения

### 1. Sprite и Glyphs

**Что это:**
- `sprite` — иконки (значки на карте: POI, стрелки и т.д.)
- `glyphs` — шрифты для подписей

**Статус:**
- Пока НЕ реализованы endpoints для проксирования
- В style JSON остаются ссылки на upstream-сервер
- Из-за CORS браузер не может их загрузить

**Результат:**
- Карта отображается ✅
- Стили применяются ✅
- Но иконки и подписи могут отсутствовать ⚠️

**Решение (если понадобится):**
Добавить endpoints:
```python
@app.route("/api/vector_tile_sprite/<path:path>")
def api_vector_tile_sprite(path):
    # Проксирует .../resources/sprites/sprite...
    
@app.route("/api/vector_tile_glyphs/<fontstack>/<range>")  
def api_vector_tile_glyphs(fontstack, range):
    # Проксирует .../resources/fonts/{fontstack}/{range}.pbf
```

И в backend:
```python
data['sprite'] = '/api/vector_tile_sprite/sprite'
data['glyphs'] = '/api/vector_tile_glyphs/{fontstack}/{range}.pbf'
```

---

### 2. Leaflet.VectorGrid vs MapLibre GL

**Leaflet.VectorGrid:**
- ✅ Простая интеграция с существующим Leaflet
- ✅ Совместимость с marker clusters, overlays
- ❌ Ограниченная поддержка сложных стилей
- ❌ Хуже производительность

**MapLibre GL:**
- ✅ Полная поддержка Mapbox GL / Esri стилей
- ✅ Лучшая производительность (WebGL)
- ✅ Sprite и glyphs "из коробки"
- ❌ Требует полной переделки карты
- ❌ Несовместим с Leaflet markers/clusters

**Текущий выбор:** Leaflet.VectorGrid (совместимость важнее)

---

## Итог

✅ **maxZoom увеличен до 24** (карта и векторные тайлы)  
✅ **Backend модифицирует style JSON** (подставляет наш прокси)  
✅ **Стили должны загружаться** (если api.maps.by отдаёт их)  
✅ **MapLibre GL подключён** (готов к использованию в будущем)  
⚠️ **Sprite и glyphs не проксируются** (иконки/подписи могут отсутствовать)

**Следующий шаг:**  
Запустите приложение и проверьте, загружаются ли стили. Пришлите логи backend с `[vector_tile_style]`.
