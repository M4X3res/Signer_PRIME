# Почему Pipeline и Process Pool медленнее на CPU?

**Дата:** 2026-08-21  
**Проблема:** Pipeline и Process Pool режимы в 3 раза медленнее Single Thread на CPU

---

## TL;DR

**На CPU всегда используйте режим "Один поток" (single_thread).** Pipeline и Process Pool добавляют overhead, который не компенсируется параллелизмом на CPU-only системах.

---

## Архитектура режимов

### 1. Single Thread (Рекомендуется для CPU) ⚡

```
VideoReaderThread
    ↓ frame_queue
DetectorThread:
    YOLO detect → CNN classify → EasyOCR (если нужно) → SignHandler
    ↓ результат
UI + GeoJSON
```

**Характеристики:**
- ✅ Все операции в одном потоке
- ✅ Модели загружаются один раз при старте
- ✅ Нет сериализации/десериализации данных
- ✅ Нет переключения контекста
- ✅ Минимальный overhead
- ✅ Кэш CNN работает эффективно (один кэш для всего)

**Производительность на CPU:**
- FPS: 0.7-3.0 (зависит от сложности видео)
- RAM: ~2-3 GB
- Инициализация: 10-15 секунд

---

### 2. Pipeline (Медленнее на CPU) ⚠️

```
VideoReaderThread
    ↓ frame_queue
DetectorThread:
    YOLO detect → CNN classify → добавляет знак в pending_ocr
    ↓ передаёт crop в OCRWorkerThread
OCRWorkerThread:
    EasyOCR → возвращает текст обратно
    ↓ callback _on_ocr_result
DetectorThread:
    обновляет DetectedSign.text → SignHandler
    ↓ результат
UI + GeoJSON
```

**Характеристики:**
- ⚠️ Вынос OCR в отдельный QThread
- ⚠️ Требует передачу crop (numpy array) между потоками
- ⚠️ Требует синхронизацию через pending_ocr словарь
- ⚠️ Два отдельных набора моделей (YOLO+CNN в основном, EasyOCR в OCR thread)

**Почему медленнее:**

1. **Overhead на передачу данных:**
   ```python
   # Каждый текстовый знак:
   crop = image[y1:y2, x1:x2].copy()  # копирование numpy array
   self._ocr_worker.submit_crop(crop, sign_id)  # передача через очередь
   ```

2. **Синхронизация:**
   - Основной поток ждёт результата OCR для обновления знака
   - `pending_ocr` растёт при большом количестве текстовых знаков
   - Callback `_on_ocr_result` конкурирует с основным циклом

3. **GIL (Global Interpreter Lock):**
   - Python GIL не даёт параллелизма на CPU-bound задачах в threads
   - EasyOCR в отдельном потоке **всё равно блокирует** основной поток через GIL

4. **Польза только при:**
   - Много текстовых знаков (ограничение скорости, названия городов) — тогда экономия ~10-20%
   - На GPU (EasyOCR может работать асинхронно на GPU)

**Производительность на CPU:**
- FPS: 0.2-1.0 (в 3 раза медленнее!)
- RAM: ~3-4 GB (два набора моделей)
- Инициализация: 15-20 секунд (загрузка EasyOCR в отдельном потоке)

---

### 3. Process Pool (Самый медленный на CPU) 🐌

```
VideoReaderThread
    ↓ frame_queue
DetectorProcessPool:
    → serialize frame (numpy → bytes)
    → submit to ProcessPoolExecutor
        Worker Process 1: loads models, detect, serialize result
        Worker Process 2: loads models, detect, serialize result
        Worker Process N: loads models, detect, serialize result
    → ReorderBuffer (восстанавливает порядок)
    → deserialize results
    ↓ result_queue
ResultAggregatorThread:
    → SignHandler
    ↓ результат
UI + GeoJSON
```

