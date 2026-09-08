# План реализации многопоточной обработки (PROMPT_MULTITHREADING.md)

**Дата начала:** 2026-08-19  
**Статус:** В ПРОЦЕССЕ

---

## Этап 0: Профилирование (ТЕКУЩИЙ)

### ✅ Выполнено:
1. Создан `core/profiler.py` с классами `TimingStats` и `Profiler`
2. Добавлены настройки в `configs/config.py`:
   - `ENABLE_PROFILING` - флаг включения
   - `PROCESSING_MODE` - режим обработки
   - `N_WORKERS` - количество воркеров
   - `WORKER_QUEUE_SIZE`, `REORDER_BUFFER_MAX_GAP`

### ⏳ В процессе:
3. Инструментирование `core/detector.py`:
   - [ ] Добавить `from core.profiler import profiler`
   - [ ] Обернуть `_find_boxes()` в `profiler.measure("yolo_bbox_detection")`
   - [ ] Обернуть `_classify_rube()` в `profiler.measure("classify_rube")`
   - [ ] Обернуть `_classify_fine()` в `profiler.measure("classify_fine")`
   - [ ] Обернуть `_read_text()` в `profiler.measure("ocr_read_text")`

4. Инструментирование `processing/detector_thread.py`:
   - [ ] Замер времени `SignHandler.check_the_data_to_add()`
   - [ ] Замер времени отрисовки превью (`_draw_boxes`, `_emit_frame`)

5. Инструментирование `processing/video_reader.py`:
   - [ ] Замер времени чтения кадра из видео

6. Активация профилирования:
   - [ ] Добавить в `main.py` или UI настройку включения
   - [ ] Автоматическая печать отчета каждые N кадров
   - [ ] Сохранение финального отчета в `docs/PROFILING.md`

### Ожидаемый результат:
Отчет вида:
```
yolo_bbox_detection:
  Count:  1000
  Mean:   45.2ms
  P95:    67.8ms
  
classify_rube:
  Count:  3456  (несколько на кадр)
  Mean:   12.3ms
  P95:    23.1ms

classify_fine:
  Count:  3456
  Mean:   15.7ms
  P95:    28.4ms

ocr_read_text:
  Count:  234  (только для знаков с текстом)
  Mean:   156.2ms
  P95:    245.6ms

tracking:
  Count:  1000
  Mean:   8.5ms
  P95:    15.2ms
```

---

## Этап 1: Батчинг классификации (СЛЕДУЮЩИЙ)

**Цель:** Оптимизация без многопоточности - безопасно и эффективно

### План:
1. Изменить `Detector.detect()`:
   - Собрать все `resized` кропы в список
   - Прогнать через `rube_modal.predict([crop1, crop2, ...])` одним батчем
   - Сгруппировать по `yolo_class`
   - Прогнать каждую группу через `model_dict[yolo_class].predict(batch)`

2. Измерить прирост производительности
3. Задокументировать в `docs/PROFILING.md`

**Риски:** Минимальные (не меняет поток выполнения, только группирует вызовы)

---

## Этап 2: Выбор стратегии параллелизма

**На основе профилирования решить:**

### Вариант A: Процессы (если CPU-bound)
- ✅ Обходит GIL
- ✅ Изолированные модели (нет shared state)
- ✅ Снимает ограничение OMP_NUM_THREADS=1
- ❌ Накладные расходы на IPC

### Вариант B: GPU Batching (если GPU-bound)
- ✅ Максимальная утилизация GPU
- ✅ Меньше накладных расходов
- ❌ Не масштабируется с количеством ядер CPU

### Вариант C: Потоки (если I/O-bound)
- ❌ GIL ограничивает CPU-heavy операции
- ❌ Требует переписывания синглтонов моделей
- ✅ Легче отладка

**Решение будет принято после анализа профилирования**

---

## Этап 3: Архитектура параллельной обработки

```
VideoReaderThread
    ↓ frame_queue
DetectionWorkerPool (N процессов/потоков)
    ↓ results (неупорядоченные)
ReorderBuffer
    ↓ results (упорядоченные по frame_number)
AggregatorThread
    - обновляет config.INDEX_OF_*
    - вызывает SignHandler
    ↓ result_queue
UI
```

### Компоненты для реализации:
1. `processing/detection_worker.py` - воркер детекции
2. `processing/reorder_buffer.py` - буфер переупорядочивания
3. `processing/aggregator_thread.py` - агрегатор результатов
4. Модификация `processing/processing_controller.py`

---

## Этап 4: Тестирование

### Регрессионные тесты:
1. `tests/test_processing_parity.py`:
   - Прогнать тестовое видео через single_thread
   - Прогнать через process_pool (N=2,4,8)
   - Сравнить GeoJSON результаты

### Бенчмарки:
1. `scripts/benchmark_processing.py`:
   - Замерить FPS для разных режимов
   - Замерить потребление памяти
   - Найти оптимальное N_WORKERS

---

## Критерии успеха

- [ ] Профилирование показывает узкие места
- [ ] Батчинг дает измеримый прирост (>20%)
- [ ] Параллелизм дает линейное ускорение до N=4
- [ ] Регрессионные тесты проходят (результаты совпадают)
- [ ] Нет утечек памяти/зомби-процессов
- [ ] Можно вернуться на single_thread одним флагом

---

## Текущий фокус

🎯 **Завершить инструментирование для профилирования**
