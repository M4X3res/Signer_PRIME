# PROMPT: Поддержка векторных тайлов (.pbf) в настройках карты

## Контекст

Карта приложения (`templates/map.html`) сейчас рендерит подложку через
обычный Leaflet `L.tileLayer`, который умеет грузить только **растровые**
тайлы (PNG/JPEG) по шаблону URL с плейсхолдерами `{z}/{x}/{y}`. Источник
подложки настраивается пользователем в UI (`ui/widgets/settings_page.py`,
группа "Карта" → поле "URL тайлов") и хранится в
`configs/settings.py::AppSettings.map_tile_url`.

Некоторые провайдеры (например, api.maps.by) отдают подложку в виде
**векторных тайлов** формата Mapbox Vector Tiles (`.pbf`), например:

```
http://api.maps.by/api/vectorTile/VectorTileServer/tile/{z}/{y}/{x}.pbf?token=...
```

Такие тайлы — не картинка, а сжатая геометрия + атрибуты, которую нужно
самостоятельно стилизовать и отрисовывать на клиенте. Текущий код молча
не работает с ними: `L.tileLayer` либо ничего не покажет, либо покажет
мусор.

Нужно добавить полноценную поддержку такого типа подложек, не сломав
существующий растровый путь (он должен остаться дефолтным и работать
как раньше).

## КРИТИЧЕСКИЕ ОГРАНИЧЕНИЯ

- НЕ трогать пайплайн обработки видео/знаков: `core/`, `processing/`,
  `licensing/`.
- НЕ менять порт карты (3000) и общую архитектуру ServerThread/Flask.
- Обратная совместимость: у пользователей, которые уже сохранили
  растровый `map_tile_url` (например, OSM `{s}.tile.openstreetmap.org`),
  после апдейта карта должна продолжать работать без каких-либо
  дополнительных действий с их стороны (дефолт = raster).
- Полностью оффлайн-режим (без интернета для CDN) не требуется, но
  подключаемую библиотеку для векторных тайлов нужно грузить так же,
  как остальные (через `<script src="https://unpkg.com/...">` в
  `templates/map.html`, по аналогии с leaflet/leaflet.markercluster).

## Задача 1 — Настройки: тип подложки

В `configs/settings.py::AppSettings` добавить новое поле:

```python
map_tile_type: Literal["raster", "vector"] = "raster"
```

Разместить рядом с существующими `map_tile_url`, `map_tile_attribution`,
`map_tile_max_zoom`. Убедиться, что `load()`/`save()`/`to_dict()`/
`from_dict()` подхватывают новое поле автоматически (они работают через
`__dataclass_fields__`/`asdict`, так что отдельного кода не требуется —
но проверь это).

В `ui/widgets/settings_page.py`, группа `SettingsGroup("Карта")`:
- добавить `QComboBox` с двумя пунктами: "Растровые тайлы (PNG/JPG)" и
  "Векторные тайлы (.pbf, Mapbox Vector Tiles)";
- текущее значение — из `self._settings.map_tile_type`;
- применить `connect_combobox_theme_updates()` как для остальных
  комбобоксов на странице (см. `_theme_combo`, `_cpu_backend_combo`);
- добавить строку в группу через `map_group.add_row(...)` **перед**
  строкой "URL тайлов", с понятной подсказкой (hint), что для
  векторных тайлов URL должен содержать `{z}/{x}/{y}` (или `{y}/{x}`,
  в зависимости от провайдера) и подсказать, что порядок X/Y может
  отличаться от растровых серверов — уточни это в hint текстом вроде
  "Для некоторых провайдеров (в т.ч. api.maps.by) порядок координат
  в пути — z/y/x, а не z/x/y — сверьтесь с документацией провайдера";
- в `_collect_settings()` и `_reset()` (и в `_import_settings()`, если
  там уже сериализуются map_tile_* поля) добавить чтение/запись нового
  комбобокса, по аналогии с `_cpu_backend_combo`.

## Задача 2 — Сервер: отдавать тип подложки в /api/map_config

В `server/map_server.py::api_map_config()` добавить в ответ JSON поле
`tile_type`:

```python
return jsonify({
    "tile_url": settings.map_tile_url,
    "attribution": settings.map_tile_attribution,
    "max_zoom": settings.map_tile_max_zoom,
    "tile_type": settings.map_tile_type,   # NEW: "raster" | "vector"
})
```

В fallback-ветке (`except Exception`) тоже добавить `"tile_type": "raster"`,
чтобы при ошибке карта гарантированно откатывалась на растровый OSM.

## Задача 3 — Фронтенд: рендер векторных тайлов

### 3.1. Подключить библиотеку для .pbf

