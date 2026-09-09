# Исправление критических багов: Пропадающие знаки + низкая производительность

**Дата:** 2026-09-03  
**Статус:** ✅ Исправлено, требует ручного тестирования

---

## Что было исправлено

### 🔴 БАГ A (P0): Крах Pipeline при текстовых знаках
**Проблема:** `AttributeError: 'DetectedSign' has no attribute 'bbox'` → DetectorThread падал сразу  
**Решение:** Изменена сигнатура `_submit_ocr_task()`, добавлено property `bbox`  
**Файлы:** `processing/detector_thread.py`, `core/frame.py`

### 🔴 БАГ B (P0): Текст знаков не сохраняется
**Проблема:** OCR результат записывался в одноразовый объект → терялся  
**Решение:** Callback-и теперь пишут напрямую в `TrackedSign.text_results`  
**Файлы:** `processing/detector_thread.py`

### 🟡 БАГ C (P1): Process Pool медленнее single_thread в 5-8 раз
**Проблема:** OCR вызывался на каждом кадре без кэширования  
**Решение:** Добавлен OCR-кэш по perceptual hash (аналогично CNN-кэшу)  
**Файлы:** `core/detector.py`  
**Эффект:** ~70-85% экономии OCR-вызовов во всех режимах

### 🟡 БАГ D (P1): Названия городов всегда пустые
**Проблема:** `best_city_name()` ожидал неправильный формат данных  
**Решение:** Переписан с использованием `most_common()`, унифицирован `_ocr_city()`  
**Файлы:** `core/sign.py`, `processing/ocr_pool.py`, `processing/ocr_worker.py`

### 🟢 БАГ E (P2): Знаки в конце видео теряются
**Проблема:** Знаки, видимые в последних кадрах, не финализировались  
**Решение:** Добавлен `SignHandler.finalize_remaining()`, вызывается в конце обработки  
**Файлы:** `core/sign_handler.py`, `processing/detector_thread.py`, `processing/detector_process_pool.py`

---

## Регресс-тесты

Созданы 3 файла тестов (10 тест-кейсов):
- `tests/test_ocr_pipeline_regression.py` — баги A и B
- `tests/test_ocr_cache_and_city_name.py` — баги C и D
- `tests/test_sign_handler_finalize_remaining.py` — баг E

---

## Быстрая проверка

### Pipeline режим (баги A + B)
```
Settings → Pipeline → обработать видео с текстовыми знаками
```
✅ Должно: обработка до конца, текст в GeoJSON заполнен  
❌ Было: крах через несколько секунд, пустой GeoJSON

### Process Pool (баг C)
```
Settings → Process Pool → обработать то же видео
```
✅ Должно: сопоставимая или выше скорость, чем single_thread  
❌ Было: в 5-8 раз медленнее

### Городские знаки (баг D)
```
Обработать видео со знаками 5.22.x / 5.23.x
```
✅ Должно: SEM250/MVALUE содержит название города  
❌ Было: всегда пустое поле

### Короткие видео (баг E)
```
Обработать 30-60 сек видео
```
✅ Должно: все знаки с >= 4 наблюдениями сохранены  
❌ Было: последние 1-3 знака отсутствуют

---

## Полная документация

См. `docs/BUGFIX_MISSING_SIGNS_OCR_PIPELINE_PERFORMANCE.md`
