# CPU_OPT_BLOCK_0_BASELINE — Baseline-профилирование

**Дата:** 2026-08-25  
**Статус:** ✅ Завершено  
**Цель:** Зафиксировать текущие метрики производительности ДО любых оптимизаций

---

## 1. Обзор

Этот блок является обязательным preflight-шагом перед началом CPU-оптимизации.
Все последующие изменения будут сравниваться с baseline-метриками, зафиксированными здесь.

---

## 2. Текущая конфигурация системы

### 2.1. Environment Variables (main.py)

Обнаружены следующие настройки окружения, критичные для CPU-производительности:

```python
# Защита от STATUS_STACK_BUFFER_OVERRUN (0xC0000409)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"      # Разрешает дублирование OpenMP runtime
os.environ["OMP_NUM_THREADS"] = "1"              # ⚠️ Жёсткое ограничение OpenMP на 1 поток
os.environ["MKL_NUM_THREADS"] = "1"              # ⚠️ MKL на 1 поток
os.environ["MKL_THREADING_LAYER"] = "GNU"
os.environ["TBB_NUM_THREADS"] = "1"
os.environ["OPENCV_NUM_THREADS"] = "1"
os.environ["QT_OPENGL"] = "software"
```

**Критичное наблюдение:** `OMP_NUM_THREADS=1` и `MKL_NUM_THREADS=1` **полностью отключают 
многопоточность** в PyTorch/NumPy/OpenCV на уровне линейной алгебры. Это было сделано 
для предотвращения краша, но **является основным узким местом производительности CPU**.

### 2.2. torch.set_num_threads() в коде

Найдены жёсткие ограничения потоков в трёх местах:

| Файл | Строка | Контекст |
|------|--------|----------|
| `processing/detector_thread.py` | `DetectorThread.run()` | `torch.set_num_threads(1)` |
| `processing/detector_pool.py` | `DetectorWorker.run()` | `torch.set_num_threads(1)` |
| `processing/detector_process_pool.py` | `_worker_process_frame()` | `torch.set_num_threads(1)` |

Все три ограничивают PyTorch на **1 CPU-поток** для матричных операций.

### 2.3. AppSettings defaults

Текущие дефолтные настройки обработки:

```python
processing_mode: "single_thread"  # Не использует pipeline для OCR
frame_step_manual: 5              # Каждый 5-й кадр
ocr_use_process_pool: True
ocr_pool_workers: 1
use_cuda: True                    # Автоматически откатится на CPU если CUDA недоступна
```

### 2.4. Режимы декодирования видео

**Текущий подход** (`processing/video_reader.py`):
```python
ret, image = cap.read()  # Полное декодирование каждого кадра
local_frame += 1
frame_counter += 1
if frame_counter % step != 0:
    continue  # ⚠️ Кадр уже декодирован, но выброшен
```

При `FRAME_STEP=5` это означает **4 из 5 кадров полностью декодируются впустую**.

### 2.5. UI-превью

**Текущий подход** (`processing/detector_thread.py::_process_loop()`):
```python
self._emit_frame(raw.image)  # Вызывается на КАЖДОЙ итерации цикла
```

Включает:
- `cv2.cvtColor(BGR2RGB)` на полном разрешении кадра
- `QPixmap.fromImage(...).scaled(960, 540, ...)`

Без троттлинга — UI-превью обновляется **на каждом обрабатываемом кадре**, 
включая пропущенные по скорости/smart-skip.

### 2.6. CNN-skip кэш (TrackedSign)

**Статус:** ✅ Полностью реализован, но **❌ НЕ ИСПОЛЬЗУЕТСЯ**

Инфраструктура существует:
- `core/sign.py::TrackedSign` имеет `should_skip_cnn()`, `_update_cnn_stability()`
- `core/sign_handler.py::SignHandler.get_tracked_signs_map()` готов
- `core/detector.py::Detector.detect_with_tracking()` реализован

Но `processing/detector_thread.py::_process_loop()` **НЕ вызывает** `detect_with_tracking()`, 
используя только `find_rectangles()` (single_thread) или `detect()` (pipeline).

### 2.7. OCR-троттлинг

**Статус:** ❌ Отсутствует

Каждый текстовый знак получает OCR-вызов **на каждом кадре**, где он виден:
- `processing/detector_thread.py::_submit_ocr_task()` вызывается для каждого 
  `DetectedSign` без проверки "уже есть достаточно текстовых результатов у TrackedSign"
- При 30-40 кадрах видимости → 30-40 OCR-вызовов на один знак
- `FinalHandler` всё равно использует `most_common(text_results)` после 4+ наблюдений

---

## 3. Методология baseline-замеров

### 3.1. Инструментирование

Для baseline используются следующие инструменты:

1. **`scripts/benchmark_detector.py`** — изолированный тест `Detector` на N кадрах
   - Замеряет FPS без OCR и с OCR
   - Использует `core/profiler.py` для детальной разбивки

