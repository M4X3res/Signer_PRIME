# Process Pool Slowdown Analysis

**Дата анализа:** 2026-09-04  
**Исполнитель:** AI Agent (Kiro)  
**Исходная проблема:** Process Pool медленнее Single Thread/Pipeline на всех backend'ах (CPU и GPU)

---

## 1. Исходные гипотезы и находки

### Находка A — Двойная сериализация кадра через IPC (ПОДТВЕРЖДЕНА)

**Код:** `processing/detector_process_pool.py::_worker_process_frame()`

Воркер-процесс получает `image_bytes` (сериализованный кадр, ~6 МБ для 1920×1080×3), выполняет 
детекцию, и затем **возвращает те же самые `image_bytes` обратно** в главный процесс:

```python
return {
    ...
    'image_bytes': raw_frame_data['image_bytes'],   # ← ВОЗВРАТ НЕИЗМЕНЁННОГО КАДРА
    'image_shape': raw_frame_data['image_shape'],
    ...
}
```

Это означает ~12 МБ IPC round-trip вместо ~6 МБ one-way (туда + обратно).

**Почему это критично:**
- Сериализация/десериализация через `pickle` — CPU-bound операция
- Десериализация `future.result()` происходит в **единственном** `ResultAggregatorThread`
- Это overhead не зависит от backend'а инференса → объясняет одинаковое замедление на CPU/GPU

---

## 2. Инструментация для измерений

Добавлены логи времени в трёх точках:

1. **`_worker_process_frame()`:** размер image_bytes, время detect(), время reshape()
2. **`ResultAggregatorThread.run()`:** время future.result() (десериализация)
3. **`ResultAggregatorThread._process_result()`:** время reshape(), время emit()

Инструментация добавлена в коммите с префиксом BLOCK PERF-ANALYSIS-1.

---

## 3. Решение — устранение двойной сериализации

### 3.1 Архитектура изменений

**ДО:**
- VideoReader → DetectorProcessPool → submit(image_bytes) → worker → return {image_bytes + detections}
- ResultAggregator: распаковывает image_bytes из future.result()

**ПОСЛЕ:**
- VideoReader → DetectorProcessPool → сохраняет RawFrame в _pending_frames[seq] → submit(image_bytes только туда)
- worker → return {detections ONLY без image_bytes}
- ResultAggregator: берёт image из _pending_frames[seq], затем pop(seq)

### 3.2 Реализация выполнена

**Изменения в `DetectorProcessPool`:**
- ✅ Добавлено: `_pending_frames: dict[int, RawFrame]` с `threading.Lock()`
- ✅ В `_submit_loop()`: сохраняем `raw` в `_pending_frames[seq]` перед `executor.submit()`
- ✅ Периодическая чистка через `ResultAggregatorThread._cleanup_stale_frames()` (раз в 5 сек)

**Изменения в `_worker_process_frame()`:**
- ✅ Убрано из return: `image_bytes`, `image_shape`
- ✅ Добавлена инструментация времени detect()

**Изменения в `ResultAggregatorThread`:**
- ✅ Передаётся `pending_frames` и `lock` в конструктор
- ✅ `_process_result()` берёт кадр из `pending_frames.pop(seq)` вместо `frame_data['image_bytes']`
- ✅ Добавлен метод `_cleanup_stale_frames()` для защиты от утечки памяти

---

## 4. Выводы и следующие шаги

### 4.1 Что сделано
- ✅ Инструментация добавлена для измерений
- ✅ Устранена двойная сериализация кадра (экономия ~6 МБ IPC на кадр)
- ✅ Добавлена защита от утечки памяти (периодическая чистка)

### 4.2 TODO
- [ ] Запустить бенчмарк и внести числа (ДО/ПОСЛЕ)
- [ ] Обновить `WHY_SINGLE_THREAD_FASTER.md` с результатами
- [ ] Обновить tooltip в `settings_page.py` про GPU без MPS
- [ ] Проверить тесты `tests/test_reorder_buffer.py`
