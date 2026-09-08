# Многопроцессная обработка - ProcessPoolExecutor

**Дата:** 2026-08-19 14:15  
**Статус:** ✅ Реализовано, готово к тестированию

## Решение: ProcessPoolExecutor

### Архитектура
```
VideoReaderThread (30 FPS read)
        ↓
    frame_queue
        ↓
DetectorProcessPool
    ├─ Process 1 (Detector + models)
    ├─ Process 2 (Detector + models)
    ├─ Process 3 (Detector + models)
    └─ Process 4 (Detector + models)
        ↓
    ReorderBuffer (восстановление порядка)
        ↓
    ResultAggregator (QThread)
        ↓
    UI
```

## Ожидаемый эффект

**Baseline:** 1.0 FPS (single-thread)  
**С N=4:** 2.5-3.5 FPS (+2.5-3.5x)  
**С N=8:** 5.0-7.0 FPS (+5-7x)

## Как использовать

### Через UI:
1. Settings → "Отладка и производительность"
2. "Режим обработки" → **"Process Pool"**
3. Запустить обработку

### Через config:
```python
PROCESSING_MODE = "process_pool"
N_WORKERS = 4  # или None для auto
```

## Файлы
- `processing/detector_process_pool.py` - новая реализация
- `processing/processing_controller.py` - интеграция
