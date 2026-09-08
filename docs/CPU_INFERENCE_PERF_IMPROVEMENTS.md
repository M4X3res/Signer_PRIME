# CPU Inference Performance Improvements

**Дата:** 2026-09-07  
**Статус:** ✅ Реализовано (4.1, 4.2, 4.4) | 🔲 TODO (4.3, 4.5)  
**Затронутые файлы:**
- `configs/inference_threading.py` — основные изменения
- `scripts/export_models_onnx.py` — информационная аннотация

---

## Контекст

До этих изменений проект имел базовую поддержку ONNX Runtime и OpenVINO
через `_LazyModel` (BLOCK M в `configs/sign_models.py`) с управлением потоками
через `configs/inference_threading.py`. Однако ряд ключевых настроек
производительности не был задействован:

- ORT использовал дефолтный граф без явной оптимизации
- ORT не сохранял оптимизированный граф на диск (повторная оптимизация при каждом старте)
- OpenVINO не получал PERFORMANCE_HINT
- OpenVINO не кэшировал скомпилированную под конкретный CPU модель

---

## Реализованные изменения

### 4.1 — ONNX Runtime SessionOptions

**Файл:** `configs/inference_threading.py` → `_patch_onnxruntime()`

**Проблема:** Ultralytics создаёт `onnxruntime.InferenceSession` внутри
`AutoBackend.__init__()` и **не предоставляет публичного API** для передачи
кастомного `SessionOptions`. Прямое изменение `_LazyModel._load()` в
`sign_models.py` не даёт доступа к этому объекту.

**Решение:** SessionOptions настраиваются через уже существующий
monkey-patch `InferenceSession.__init__` в `inference_threading.py`.
Это единственное место, где можно перехватить создание сессии до того,
как Ultralytics успеет её инициализировать.

**Применённые опции:**

| Опция | Значение | Эффект |
|---|---|---|
| `graph_optimization_level` | `ORT_ENABLE_ALL` | Constant folding, op fusion, layout optimization, kernel fusion |
| `execution_mode` | `ORT_SEQUENTIAL` | Снижает overhead планировщика при single-batch инференсе |
| `enable_mem_pattern` | `True` | Переиспользование memory buffers между вызовами |
| `enable_cpu_mem_arena` | `True` | ORT управляет своим memory arena, снижает число syscalls alloc/free |

> **Примечание:** `ORT_SEQUENTIAL` оптимален для нашего сценария (1 изображение
> за раз). При батч-инференсе N > 8 стоит оценить `ORT_PARALLEL`.

**Почему не в `sign_models.py`:**  
Ultralytics `YOLO(path)` → `AutoBackend.__init__()` → `ort.InferenceSession(path)`
вызывается синхронно без возможности передать `sess_options` снаружи.
Обходные пути (форк AutoBackend, subclassing YOLO) создают maintenance burden
и несовместимость при обновлении Ultralytics. Monkey-patch `__init__` —
наименее инвазивный и уже используемый в проекте подход.

---

### 4.2 — Кэширование скомпилированных моделей

**Файл:** `configs/inference_threading.py`

#### ONNX Runtime — optimized_model_filepath

**Где:** `_patch_onnxruntime()` → внутри `_patched_init()`

При первом запуске ORT применяет graph optimization и сохраняет
результат как `<model>.opt.onnx` рядом с исходным файлом.
При повторных запусках загружается оптимизированный граф напрямую,
минуя фазу оптимизации (~200-500 мс на модель).

```
CNN_side/best.onnx          ← исходный файл (экспортированный)
CNN_side/best.opt.onnx      ← создаётся ORT при первом запуске
```

**Файл:** `scripts/export_models_onnx.py`

Добавлен информационный лог с ожидаемым путём `<model>.opt.onnx`.
Фактическое создание файла выполняет ORT автоматически при первой
загрузке через `inference_threading._patched_init()`.

#### OpenVINO — CACHE_DIR

**Где:** `_patch_openvino()` → `_patched_core_init()`

OpenVINO кэширует скомпилированную под конкретный CPU модель. Повторная
загрузка из кэша в **3–5x быстрее** первичной компиляции.

**Путь кэша:** `.kiro/model_cache/openvino/` (относительно корня проекта)

```
<project_root>/
  .kiro/
    model_cache/
      openvino/          ← бинарный кэш OpenVINO
```

Директория создаётся автоматически через `os.makedirs(exist_ok=True)`.

> ⚠️ При обновлении модели или смене CPU кэш необходимо очистить вручную.
> OpenVINO НЕ инвалидирует кэш при изменении .xml/.bin файлов.

---

### 4.4 — OpenVINO PERFORMANCE_HINT: THROUGHPUT

**Файл:** `configs/inference_threading.py` → `_patch_openvino()`

**Применяется двумя способами (для надёжности):**

1. **`Core.set_property("CPU", {"PERFORMANCE_HINT": "THROUGHPUT"})`**  
   Вызывается в monkey-patch `Core.__init__()` сразу после инициализации core.
   Устанавливает глобальный хинт для всех моделей, компилируемых этим core.

2. **`config.setdefault("PERFORMANCE_HINT", "THROUGHPUT")`**  
   В monkey-patch `Core.compile_model()` как fallback, если `__init__`-патч
   не сработал (например, при прямом вызове `compile_model` из Ultralytics).

**Значения хинта:**