В `<head>` `templates/map.html`, рядом с существующими `<script>` для
leaflet/markercluster, добавить **Leaflet.VectorGrid**
(https://github.com/Leaflet/Leaflet.VectorGrid) — она достаточно лёгкая,
не требует WebGL (в отличие от MapLibre GL JS) и хорошо интегрируется с
уже используемым `L.tileLayer`-подходом:

```html
<script src="https://unpkg.com/leaflet.vectorgrid@1.3.0/dist/Leaflet.VectorGrid.bundled.js"></script>
```

Не заменяй существующий `leaflet.js`/`leaflet.markercluster` — они
остаются, просто добавляется ещё один `<script>`.

### 3.2. Обновить `loadTileLayer()`

Сейчас:

```js
async function loadTileLayer() {
  try {
    const resp = await fetch('/api/map_config');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const cfg = await resp.json();

    L.tileLayer(cfg.tile_url, {
      attribution: cfg.attribution,
      maxZoom: cfg.max_zoom,
    }).addTo(map);
  } catch (err) {
    console.error('Failed to load map config, using fallback OSM:', err);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);
  }
}
```

Нужно:

1. Ветвиться по `cfg.tile_type`.
2. Для `"vector"` — создавать `L.vectorGrid.protobuf(cfg.tile_url, {...})`
   вместо `L.tileLayer`.
3. Обязательно передать `vectorTileLayerStyles` — без явных стилей
   VectorGrid ничего не нарисует (у векторных тайлов нет своего вида,
   это только геометрия + слои с именами вроде `water`, `roads`,
   `buildings`, `landuse` — имена слоёв зависят от схемы провайдера и
   их нужно будет подобрать опытным путём/из документации провайдера).
   Сделай styles настраиваемыми через один "универсальный" fallback-стиль
   (`{ '*': genericStyleFn }` — VectorGrid поддерживает `'*'` как стиль
   по умолчанию для всех слоёв, если конкретные имена слоёв неизвестны),
   чтобы код не был жёстко привязан к схеме одного провайдера.
4. Если `L.vectorGrid` не определён (библиотека не подгрузилась —
   например, нет интернета) — логировать ошибку в консоль и откатываться
   на дефолтный растровый OSM-слой (как в текущем catch-блоке), а не
   падать молча с пустой картой.
5. Attribution и maxZoom применяются так же, как для растрового слоя.

Пример структуры (адаптируй под реальный API VectorGrid, проверь по
документации библиотеки):

```js
async function loadTileLayer() {
  try {
    const resp = await fetch('/api/map_config');
    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
    const cfg = await resp.json();

    if (cfg.tile_type === 'vector') {
      if (typeof L.vectorGrid === 'undefined') {
        throw new Error('Leaflet.VectorGrid library not loaded');
      }
      const genericStyle = {
        weight: 1,
        color: '#3d8ef0',
        fillColor: '#1c2128',
        fillOpacity: 0.3,
      };
      L.vectorGrid.protobuf(cfg.tile_url, {
        attribution: cfg.attribution,
        maxZoom: cfg.max_zoom,
        vectorTileLayerStyles: { '*': genericStyle },
        interactive: false,
      }).addTo(map);
    } else {
      L.tileLayer(cfg.tile_url, {
        attribution: cfg.attribution,
        maxZoom: cfg.max_zoom,
      }).addTo(map);
    }
  } catch (err) {
    console.error('Failed to load map config, using fallback OSM:', err);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
      maxZoom: 19,
    }).addTo(map);
  }
}
```

### 3.3. Инверсия тёмной темы

Сейчас в CSS для растровых тайлов применяется фильтр инверсии/оттенков
под тёмную тему:

```css
.leaflet-tile {
  filter: brightness(0.55) contrast(1.1) saturate(0.7) hue-rotate(180deg) invert(1);
}
```

Этот CSS-фильтр рассчитан на `<img>`-тайлы (`.leaflet-tile`) и не
применяется к canvas/svg-рендерингу VectorGrid. Проверь, как VectorGrid
рендерится в данной версии (canvas по умолчанию), и либо:
- подбери отдельные тёмные/светлые цвета прямо в `vectorTileLayerStyles`
  (предпочтительно — через `body.theme-light` детектировать текущую
  тему при инициализации слоя и выбрать соответствующую палитру), либо
- если рендер идёт через canvas с классом, которому можно назначить
  фильтр, — добавь отдельное CSS-правило для векторного слоя.
Не оставляй ситуацию, когда векторная подложка в тёмной теме выглядит
белой/нечитаемой.

## Задача 4 — Тест/валидация URL в настройках (опционально, но желательно)

В `ui/widgets/settings_page.py` при сохранении (`_save()`) добавь мягкую
проверку: если выбран `map_tile_type == "vector"`, а введённый URL
заканчивается на `.png`/`.jpg`/`.jpeg`, или наоборот `map_tile_type ==
"raster"`, а URL заканчивается на `.pbf`, `.mvt` — показать
предупреждение (`QMessageBox.warning`, не блокирующее сохранение,
аналогично `_check_backend_readiness()`), чтобы пользователь не
попадал в ситуацию "выбрал не тот тип и не понимает почему карта пустая".

## Задача 5 — Документация

Обнови (или создай) `docs/` заметку о настройке подложки карты:
кратко опиши оба режима, для векторного — пример URL с плейсхолдерами
(`{z}/{x}/{y}` или `{z}/{y}/{x}` — с явной пометкой, что нужно уточнять
порядок у провайдера) и предупреждение про формат токена в URL
(некоторые провайдеры используют `&`, которые ломаются при копировании
из некоторых источников — то есть нужно убедиться, что весь query-string
скопирован и корректно urlencoded).

## Критерии приёмки

1. Существующие сохранённые настройки (`map_tile_type` отсутствует в
   старом сохранённом `QSettings`) продолжают открывать карту как
   растровую подложку — без изменений в поведении.
2. В UI настроек можно переключить тип подложки на "Векторные тайлы",
   ввести URL с плейсхолдерами `{z}/{x}/{y}` и сохранить — карта после
   перезапуска/перезагрузки грузит `L.vectorGrid.protobuf(...)`.
3. Если библиотека VectorGrid не загрузилась или векторный URL
   недоступен — карта откатывается на дефолтный OSM-растр, приложение
   не падает и не показывает пустой белый/чёрный экран без объяснения
   (см. `console.error`).
4. `/api/map_config` возвращает поле `tile_type` во всех ветках
   (успех и fallback при ошибке).
5. Тёмная тема не делает векторную подложку нечитаемой.
6. Не затронуты `core/`, `processing/`, `licensing/`, порт 3000 и общая
   структура Flask/SocketIO сервера.
