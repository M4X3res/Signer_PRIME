# Исправление загрузки стилей для api.maps.by

**Дата:** 2026-09-15 14:35  
**Статус:** ✅ Исправлено

---

## Проблема

Стили не загружались, так как код пытался искать их по неправильному пути.

### Неправильный путь (было):
```
https://api.maps.by/api/vectorTile/VectorTileServer/resources/styles?token=...
                                    ^^^^^^^^^^^^^^^^^^^^ лишнее!
```

### Правильный путь (стало):
```
https://api.maps.by/api/vectorTile/resources/styles?token=...
                                    ^^^^^^^^^^ без /VectorTileServer/
```

---

## Что исправлено

**Файл:** `server/map_server.py`

**Было:**
```python
base_url = tile_url.split('/VectorTileServer/tile/')[0] + '/VectorTileServer'
#                                                           ^^^^^^^^^^^^^^^^^^
#                                                           ОШИБКА: добавляли обратно
```

**Стало:**
```python
base_url = tile_url.split('/VectorTileServer/tile/')[0]
# Результат: https://api.maps.by/api/vectorTile (без /VectorTileServer)
```

---

## Логика извлечения

### Ваш URL тайлов:
```
https://api.maps.by/api/vectorTile/VectorTileServer/tile/{z}/{y}/{x}.pbf?token=ABC*123
```

### Шаги обработки:

1. **Разделяем по `/VectorTileServer/tile/`:**
   ```
   base_url = "https://api.maps.by/api/vectorTile"
   ```

2. **Извлекаем токен:**
   ```
   query_string = "?token=ABC*123"
   ```

3. **Формируем URL стилей (приоритет):**
   ```
   ✅ Попытка 1: https://api.maps.by/api/vectorTile/resources/styles?token=ABC*123
   ⚠️ Попытка 2: https://api.maps.by/api/vectorTile/VectorTileServer/resources/styles?token=ABC*123
   ```

4. **Первая успешная попытка возвращается клиенту**

---

## Проверка синтаксиса

```bash
py -m py_compile server/map_server.py  # ✅ exit 0
```

---

## Как проверить

1. **Запустите приложение**
2. **Откройте карту** с векторными тайлами api.maps.by
3. **Проверьте логи backend:**
   ```
   [vector_tile_style] Trying: https://api.maps.by/.../resources/styles?token=***y6
   [vector_tile_style] ✅ SUCCESS: Found valid styles at ...
   [vector_tile_style] Style keys: ['version', 'layers', 'sources', ...]
   ```

4. **Проверьте консоль браузера (F12):**
   ```
   [loadTileLayer] Attempting to load vector tile styles...
   [loadTileLayer] Processing N style layers...
   [loadTileLayer] Styles loaded successfully: N layers
   ```

5. **Карта должна отображаться с оригинальными стилями** (дороги, здания, вода в правильных цветах)

---

## Если стили всё ещё не загружаются

### Проверьте логи backend на:
- `404` - неправильный путь (сообщите мне точный URL)
- `401/403` - проблема с токеном
- `Timeout` - сетевые проблемы

### Проверьте консоль браузера на:
- `Failed to load styles` - ошибка при парсинге JSON
- `using fallback` - стили не найдены, используется упрощённый вид

---

## Дополнительные варианты

Если стандартные пути не работают, код автоматически пробует:
1. `.../resources/styles` ← основной для api.maps.by
2. `.../VectorTileServer/resources/styles` ← запасной
3. `.../resources/styles/root.json` ← альтернативный формат
4. `.../styles/root.json` ← для других провайдеров

---

## Итог

✅ **Путь к стилям исправлен** согласно документации api.maps.by  
✅ **Токен с `*` поддерживается** (после предыдущего исправления)  
✅ **Graceful fallback** при ошибках  
✅ **Логирование** для диагностики

**Следующий шаг:** Запустите приложение и проверьте загрузку стилей.
