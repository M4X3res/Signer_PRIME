# ✅ ИСПРАВЛЕНО: Логи FinalHandler теперь попадают в roadscan.log

**Дата:** 2026-08-24  
**Проблема:** Логи о сохранении GeoJSON не попадали в roadscan.log  
**Причина:** Использовался `print()` вместо `logging.getLogger()`

---

## Что было исправлено

### Проблема
```python
# ❌ Старый код
print(f"[FinalHandler] save_result вызван:")
print(f"  - Знаков: {len(result_signs)}")
print(f"[FinalHandler] Сохранено {len(features)} знаков → {path}")
```

**Симптомы:**
- Логи о сохранении видны только в консоли (если есть)
- В `roadscan.log` НЕТ строк от FinalHandler
- Невозможно диагностировать проблемы с сохранением GeoJSON

---

### Решение
```python
# ✅ Новый код
import logging
logger = logging.getLogger(__name__)

logger.info(f"[FinalHandler] save_result вызван:")
logger.info(f"  - Знаков: {len(result_signs)}")
logger.info(f"[FinalHandler] Сохранено {len(features)} знаков → {path}")
```

---

## Изменения

### 1. Добавлен logger в core/final_handler.py
```python
import logging
logger = logging.getLogger(__name__)
```

### 2. Заменены все print() на logger
- `print("[FinalHandler] ...")` → `logger.info("[FinalHandler] ...")`
- `print(f"[FinalHandler] ОШИБКА ...")` → `logger.error(f"[FinalHandler] ОШИБКА ...")`
- `print(f"[FinalHandler] ВНИМАНИЕ ...")` → `logger.warning(f"[FinalHandler] ВНИМАНИЕ ...")`

**Всего заменено:** ~30 вызовов print()

### 3. Исправлена сигнатура _build_feature()
```python
# Было несоответствие:
self._build_feature(sign, x1, y1, x2, y2)  # одни места
self._build_feature(x1, y1, x2, y2, sign)  # другие места

# Стало единообразно:
self._build_feature(x1, y1, x2, y2, sign)  # везде
```

---

## Что теперь видно в логах

### После обработки в roadscan.log будет:
```
09:41:45 [INFO] core.final_handler: [FinalHandler] Инициализирован: DEDUP_RADIUS_M=30.0m, DEDUP_AZIMUTH_DEG=15.0°
09:41:45 [INFO] core.final_handler: [FinalHandler] save_result вызван:
09:41:45 [INFO] core.final_handler:   - Знаков: 83
09:41:45 [INFO] core.final_handler:   - Поворотов: 0
09:41:45 [INFO] core.final_handler:   - Путь: C:\Users\...\output.geojson
09:41:45 [INFO] core.final_handler: [FinalHandler] Начинаем обработку прямолинейных знаков...
09:41:45 [INFO] core.final_handler: [FinalHandler] _process_straight_signs: обрабатываем 83 знаков
09:41:45 [INFO] core.final_handler: [FinalHandler] Сгруппировано в 42 групп
09:41:45 [INFO] core.final_handler: [FinalHandler] Выполняем batch OSM snap...
09:41:46 [INFO] core.final_handler: [FinalHandler] Batch OSM snap завершён: 83 результатов
09:41:46 [INFO] core.final_handler: [FinalHandler] Обработано 0/42 групп
09:41:46 [INFO] core.final_handler: [FinalHandler] Обработано 10/42 групп
09:41:46 [INFO] core.final_handler: [FinalHandler] Обработано 20/42 групп
09:41:46 [INFO] core.final_handler: [FinalHandler] Обработано 30/42 групп
09:41:46 [INFO] core.final_handler: [FinalHandler] Обработано 40/42 групп
09:41:46 [INFO] core.final_handler: [FinalHandler] _process_straight_signs завершён: 83 features
09:41:46 [INFO] core.final_handler: [FinalHandler] Обработано 83 прямолинейных знаков
09:41:46 [INFO] core.final_handler: [FinalHandler] Начинаем обработку знаков на поворотах...
09:41:46 [INFO] core.final_handler: [FinalHandler] После обработки: 83 features
09:41:46 [INFO] core.final_handler: [FinalHandler] Начинаем дедупликацию...
09:41:46 [INFO] core.final_handler: [FinalHandler] _deduplicate начат, features: 83
09:41:46 [INFO] core.final_handler: [FinalHandler] _deduplicate прогресс: 0/83 (0.0s)
09:41:46 [INFO] core.final_handler: [FinalHandler] _deduplicate завершён: 78 знаков (0.2s)
09:41:46 [INFO] core.final_handler: [FinalHandler] После дедупликации: 78 features
09:41:46 [INFO] core.final_handler: [FinalHandler] Сохраняем GeoJSON...
09:41:46 [INFO] core.final_handler: [FinalHandler] Сохранено 78 знаков → C:\Users\...\output.geojson
```

