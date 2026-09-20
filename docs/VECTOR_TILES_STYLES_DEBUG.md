# Диагностика: Почему стили не загружаются

**Дата:** 2026-09-15 14:51  
**Статус:** Добавлено детальное логирование

---

## Что добавлено

### 1. Детальное логирование в backend
- Показывает оригинальный `tile_url`
- Показывает извлечённый `base_url`
- Показывает количество попыток загрузки
- Для каждой попытки:
  - HTTP статус
  - Content-Type
  - Размер ответа в байтах
  - Ключи JSON (если парсится)
  - Первые 200 символов при ошибке парсинга

### 2. Headers для запросов
Добавлены headers, которые могут требовать некоторые серверы:
```python
headers = {
    'User-Agent': 'Mozilla/5.0 ...',
    'Accept': 'application/json, */*'
}
```

---

## Как диагностировать

### Шаг 1: Запустите приложение
```bash
python main.py
```

### Шаг 2: Откройте карту с векторными тайлами

### Шаг 3: Проверьте логи backend

Ищите строки с `[vector_tile_style]`:

#### Пример успешной загрузки:
```
[vector_tile_style] Original tile_url: https://api.maps.by/.../tile/{z}/{y}/{x}.pbf?token=***y6
[vector_tile_style] Extracted base_url: https://api.maps.by/...?token=***y6
[vector_tile_style] Will try 2 paths
[vector_tile_style] [1/2] Trying: https://api.maps.by/.../resources/styles?token=***y6
[vector_tile_style] Response: HTTP 200, Content-Type: application/json, Size: 12345 bytes
[vector_tile_style] JSON parsed successfully, type: <class 'dict'>
[vector_tile_style] Style keys: ['version', 'layers', 'sources', ...]
[vector_tile_style] ✅ SUCCESS: Found valid styles
```

#### Пример ошибки 404:
```
[vector_tile_style] [1/2] Trying: https://api.maps.by/.../resources/styles?token=***y6
[vector_tile_style] Response: HTTP 404, Content-Type: text/html, Size: 1234 bytes
[vector_tile_style] 404 Not Found at ...
[vector_tile_style] [2/2] Trying: https://api.maps.by/.../VectorTileServer/resources/styles?token=***y6
[vector_tile_style] Response: HTTP 404, Content-Type: text/html, Size: 1234 bytes
[vector_tile_style] ⚠️ Styles not found at any known path
```

#### Пример ошибки 401/403 (токен):
```
[vector_tile_style] Response: HTTP 401, Content-Type: application/json, Size: 123 bytes
[vector_tile_style] HTTP 401 at ...
```

#### Пример неправильного JSON:
```
[vector_tile_style] Response: HTTP 200, Content-Type: text/html, Size: 5678 bytes
[vector_tile_style] Failed to parse JSON: ...
[vector_tile_style] Response preview: <!DOCTYPE html><html>...
```

---

## Шаг 4: Интерпретация логов

### Сценарий A: HTTP 404 на всех путях
**Проблема:** Сервер не отдаёт стили по стандартным путям.

**Решение:**
1. Проверьте документацию api.maps.by для вашего конкретного сервиса
2. Возможно, у вас ограниченный API без доступа к стилям
3. Сообщите мне точные URL'ы из логов — добавлю альтернативные пути

---

### Сценарий B: HTTP 401 / 403
**Проблема:** Токен не работает для endpoint стилей.

**Возможные причины:**
- Токен валиден только для `/tile/`, но не для `/resources/`
- Токен просрочен
- Нужны другие параметры авторизации

**Решение:**
1. Проверьте в личном кабинете api.maps.by права доступа
2. Возможно, нужен другой токен для metadata/styles
3. Попробуйте получить новый токен

---

### Сценарий C: HTTP 200, но не JSON
**Проблема:** Сервер возвращает HTML вместо JSON.

**Пример:**
```
Response preview: <!DOCTYPE html><html><head><title>404...
```

**Решение:**
- Это 404, замаскированный под 200 (плохая практика сервера)
- Смотрите "Сценарий A"

---

### Сценарий D: HTTP 200, JSON, но пустой или неожиданный формат
**Проблема:** Сервер возвращает JSON, но он не содержит `layers`, `sources`, `version`.

**Пример лога:**
```
Style keys: ['error', 'message']
Empty or invalid style format
```

**Решение:**
1. Проверьте, какие ключи возвращаются (из лога)
2. Сообщите мне — возможно, формат отличается от стандарта
3. Я адаптирую парсер

---

### Сценарий E: Timeout
**Проблема:** Сервер не отвечает в течение 10 секунд.

**Решение:**
1. Проверьте интернет-соединение
2. Попробуйте позже — сервер может быть перегружен
3. Если повторяется — сообщите, увеличу timeout

---

## Шаг 5: Проверка консоли браузера

Откройте DevTools (F12) → Console:

### Если стили загрузились:
```
[loadTileLayer] Attempting to load vector tile styles...
[loadTileLayer] Processing N style layers...
[loadTileLayer] Styles loaded successfully: N layers
```

### Если стили не загрузились:
```
[loadTileLayer] Styles not available (HTTP 404), using fallback
[loadTileLayer] Using default fallback styles
```

---

## Что сообщить мне

Если стили не загрузились, пришлите:

1. **Логи backend** (все строки с `[vector_tile_style]`)
2. **Точный URL тайлов** (можно замаскировать токен)
3. **Консоль браузера** (строки с `[loadTileLayer]`)

Это поможет понять, почему сервер не отдаёт стили.

---

## Временное решение

Если стили не загружаются, карта всё равно работает с fallback-стилями (упрощённый синий вид).

Это не критично — все функции доступны, просто визуально не так красиво.

---

## Проверка синтаксиса

```bash
py -m py_compile server/map_server.py  # ✅ exit 0
```

---

## Следующий шаг

Запустите приложение и пришлите логи backend из консоли.
