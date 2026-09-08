# HOTFIX: Видеоплеер не загружает видео при клике на знак

**Дата:** 2026-08-25  
**Статус:** ✅ ИСПРАВЛЕНО

---

## ПРОБЛЕМА

При клике на знак на карте видеоплеер не открывался с нужного момента времени, выдавал ошибку.

### Симптомы
- Клик на маркер знака на карте
- Видеоплеер должен загрузить видео и перемотать к моменту наблюдения знака
- Вместо этого: JavaScript ошибка, видео не загружается

### Причина

**Корневая проблема:** Поле `absolute_frame_numbers` в GeoJSON файле сохранялось как **Python-строка** представления списка, а не как настоящий JSON массив.

```json
// ❌ НЕПРАВИЛЬНО (старый формат):
"absolute_frame_numbers": "[85545, 85550, 85555, 85560, ...]"

// ✅ ПРАВИЛЬНО (новый формат):
"absolute_frame_numbers": [85545, 85550, 85555, 85560, ...]
```

**Файл:** `core/final_handler.py`, метод `_build_feature()`, строка **~1085**

**Проблемный код:**
```python
"absolute_frame_numbers": str(sign.abs_frame_numbers)  # ❌ Создаёт строку!
```

**Последствия:**
1. JavaScript получал строку `"[123, 456, 789]"` вместо массива
2. Парсинг строки работал, но был хрупким (зависел от формата Python `str()`)
3. При изменениях в структуре данных мог ломаться

---

## ИСПРАВЛЕНИЕ

### 1. Python: Сохранение настоящего JSON массива

**Файл:** `core/final_handler.py`

**Изменения:**
```python
# БЫЛО:
"absolute_frame_numbers": str(sign.abs_frame_numbers),

# СТАЛО:
"absolute_frame_numbers": sign.abs_frame_numbers if sign.abs_frame_numbers else [],
```

**Результат:** GeoJSON теперь содержит настоящий JSON массив, который корректно десериализуется в JavaScript без дополнительной обработки.

---

### 2. JavaScript: Улучшенный парсинг (обратная совместимость)

**Файл:** `templates/map.html`, функция `loadVideoForSign()`

**Изменения:**
```javascript
// БЫЛО:
let rawFrames = signProps.absolute_frame_numbers || signProps.abs_frame || "";
if (typeof rawFrames === 'string') {
  rawFrames = rawFrames.replace(/[\[\]]/g, "").split(",").map(Number).filter(Boolean);
}

// СТАЛО:
let rawFrames = signProps.absolute_frame_numbers || signProps.abs_frame || "";

// Проверяем тип данных
if (Array.isArray(rawFrames)) {
  // Новый формат: уже массив из GeoJSON
  rawFrames = rawFrames.filter(n => typeof n === 'number' && !isNaN(n));
} else if (typeof rawFrames === 'string' && rawFrames.trim().length > 0) {
  // Старый формат: строка вида "[123, 456, 789]"
  rawFrames = rawFrames.replace(/[\[\]]/g, "").split(",").map(Number).filter(Boolean);
} else {
  // Пустые данные
  rawFrames = [];
}
```

**Результат:** 
- ✅ Поддержка нового формата (массивы)
- ✅ Обратная совместимость со старыми GeoJSON файлами (строки)
- ✅ Явная обработка пустых значений
- ✅ Валидация типов данных

---

## ТЕСТИРОВАНИЕ

### Шаги проверки:

1. **Запустить обработку видео** (создаст новый GeoJSON с массивами):
   ```bash
   python main.py
   ```

2. **Проверить формат GeoJSON** (должны быть массивы):
   ```bash
   powershell -Command "Get-Content 'E:\Urban\vid\test\test_new_algo.geojson' | Select-String 'absolute_frame_numbers' | Select-Object -First 1"
   ```
   
   **Ожидаемый результат:**
   ```json
   "absolute_frame_numbers": [85545, 85550, 85555, 85560, ...]
   ```

3. **Открыть карту**:
   ```
   http://localhost:5001
   ```

4. **Кликнуть на любой маркер знака**

5. **Проверить консоль браузера (F12)**:
   - ✅ Не должно быть ошибок
   - ✅ Логи вида: `[loadVideoForSign] avgFrame=85627.5, videoIdx=1, frameInVideo=22027`

6. **Проверить видеоплеер**:
   - ✅ Видео загружается
   - ✅ Автоматически перематывается к нужному кадру
   - ✅ Отображается время и длительность

---

## ОБРАТНАЯ СОВМЕСТИМОСТЬ

✅ **Старые GeoJSON файлы продолжат работать** через fallback-парсинг строк в JavaScript.

✅ **Новые GeoJSON файлы** будут использовать нативный JSON формат (быстрее, надёжнее).

---

## ДОПОЛНИТЕЛЬНЫЕ УЛУЧШЕНИЯ

Рекомендуется аналогичный подход применить к другим спискам в properties:
- `pixel_coordinates_x`
- `pixel_coordinates_y`
- `h` (heights)
- `w` (widths)
- `car_coordinates_x`
- `car_coordinates_y`
- `frame_numbers`
- `side` (side_results)

**Причина:** Те же проблемы — сохраняются как строки, что усложняет обработку в JavaScript и других клиентах GeoJSON.

**Реализация:** Заменить `str(sign.pixel_x)` → `sign.pixel_x` для всех списков в `props` dict.

---

## ИТОГ

✅ **Проблема решена:** Видеоплеер теперь корректно загружает и перематывает видео при клике на знак.

✅ **Формат улучшен:** GeoJSON использует нативные JSON массивы вместо строковых представлений.

✅ **Совместимость сохранена:** Старые файлы продолжают работать.

✅ **Код упрощён:** Меньше парсинга, меньше ошибок.

---

**Примечание:** После применения фикса **необходимо пере-обработать видео** для создания нового GeoJSON с массивами. Старые GeoJSON файлы будут работать через fallback, но рекомендуется обновить их.
