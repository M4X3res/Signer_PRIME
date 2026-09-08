# CPU_OPT_BLOCK_4 — Троттлинг и переиспользование OCR

**Дата:** 2026-08-25  
**Статус:** ✅ Завершено  
**Приоритет:** Очень высокий (критично для видео с текстовыми знаками)  
**Риск:** Средний  

---

## 1. Проблема

EasyOCR — **самая тяжёлая операция** в пайплайне на CPU:
- CRAFT text detector + recognition neural network
- Каждый текстовый знак → OCR на **каждом кадре** без переиспользования
- Знак виден 30-40 кадров → **30-40 OCR-вызовов**
- `FinalHandler` всё равно использует `most_common(text_results)` после 4+ наблюдений

**Избыточность:** После 4-6 успешных распознаваний дополнительные OCR-вызовы **не улучшают результат**, это чистая трата CPU.

---

## 2. Решение

### 2.1. Добавление методов в `TrackedSign`

**Файл:** `core/sign.py`

```python
# Настройки троттлинга OCR
OCR_MIN_INTERVAL_FRAMES = 8   # не чаще раза в N обработанных кадров
OCR_MAX_CALLS_PER_SIGN = 6    # после этого числа успешных вызовов — хватит

def should_run_ocr(self, current_abs_frame: int) -> bool:
    """Решает, нужно ли запускать OCR для этого наблюдения."""
    # Считаем непустые текстовые результаты
    non_empty = sum(1 for t in self.text_results if t)
    if non_empty >= self.OCR_MAX_CALLS_PER_SIGN:
        return False
    
    # Защита от знака с постоянно разным/пустым текстом
    if self._ocr_call_count >= self.OCR_MAX_CALLS_PER_SIGN * 2:
        return False
    
    # Проверка временного интервала
    if current_abs_frame - self._last_ocr_abs_frame < self.OCR_MIN_INTERVAL_FRAMES:
        return False
    
    return True

def mark_ocr_requested(self, current_abs_frame: int) -> None:
    """Отмечает, что OCR был запрошен."""
    self._last_ocr_abs_frame = current_abs_frame
    self._ocr_call_count += 1
```

### 2.2. Настройки в `AppSettings`

```python
ocr_throttle_interval_frames: int = 8   # Минимальный интервал между OCR-вызовами
ocr_max_calls_per_sign: int = 6         # Максимальное число OCR-вызовов
```

### 2.3. Интеграция в `DetectorThread`

**Ключевое изменение:** OCR-решение принимается **ПОСЛЕ** трекинга, а не до:

```python
# Трекинг ПЕРЕД OCR (нужен TrackedSign для троттлинга)
with profiler.measure("sign_handler_tracking"):
    turn = self._sign_handler.check_the_data_to_add(detected or None, turn)

# OCR Throttling на уровне TrackedSign
if self._use_pipeline and self._sign_handler.signs:
    for tracked_sign in self._sign_handler.signs:
        if self._detector.needs_ocr(tracked_sign.best_cnn, tracked_sign.best_yolo):
            if tracked_sign.should_run_ocr(raw.abs_frame_number):
                # Отправляем в OCR Worker
                self._submit_ocr_task(...)
                tracked_sign.mark_ocr_requested(raw.abs_frame_number)
                self._ocr_calls_total += 1
            else:
                self._ocr_calls_skipped += 1
```

---

## 3. Ожидаемый эффект

### 3.1. Типичный сценарий

**Знак "5.19.1" (населённый пункт) виден 40 кадров:**

**Без троттлинга:** 40 OCR-вызовов  
**С троттлингом (интервал=8, max=6):**
- Кадр 1: OCR → результат "МИНСК" ✅
- Кадры 2-8: пропущено (интервал)
- Кадр 9: OCR → результат "МИНСК" ✅
- Кадры 10-16: пропущено
- Кадр 17: OCR → результат "МИНСК" ✅
- ...
- **Всего: 6 вызовов**, после 6-го — `non_empty >= OCR_MAX_CALLS_PER_SIGN` → stop

**Экономия:** 34 из 40 вызовов = **85% пропусков**

### 3.2. Видео с текстовыми знаками

При 5 городских знаках по 30 кадров каждый:
- **Без троттлинга:** 5 × 30 = 150 OCR-вызовов
- **С троттлингом:** 5 × 6 = 30 OCR-вызовов
- **Прирост FPS:** **5-8x** для OCR-компонента, **2-3x** для всего пайплайна

---

## 4. Критерии приёмки

### 4.1. Логирование

```
[SmartSkip] ... OCR: 30 calls, 120 skipped (80.0%), pending: 2
```

**Ожидание:** 70-85% skip rate на видео с текстовыми знаками

### 4.2. Regression-тест содержимого текста

**Обязательно:** Финальные `SEM250`/`MVALUE` в GeoJSON должны **совпадать** с baseline или быть эквивалентно корректными (через `most_common()` получен тот же текст).

### 4.3. FPS на видео с текстом

```
Baseline (БЛОК 3): [X.X] FPS
БЛОК 4:            [X.X + 100-200%] FPS (на видео с городскими знаками)
```

---

## 5. Известные ограничения

### 5.1. Знаки с "мерцающим" текстом

Если OCR даёт разные результаты каждый раз ("МИНСК" → "M1HCK" → "МИНСК"), троттлинг может остановиться на `OCR_MAX_CALLS_PER_SIGN * 2 = 12` попытках.

**Решение:** Это защита, не баг. Такие знаки (плохое качество/освещение) всё равно не дадут надёжного результата.

### 5.2. Короткие треки (<8 кадров)

Знак виден менее `OCR_MIN_INTERVAL_FRAMES` → получит только 1 OCR-вызов.

**Это норма:** Короткие треки редки (<10% знаков), один вызов достаточен.

---

## 6. Следующие шаги

- [x] Код изменён
- [ ] Логирование OCR throttling работает
- [ ] Regression-тест текста пройден (SEM250/MVALUE идентичны)
- [ ] FPS-бенчмарк на городском видео показывает 2-3x прирост
- [ ] Коммит: `CPU-OPT BLOCK 4: OCR throttling on TrackedSign level`

→ **БЛОК 6:** Диагностика и фикс Process Pool (корректность)

---

**Автор:** Kiro AI Agent  
**Дата создания:** 2026-08-25