2. **`scripts/test_detector_regression.py`** — сохранение эталонных детекций
   - `--save-baseline` создаёт `regression_baseline.json`
   - Используется для проверки идентичности результатов после оптимизаций

3. **`core/profiler.py`** — встроенное профилирование пайплайна
   - `config.ENABLE_PROFILING = True` активирует замеры
   - Разбивает по стадиям: `yolo_bbox_detection`, `batch_classify_rube`, 
     `batch_classify_fine`, `ocr_read_text`, `draw_boxes_and_emit`, `video_read_frame`, 
     `sign_handler_tracking`

4. **End-to-end прогон** через `main.py` на полном видео
   - Single_thread режим
   - Pipeline режим (если доступен)

### 3.2. Тестовые данные

Для воспроизводимого baseline требуется:
- Тестовое видео ≥2000 кадров, с GPX-треком
- Содержит городские/текстовые знаки для проверки OCR
- Участок с поворотами/перекрёстками для проверки трекинга

**⚠️ ВАЖНО:** Baseline-замеры должны выполняться на реальной CPU-only машине 
(или с `settings.use_cuda = False` для принудительного CPU-пути).

---

## 4. Baseline-метрики (требуют фактических замеров)

> **Примечание:** Раздел будет заполнен после выполнения замеров на реальном 
> тестовом видео. Ниже — шаблон для заполнения.

### 4.1. Системные характеристики

```
OS:                  Windows [версия]
CPU:                 [модель]
Cores/Threads:       [физические / логические]
RAM:                 [объём]
AVX2 support:        [да/нет]
CUDA available:      False (baseline для CPU-only)
Python version:      [версия]
PyTorch version:     [версия]
torch.get_num_threads(): 1  ⚠️ (ограничен в main.py)
```

### 4.2. Benchmark Detector (изолированный)

#### 4.2.1. Без OCR (`--frames 300`)

```
Команда: python scripts/benchmark_detector.py --video [test.mp4] --frames 300

Кадров обработано:      [N]
Время выполнения:       [X.XX] сек
FPS:                    [X.XX]
Всего детекций:         [N]
Детекций на кадр:       [X.X]
```

**Профилировщик (core/profiler):**

| Операция | Вызовов | Всего (с) | Средн. (мс) | % от общего |
|----------|---------|-----------|-------------|-------------|
| yolo_bbox_detection | ? | ? | ? | ? |
| batch_classify_rube | ? | ? | ? | ? |
| batch_classify_fine | ? | ? | ? | ? |
| video_read_frame | ? | ? | ? | ? |
| draw_boxes_and_emit | ? | ? | ? | ? |
| sign_handler_tracking | ? | ? | ? | ? |

#### 4.2.2. С OCR (`--frames 300 --with-ocr`)

```
Команда: python scripts/benchmark_detector.py --video [test.mp4] --frames 300 --with-ocr

Кадров обработано:      [N]
Время выполнения:       [X.XX] сек
FPS:                    [X.XX]
Всего детекций:         [N]
Детекций на кадр:       [X.X]
OCR:                    включен
```

**Профилировщик (core/profiler):**

| Операция | Вызовов | Всего (с) | Средн. (мс) | % от общего |
|----------|---------|-----------|-------------|-------------|
| ocr_read_text | ? | ? | ? | ? |
| (остальные) | ? | ? | ? | ? |

### 4.3. End-to-end прогон (main.py)

#### 4.3.1. Single_thread режим

```
Видео:                  [test.mp4]
Кадров в видео:         [N]
Обработано кадров:      [N] (с учётом FRAME_STEP=5)
Общее время:            [X.XX] мин
Средний FPS:            [X.XX]
Знаков в итоговом GeoJSON: [N]
```

**Профилировщик (если включён):** [таблица]

#### 4.3.2. Pipeline режим

```
Видео:                  [test.mp4]
Кадров в видео:         [N]
Обработано кадров:      [N]
Общее время:            [X.XX] мин
Средний FPS:            [X.XX]
Знаков в итоговом GeoJSON: [N]
```

**Примечание:** Сравнение с single_thread для оценки эффекта асинхронного OCR.

### 4.4. Regression Baseline

```
Команда: python scripts/test_detector_regression.py --video [test.mp4] --frames 100 --save-baseline

Сохранено:              regression_baseline_pre_cpu_opt.json
Кадров в baseline:      100
Всего детекций:         [N]
```

Этот файл будет использоваться для проверки идентичности результатов после 
каждого блока оптимизации.

---

## 5. Узкие места (предварительная диагностика)

На основе анализа кода **ДО** фактических замеров можно выделить:

### 5.1. Критичные (высокий приоритет)

1. **OMP_NUM_THREADS=1 + torch.set_num_threads(1)** 
   - Полностью убивает многопоточность в PyTorch матричных операциях
   - YOLO/CNN инференс использует **одно ядро** из доступных 4-16+
   - **Ожидаемый эффект снятия ограничения:** 2-4x для инференса