| Значение | Описание | Лучше для |
|---|---|---|
| `THROUGHPUT` | Async pipeline с micro-batching внутри OV runtime | Непрерывный видеопоток |
| `LATENCY` | Минимальное время первого ответа | Единичные запросы |
| `CUMULATIVE_THROUGHPUT` | Максимальный суммарный throughput | Большие батчи |

Выбран `THROUGHPUT` как оптимальный для нашего сценария
(непрерывный видеопоток, 1–30 FPS обработки).

---

## TODO — Требуют бенчмарков до/после

### 4.3 — Батчинг CNN (ОТЛОЖЕНО)

**Почему отложено:**  
Предыдущий эксперимент с батчингом (commit 29acf57, откачен в 1c84127)
показал **−36% производительности** на CPU при малых батчах (N < 5).
Подробный анализ: `docs/BATCHING_FAILURE_ANALYSIS.md`.

**Условия для повторной оценки:**
- Подтверждённый прирост от 4.1/4.2/4.4 (базовые метрики)
- Среднее число знаков на кадр ≥ 8
- Либо переход на GPU-backend

**Метрики для измерения:**
```
[ ] FPS baseline после 4.1/4.2/4.4 (без батчинга)
[ ] FPS с батчингом при N=4, N=8, N=16
[ ] Время инференса per-sign: одиночный vs батч
[ ] Overhead сборки батча (numpy concatenate time)
```

### 4.5 — INT8 квантизация (ОТЛОЖЕНО)

**Потенциальный прирост:** 1.5–2x скорость инференса при ~1% потере точности

**Требования:**
- Калибровочный датасет (репрезентативные кропы знаков)
- Метрики точности baseline (mAP, top-1 accuracy per model)
- Инфраструктура для автоматического сравнения точности

**Инструменты:**
- ONNX: `onnxruntime.quantization.quantize_dynamic` или `quantize_static`
- OpenVINO: `openvino.tools.pot` (Post-Training Optimization Toolkit)

**Риски:**
- Потеря точности на редких классах знаков (малый датасет)
- Различное поведение динамической vs статической квантизации
- Необходимость раздельной квантизации для detect/classify/segment моделей

---

## Бенчмарки

> **⚠️ Placeholder — заполнить после запуска тестов**

### Методология

```bash
# Запуск бенчмарка детектора
python scripts/benchmark_detector.py --backend onnx --video <test_video.mp4>
python scripts/benchmark_detector.py --backend openvino --video <test_video.mp4>

# End-to-end бенчмарк
python scripts/benchmark_end_to_end_cpu.py --video <test_video.mp4>
```

### Результаты: ONNX Runtime

| Метрика | До (baseline) | После 4.1+4.2 | Δ |
|---|---|---|---|
| FPS (со знаками) | — | — | — |
| FPS (без знаков) | — | — | — |
| Время загрузки модели (холодный старт) | — | — | — |
| Время загрузки модели (тёплый старт, .opt.onnx) | — | — | — |
| Инференс 1 кадра, avg ms | — | — | — |

### Результаты: OpenVINO

| Метрика | До (baseline) | После 4.2+4.4 | Δ |
|---|---|---|---|
| FPS (со знаками) | — | — | — |
| FPS (без знаков) | — | — | — |
| Время загрузки модели (холодный старт) | — | — | — |
| Время загрузки модели (тёплый старт, кэш) | — | — | — |
| Инференс 1 кадра, avg ms | — | — | — |

### Базовые метрики проекта (до этих изменений)

Из `docs/BATCHING_FAILURE_ANALYSIS.md`:

```
Со знаками:  1.0-1.1 FPS
Без знаков:  2.7-2.9 FPS
Backend:     ONNX / OpenVINO (CPU)
```

---

## Технические детали реализации

### Архитектура monkey-patch

```
apply_cpu_thread_limits()
    ├── _patch_onnxruntime()
    │     Патчит: ort.InferenceSession.__init__
    │     Добавляет: SessionOptions (4.1) + optimized_model_filepath (4.2)
    │     Применяется: при любом вызове YOLO(onnx_path) из _LazyModel._load()
    │
    └── _patch_openvino()
          Патчит: ov.Core.__init__ + ov.Core.compile_model
          Добавляет: PERFORMANCE_HINT (4.4) + CACHE_DIR (4.2) + INFERENCE_NUM_THREADS
          Применяется: при любом вызове YOLO(openvino_path) из _LazyModel._load()
```

### Порядок применения патчей

Критично вызывать `apply_cpu_thread_limits()` **до** первого `_LazyModel._load()`:

1. `main.py::setup_environment()` — главный процесс
2. `processing/detector_process_pool.py::_worker_process_frame()` — воркеры pool

Патчи идемпотентны (`_patched_onnx`, `_patched_openvino` флаги).

### Совместимость с `_patched_init` (потоки)

Новые SessionOptions **не перезаписывают** явно переданные значения.
Если Ultralytics в будущих версиях начнёт передавать `sess_options`,
наш код применит дополнительные настройки поверх них, не ломая логику.

---

## Связанные документы

- `docs/BATCHING_FAILURE_ANALYSIS.md` — анализ провала батчинга (4.3 context)
- `configs/inference_threading.py` — полная реализация патчей
- `configs/sign_models.py` — _LazyModel, точка загрузки моделей
- `scripts/export_models_onnx.py` — экспорт моделей в ONNX/OpenVINO