---

## Как проверить исправление

### 1. Перезапустите приложение
```bash
python main.py
```

### 2. Обработайте тестовое видео
- **Обязательно выберите папку для результатов** перед обработкой!
- Dashboard → "Папка результатов" → выберите папку

### 3. Проверьте логи
```bash
notepad roadscan.log
```

**Ищите строки:**
```
[INFO] core.final_handler: [FinalHandler] save_result вызван:
[INFO] core.final_handler:   - Знаков: N
[INFO] core.final_handler: [FinalHandler] Сохранено M знаков → path
```

### 4. Если знаков сохранено меньше чем обнаружено
**Причина:** Дедупликация удалила дубли

**Пример:**
```
Обнаружено: 83 знака
После дедупликации: 78 знаков
Сохранено: 78 знаков ✅
```

Это **нормально** — дубли должны удаляться!

---

## Диагностика проблем

### Проблема 1: "PATH_TO_GEOJSON пустой"
```
[ERROR] core.final_handler: [FinalHandler] ERROR: PATH_TO_GEOJSON пустой!
```

**Решение:** Dashboard → выберите папку результатов

---

### Проблема 2: "Знаков: 0"
```
[INFO] core.final_handler:   - Знаков: 0
```

**Причины:**
- Видео не содержит знаков
- Пороги confidence слишком высокие
- Нет GPS-трека

**Решение:** Settings → понизьте пороги (conf_side до 0.5)

---

### Проблема 3: "ОШИБКА в _process_straight_signs"
```
[ERROR] core.final_handler: [FinalHandler] ОШИБКА в _process_straight_signs: ...
Traceback:
  ...
```

**Действия:**
1. Скопируйте полный traceback
2. Проверьте что все зависимости установлены
3. Если ошибка в bearing-режиме:
   - Settings → "Геометрическая привязка" = OFF
   - Попробуйте legacy режим

---

### Проблема 4: Файл не создаётся
```
[INFO] core.final_handler: [FinalHandler] Сохраняем GeoJSON...
[ERROR] core.final_handler: [FinalHandler] ОШИБКА при сохранении файла: ...
```

**Причины:**
- Нет прав на запись в папку
- Недостаточно места на диске
- Папка не существует

**Решение:** Выберите другую папку (например, Desktop)

---

## Файлы изменены

- ✅ `core/final_handler.py` - добавлен logging, заменены все print()
- ✅ `scripts/fix_logging.py` - скрипт для автоматической замены

---

## Следующие шаги

### 1. Обработайте тестовое видео
- Убедитесь что логи FinalHandler теперь в roadscan.log
- Проверьте что GeoJSON создаётся корректно

### 2. Если всё работает
- Удалите temporary файлы:
  ```bash
  del scripts\fix_logging.py
  ```

### 3. Если проблемы остались
- Соберите логи:
  ```bash
  notepad roadscan.log
  ```
- Скопируйте все строки с `[FinalHandler]`
- Отправьте для анализа

---

## Статус

✅ **Логи исправлены** - print() → logger  
✅ **Сигнатура унифицирована** - _build_feature() работает корректно  
✅ **Синтаксис проверен** - py_compile успешно

**Готово к тестированию!**

---

*Дата: 2026-08-24*  
*Автор: AI Agent (Kiro)*