**Характеристики:**
- ❌ N отдельных процессов (каждый = полная копия моделей)
- ❌ Сериализация/десериализация кадров (numpy → bytes → numpy)
- ❌ Сериализация/десериализация результатов (DetectedSign → dict → DetectedSign)
- ❌ ReorderBuffer для восстановления порядка кадров
- ❌ Межпроцессное взаимодействие через Pipe/Queue

**Почему ОЧЕНЬ медленно:**

1. **Загрузка моделей в каждом процессе:**
   ```python
   # При N=4 воркерах:
   Worker 1: загружает YOLO (2.5GB) + CNN (500MB) + EasyOCR (1GB) = 4GB
   Worker 2: загружает YOLO (2.5GB) + CNN (500MB) + EasyOCR (1GB) = 4GB
   Worker 3: загружает YOLO (2.5GB) + CNN (500MB) + EasyOCR (1GB) = 4GB
   Worker 4: загружает YOLO (2.5GB) + CNN (500MB) + EasyOCR (1GB) = 4GB
   # Итого: 16 GB RAM! И инициализация 40-60 секунд
   ```

2. **Сериализация каждого кадра:**
   ```python
   # Каждый кадр Full HD (1920x1080x3):
   image_bytes = image.tobytes()  # ~6 MB
   # Отправка в процесс через pipe
   # Получение обратно
   # Десериализация в numpy
   ```

3. **Переключение контекста:**
   - OS scheduler переключает между процессами
   - CPU кэш инвалидируется при переключении
   - TLB flush при переключении адресных пространств

4. **Холодный старт каждого батча:**
   - Каждый новый кадр попадает в холодный процесс
   - Кэш CNN не работает между процессами
   - Нет переиспользования вычислений

5. **ReorderBuffer overhead:**
   - Буфер накапливает результаты для восстановления порядка
   - Добавляет латентность (задержку между детекцией и обработкой)
   - Может переполниться при неравномерной нагрузке

**Когда полезен:**
- ✅ GPU доступна (каждый процесс использует свой GPU stream)
- ✅ Батчинг включён (YOLO обрабатывает 8-16 кадров за раз)
- ✅ Очень много RAM (>32GB)
- ✅ CPU с большим количеством ядер (>8 физических)

**Производительность на CPU:**
- FPS: 0.1-0.5 (в 6-10 раз медленнее!)
- RAM: 12-20 GB (N копий моделей)
- Инициализация: 40-60 секунд (N процессов загружают модели)

---

## Сравнительная таблица (CPU only)

| Режим         | FPS   | RAM    | Инициализация | Overhead | Рекомендация |
|---------------|-------|--------|---------------|----------|--------------|
| Single Thread | 2.0   | 2-3GB  | 10s           | Минимум  | ✅ **Используйте** |
| Pipeline      | 0.7   | 3-4GB  | 15s           | Средний  | ⚠️ Только если много текстовых знаков |
| Process Pool  | 0.2   | 16GB   | 50s           | Огромный | ❌ Не используйте на CPU |

---

## Почему GIL не даёт параллелизма

Python **Global Interpreter Lock (GIL)** позволяет только одному потоку выполнять Python bytecode одновременно.

**В Pipeline режиме:**
```python
# Основной поток:
detections = detector.detect(frame)  # ← держит GIL
# В это время OCRWorkerThread не может работать!

# OCRWorkerThread:
text = ocr_reader.readtext(crop)     # ← ждёт GIL
# В это время основной поток не может работать!
```

Результат: потоки выполняются **последовательно**, но с добавленным overhead на переключение.

**Обход GIL:** Только через multiprocessing (Process Pool), но тогда появляется overhead на IPC.

---

## Что реально ускоряет на CPU?

### 1. Умный frame skipping (уже реализован) ✅

```python
# Адаптивный пропуск кадров по скорости:
if speed > 90 km/h:
    skip_every_4th_frame()
elif speed > 60 km/h:
    skip_every_2nd_frame()
else:
    process_every_frame()
```

**Даёт:** 2-4x ускорение без потери точности

### 2. CNN кэширование (уже реализован) ✅

```python
# Кэш недавних crop'ов:
if crop_hash in cache:
    return cached_result  # Пропускаем CNN inference
```