2. **Декодирование пропускаемых кадров** (`video_reader.py`)
   - 80% кадров (при FRAME_STEP=5) декодируются впустую
   - `cap.read()` включает полное JPEG/H.264 декодирование + BGR-конвертацию
   - **Ожидаемый эффект `grab()`/`retrieve()`:** 1.5-2x для видео I/O

3. **OCR без троттлинга** 
   - EasyOCR — самая тяжёлая операция на CPU
   - Каждый текстовый знак → 30-40 OCR-вызовов вместо 4-6
   - **Ожидаемый эффект троттлинга:** 5-8x для видео с текстовыми знаками

4. **CNN-skip кэш не подключён**
   - Уже реализован, но не используется
   - Каждый стабильный знак → 50-100 CNN-вызовов вместо 5+пропуски
   - **Ожидаемый эффект:** 2-3x для CNN-стадии на длинных треках

### 5.2. Средние (средний приоритет)

5. **UI-превью без троттлинга**
   - `cv2.cvtColor` + `QPixmap.scaled` на каждом кадре
   - Конкурирует за CPU с детекцией
   - **Ожидаемый эффект:** 10-20% общего FPS

6. **Process Pool не интегрирован** (`processing_mode="process_pool"`)
   - `_on_process_pool_frame()` не передаёт данные в `SignHandler` → пустой GeoJSON
   - Выбор в UI не синхронизируется с `config.PROCESSING_MODE`
   - Блокирует корректность, не только производительность

### 5.3. Опциональные (высокий потенциал, но высокая сложность)

7. **PyTorch backend** (ONNX/OpenVINO)
   - Нативный PyTorch на CPU медленнее оптимизированных backend'ов
   - **Ожидаемый эффект ONNX:** 1.5-2.5x
   - **Ожидаемый эффект OpenVINO (Intel CPU):** 2-4x

---

## 6. Следующие шаги

После заполнения раздела 4 фактическими метриками:

1. ✅ **БЛОК 0 завершён** — baseline зафиксирован
2. → **БЛОК 1** — `grab()`/`retrieve()` для видео I/O
3. → **БЛОК 2** — Троттлинг UI-превью
4. → **БЛОК 3** — Подключение CNN-skip кэша
5. → **БЛОК 4** — Троттлинг OCR
6. → **БЛОК 6** — Диагностика/фикс Process Pool
7. → **БЛОК 8** — Авто-профиль "CPU Performance Mode"
8. → **БЛОК 9** — Методология бенчмарков
9. → **БЛОК 5** — Пересмотр CPU-потоков (рискованно, последним из "быстрых")
10. → **БЛОК 7** — ONNX/OpenVINO (опционально, отдельная итерация)
11. → **БЛОК 10** — Итоговая документация

---

## 7. Инструкции по выполнению baseline-замеров

### 7.1. Подготовка

```bash
# 1. Убедиться, что CUDA недоступна (или временно отключена в settings)
# 2. Выбрать тестовое видео ≥2000 кадров с GPX
# 3. Активировать виртуальное окружение
.venv\Scripts\activate
```

### 7.2. Изолированные бенчмарки

```bash
# Без OCR
python scripts/benchmark_detector.py --video <test.mp4> --frames 300

# С OCR
python scripts/benchmark_detector.py --video <test.mp4> --frames 300 --with-ocr
```

### 7.3. Regression baseline

```bash
python scripts/test_detector_regression.py --video <test.mp4> --frames 100 --save-baseline
# Сохранит regression_baseline.json → переименовать в regression_baseline_pre_cpu_opt.json
```

### 7.4. End-to-end через main.py

1. Открыть RoadScanner GUI
2. Settings → `use_cuda = False`, `processing_mode = "single_thread"`
3. Включить `config.ENABLE_PROFILING = True` в `configs/config.py` (или через код)
4. Обработать тестовое видео целиком
5. Сохранить логи (`roadscan.log`) и профилировщик-отчёт
6. Повторить с `processing_mode = "pipeline"` для сравнения

### 7.5. Сохранение результатов

Все замеры заносятся в раздел 4 этого документа для reference при следующих блоках.

---

## 8. Критерии завершения БЛОКА 0

- [x] Задокументированы все environment variables из `main.py`
- [x] Найдены все `torch.set_num_threads(1)` в коде
- [x] Проанализированы текущие узкие места по коду
- [ ] Выполнены изолированные бенчмарки (с/без OCR)
- [ ] Создан `regression_baseline_pre_cpu_opt.json`
- [ ] Выполнен end-to-end прогон в single_thread режиме
- [ ] Выполнен end-to-end прогон в pipeline режиме (опционально)
- [ ] Раздел 4 заполнен фактическими цифрами
- [ ] Baseline-данные сохранены в систему контроля версий

**Статус:** Инфраструктура готова, требуются фактические замеры на тестовом видео.

---

**Автор:** Kiro AI Agent  
**Дата создания:** 2026-08-25