**Даёт:** 30-50% ускорение на повторяющихся знаках

### 3. EasyOCR только для текстовых знаков ✅

```python
if sign_type not in TYPE_SIGNS_WITH_TEXT:
    det.text = ""  # Пропускаем OCR
    return det
```

**Даёт:** 5-10x ускорение на нетекстовых знаках

### 4. Batch inference (не реализовано)

```python
# Вместо:
for frame in frames:
    result = model(frame)  # 10ms per frame

# Можно:
results = model(frames)  # 30ms for 8 frames = 3.75ms per frame
```

**Даёт:** 2-3x ускорение на GPU, но требует накопления батча (увеличивает латентность)

---

## Рекомендации

### Для CPU (текущая ситуация):

1. ✅ **Используйте "Один поток"** — всегда
2. ✅ Включите умный frame skipping — по умолчанию
3. ✅ Включите CNN кэш — по умолчанию
4. ⚠️ Pipeline можно попробовать ТОЛЬКО если:
   - Вы обрабатываете городские видео с кучей знаков ограничения скорости
   - И готовы пожертвовать 30% производительности ради более плавной обработки текста

5. ❌ **Никогда не используйте Process Pool на CPU**

### Для GPU (будущее):

1. ✅ Process Pool с батчингом
2. ✅ 2-4 воркера (не больше)
3. ✅ Batch size 8-16
4. ⚠️ Требуется >16GB RAM

---

## Исправления в коде

### Добавлены tooltips с предупреждениями:

**ui/widgets/settings_page.py:**

```python
self._processing_mode_combo.setToolTip(
    "⚡ Для CPU всегда выбирайте 'Один поток'\n\n"
    "Pipeline и Process Pool медленнее из-за overhead!"
)

self._workers_spin.setToolTip(
    "⚠️ Каждый процесс загружает свои копии моделей!\n"
    "На CPU это обычно МЕДЛЕННЕЕ"
)
```

### Дефолтные настройки правильные:

**configs/settings.py:**
```python
processing_mode: "single_thread"  # ✅ Оптимально для CPU
process_pool_workers: 0           # Не используется по умолчанию
```

---

## Паритет потоков между backend'ами (BLOCK CPU-5)

До версии 2.0 сравнение backend'ов "PyTorch" vs "ONNX Runtime"/"OpenVINO"
на CPU было некорректным: `torch.set_num_threads(1)` и `OMP_NUM_THREADS=1`
ограничивали ТОЛЬКО PyTorch (ради защиты от краша 0xC0000409), в то время
как ONNX Runtime и OpenVINO использовали дефолтные (все доступные) потоки
CPU без каких-либо ограничений. Поэтому ONNX/OpenVINO казались значительно
быстрее — не благодаря более эффективной архитектуре инференса, а просто
за счёт использования в разы больше CPU-ресурсов.

Начиная с BLOCK CPU-5 (версия 2.1), количество потоков ONNX Runtime/OpenVINO
настраивается явно через `configs/inference_threading.py` и
Settings → Диагностика системы → "Потоки ONNX/OpenVINO". Значение по
умолчанию (0/авто) безопасно делит доступные ядра между воркерами в
режиме Process Pool, чтобы избежать перегрузки CPU.

См. также: `configs/inference_threading.py`, `prompts/PROMPT_FIX_CPU_INFERENCE_BACKEND.md`

---

## Вывод

**Single Thread — это не баг, это фича!** На CPU однопоточная обработка с умными оптимизациями (frame skipping, кэширование, избирательный OCR) даёт лучший результат, чем наивный параллелизм с огромным overhead.

Pipeline и Process Pool полезны только на GPU с батчингом, где overhead компенсируется параллельным выполнением на ускорителе.

---

## См. также

- `CHANGELOG_PERFORMANCE.md` — история оптимизаций
- `CHANGELOG_SMART_SKIPPING.md` — умный frame skipping
- `configs/settings.py` — дефолтные настройки
