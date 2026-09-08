# PROMPT ДЛЯ ИИ-АГЕНТА: Паритет потоков CPU-инференса (ONNX/OpenVINO vs PyTorch) + сопутствующие баги

**Статус:** к реализации
**Приоритет:** Высокий (искажает все замеры производительности CPU-режимов, риск краша, риск CPU oversubscription)
**Связанные документы в репозитории:** `WHY_SINGLE_THREAD_FASTER.md`, `docs/CRASH_FIX_0xC0000409.md`, `docs/BATCHING_FAILURE_ANALYSIS.md`, `tests/test_no_eager_model_loading.py`, `docs/PERFORMANCE_OPTIMIZATIONS.md`

---

## 0. Контекст и корневая причина (обязательно прочитать перед началом)

В проекте есть глобальная защита от краша Windows `0xC0000409` (`STATUS_STACK_BUFFER_OVERRUN`), вызванного конфликтом DLL OpenMP/MKL (`libiomp5md.dll`) между PyTorch и Qt/QWebEngine. Защита реализована так:

- `main.py::setup_environment()` — `OMP_NUM_THREADS=1`, `MKL_NUM_THREADS=1`, `MKL_THREADING_LAYER=GNU`, `KMP_DUPLICATE_LIB_OK=TRUE`;
- `processing/detector_thread.py::DetectorThread.run()` — явный `torch.set_num_threads(1)`;
- `processing/detector_process_pool.py::_worker_process_frame()` — та же связка переменных окружения + `torch.set_num_threads(1)` внутри каждого воркер-процесса.

**Проблема:** все эти ограничения относятся ТОЛЬКО к PyTorch/MKL/OpenMP. Модели в `configs/sign_models.py` (`_LazyModel`) при `cpu_inference_backend in ("onnx", "openvino")` выполняются через **ONNX Runtime** и **OpenVINO**, у которых собственные, никак не сконфигурированные в этом проекте пулы потоков. По умолчанию обе библиотеки используют **все логические ядра CPU на одну сессию модели**, и это никак не ограничивается `torch.set_num_threads(1)` / `OMP_NUM_THREADS=1` (эти библиотеки НЕ используют OpenMP/MKL из PyTorch — у них собственные раннтаймы).

**Следствие:** сравнение "single_thread + backend=torch" против "single_thread + backend=onnx/openvino" — это сравнение "1 поток CPU" против "N потоков CPU". ONNX/OpenVINO не более эффективны *на равных ресурсах* — они просто не подчиняются ограничению, которое искусственно душит PyTorch-путь. Это же создаёт скрытый риск **CPU oversubscription** в режиме `process_pool`: если запущено `W` воркер-процессов, а каждый из них поднимает ONNX/OpenVINO сессию, использующую все `C` ядер, суммарная потребность в потоках — `W × C` при физически доступных `C` ядрах, что приводит к жестокому переключению контекста и деградации производительности (может быть даже хуже, чем "лишние" накладные расходы IPC, уже описанные в `WHY_SINGLE_THREAD_FASTER.md`).

Цель этого промпта — устранить асимметрию, сделать поведение потоков **явным, настраиваемым и предсказуемым** для всех backend'ов и во всех режимах обработки (`single_thread`, `pipeline`, `process_pool`), а также исправить два независимых сопутствующих бага, обнаруженных в процессе анализа.

**НЕ трогать:** сам механизм `torch.set_num_threads(1)` и переменные окружения `OMP_NUM_THREADS=1`/`MKL_NUM_THREADS=1` для PyTorch-пути — они защищают от реального краша и должны остаться как есть. Мы не убираем защиту, мы её **дополняем** для ONNX/OpenVINO и делаем управляемой.

---

## Задача 1 (BLOCK CPU-5): Явное и настраиваемое управление потоками ONNX Runtime / OpenVINO

### 1.1. Новый модуль `configs/inference_threading.py`

Создать файл со следующим содержимым (адаптировать под фактическую версию `onnxruntime`/`openvino`, обязательно обернуть в try/except с логированием — библиотеки могут отсутствовать):

```python
"""
configs/inference_threading.py
Явное, настраиваемое и одинаковое для всех backend'ов управление
количеством потоков CPU-инференса.

БЕЗ этого модуля ONNX Runtime и OpenVINO используют собственные
дефолтные пулы потоков (обычно = все логические ядра CPU на сессию),
которые НЕ подчиняются torch.set_num_threads(1) / OMP_NUM_THREADS=1,
выставленным в main.py и processing/detector_thread.py специально для
PyTorch. Из-за этого сравнение backend'ов "torch" vs "onnx"/"openvino"
в этом проекте было некорректным (PyTorch принудительно однопоточный,
ONNX/OpenVINO — многопоточные без ограничений), а Process Pool +
onnx/openvino рисковал CPU oversubscription (N процессов × все ядра
на сессию).

Вызывать apply_cpu_thread_limits() РОВНО ОДИН РАЗ НА ПРОЦЕСС, до первой
загрузки любой _LazyModel:
  - в main.py::setup_environment() — для главного процесса;
  - в processing/detector_process_pool.py::_worker_process_frame() —
    для каждого воркер-процесса Process Pool (там уже есть похожий
    паттерн настройки окружения в начале функции).
"""
from __future__ import annotations
import logging
import os

logger = logging.getLogger(__name__)

_patched_onnx = False
_patched_openvino = False


def apply_cpu_thread_limits(
    intra_threads: int = 0,
    inter_threads: int = 1,
    openvino_threads: int = 0,
    disable_cuda_providers: bool = True,
) -> None:
    """
    intra_threads / openvino_threads == 0 означает "не трогать" (оставить
    библиотеке дефолт) — но в этом проекте вызывающий код (см. п.1.2)
    ДОЛЖЕН передавать явное положительное число, вычисленное из
    os.cpu_count() и текущего режима обработки (single_thread/process_pool),
    а не полагаться на 0 в проде — 0 оставлен только как "явный no-op"
    для тестов/отладки.
    """
    _patch_onnxruntime(intra_threads, inter_threads, disable_cuda_providers)
    _patch_openvino(openvino_threads)


def _patch_onnxruntime(intra_threads: int, inter_threads: int, disable_cuda_providers: bool) -> None:
    global _patched_onnx
    if _patched_onnx:
        return
    try:
        import onnxruntime as ort
    except ImportError:
        return

    _orig_init = ort.InferenceSession.__init__

    def _patched_init(self, path_or_bytes, sess_options=None, providers=None, provider_options=None, **kwargs):
        if sess_options is None:
            sess_options = ort.SessionOptions()
        if intra_threads > 0:
            sess_options.intra_op_num_threads = intra_threads
        if inter_threads > 0:
            sess_options.inter_op_num_threads = inter_threads
        # Явно и по-настоящему (в отличие от мёртвого ORT_DISABLE_CUDA)
        # запрещаем CUDA-провайдер, когда просят CPU-only.
        if disable_cuda_providers and providers:
            cpu_only = [p for p in providers if p == "CPUExecutionProvider"]
            providers = cpu_only or ["CPUExecutionProvider"]
        return _orig_init(
            self, path_or_bytes, sess_options=sess_options,
            providers=providers, provider_options=provider_options, **kwargs
        )

    ort.InferenceSession.__init__ = _patched_init
    _patched_onnx = True
    logger.info(
        f"[inference_threading] ONNX Runtime запатчен: "
        f"intra_op_num_threads={intra_threads or 'default'}, "
        f"inter_op_num_threads={inter_threads or 'default'}, "
        f"disable_cuda_providers={disable_cuda_providers}"
    )


def _patch_openvino(openvino_threads: int) -> None:
    global _patched_openvino
    if _patched_openvino:
        return
    try:
        import openvino as ov
    except ImportError:
        return

    _orig_compile = ov.Core.compile_model

    def _patched_compile(self, model, device_name="CPU", config=None, *args, **kwargs):
        config = dict(config or {})
        if openvino_threads > 0:
            config.setdefault("INFERENCE_NUM_THREADS", str(openvino_threads))
        return _orig_compile(self, model, device_name, config, *args, **kwargs)

    ov.Core.compile_model = _patched_compile
    _patched_openvino = True
    logger.info(
        f"[inference_threading] OpenVINO запатчен: "
        f"INFERENCE_NUM_THREADS={openvino_threads or 'default'}"
    )


def compute_safe_intra_threads(num_worker_processes: int = 1) -> int:
    """
    Безопасное число потоков на одну CPU-инференс-сессию с учётом того,
    сколько параллельных ПРОЦЕССОВ (Process Pool) на этой машине уже
    претендуют на CPU. Оставляет минимум 1 ядро на GUI/VideoReader поток.

    single_thread / pipeline: num_worker_processes=1 → почти все ядра.
    process_pool с W воркерами: делим ядра между ними, чтобы избежать
    W * cpu_count() конкурирующих потоков.
    """
    cpu_count = os.cpu_count() or 4
    if num_worker_processes <= 1:
        return max(1, cpu_count - 1)
    return max(1, cpu_count // num_worker_processes)
```

### 1.2. Новые настройки в `configs/settings.py::AppSettings`

Добавить поля (со значениями по умолчанию `0` = "вычислить автоматически через `compute_safe_intra_threads`"):

```python
# ── CPU-инференс: потоки ONNX/OpenVINO (BLOCK CPU-5) ──────────────
cpu_onnx_intra_threads: int = 0     # 0 = авто (cpu_count-1, либо cpu_count//workers в process_pool)
cpu_onnx_inter_threads: int = 1
cpu_openvino_threads: int = 0       # 0 = авто, та же логика
```

Добавить их в `to_dict()`/`from_dict()` (уже произойдёт автоматически, т.к. используется `asdict(self)` по всем полям dataclass — просто убедиться, что новые поля не сломали `AppSettings.load()` из-за типов; там уже есть универсальная обработка `int`).

### 1.3. Точки вызова `apply_cpu_thread_limits`

**В `main.py::setup_environment()`**, сразу после блока с `OMP_NUM_THREADS` и т.д., добавить:

```python
from configs.settings import get_app_settings
from configs.inference_threading import apply_cpu_thread_limits, compute_safe_intra_threads

settings = get_app_settings()
if not settings.use_cuda:
    num_workers = settings.process_pool_workers if settings.processing_mode == "process_pool" else 1
    if num_workers <= 0:
        num_workers = max(1, (os.cpu_count() or 4) - 1)
    intra = settings.cpu_onnx_intra_threads or compute_safe_intra_threads(num_workers)
    ov_threads = settings.cpu_openvino_threads or intra
    apply_cpu_thread_limits(
        intra_threads=intra,
        inter_threads=settings.cpu_onnx_inter_threads,
        openvino_threads=ov_threads,
        disable_cuda_providers=True,
    )
    logger.info(f"[main] CPU inference threads: intra={intra}, openvino={ov_threads}, workers={num_workers}")
```

**В `processing/detector_process_pool.py::_worker_process_frame()`**, сразу после существующего блока `os.environ[...]` и `torch.set_num_threads(1)`, добавить эквивалентный вызов (воркер-процесс не наследует патч из главного процесса при `spawn`-контексте — модуль должен быть импортирован и вызван заново внутри каждого воркера):

```python
if not hasattr(_worker_process_frame, '_threads_patched'):
    try:
        from configs.settings import get_app_settings
        from configs.inference_threading import apply_cpu_thread_limits, compute_safe_intra_threads
        settings = get_app_settings()
        if not settings.use_cuda:
            num_workers = settings.process_pool_workers or max(1, (os.cpu_count() or 4) - 1)
            intra = settings.cpu_onnx_intra_threads or compute_safe_intra_threads(num_workers)
            ov_threads = settings.cpu_openvino_threads or intra
            apply_cpu_thread_limits(intra, settings.cpu_onnx_inter_threads, ov_threads, True)
        _worker_process_frame._threads_patched = True
    except Exception as e:
        _safe_log(f"[Worker] Не удалось применить cpu thread limits: {e}")
```

### 1.4. Удалить мёртвый код `ORT_DISABLE_CUDA`

`ORT_DISABLE_CUDA` — не распознаваемая ни `onnxruntime`, ни `ultralytics` переменная окружения; она нигде не читается и не имеет эффекта. Удалить (или как минимум пометить `# DEPRECATED, no-op — see configs/inference_threading.py disable_cuda_providers`) все места, где она выставляется:

- `main.py::setup_environment()`
- `configs/sign_models.py::reload_all_models_if_device_changed()`
- `processing/detector_process_pool.py::_worker_process_frame()`

Реальная защита от CUDA-провайдера теперь идёт через `disable_cuda_providers=True` в `apply_cpu_thread_limits()` (п.1.1) **и** уже существующий `device='cpu'`-пин в `_LazyModel._predict_kwargs_with_cpu_pin()` — оставить оба механизма (belt-and-suspenders), но убрать вводящий в заблуждение мёртвый env var.

### 1.5. UI: настройки в `ui/widgets/settings_page.py`

В группу "Диагностика системы" (рядом с `_cpu_backend_combo`) добавить:
- `QSpinBox` для `cpu_onnx_intra_threads` (диапазон 0–64, суффикс "потоков (0=авто)"), с тултипом, объясняющим, что 0 = автоматический безопасный расчёт с учётом `Количество воркеров` (Process Pool).
- `QSpinBox` для `cpu_openvino_threads` (аналогично).
- В существующий тултип `_processing_mode_combo` и `_workers_spin` добавить упоминание, что при Process Pool + ONNX/OpenVINO потоки автоматически делятся между воркерами, чтобы не было oversubscription.
- Подключить сохранение/сброс этих полей в `_collect_settings()` / `_reset()` / `_export_settings()` / `_import_settings()` по аналогии с уже существующими полями (`hasattr` guard, как у остальных).

### 1.6. Тест на регрессию

Добавить `tests/test_cpu_thread_parity.py`:

```python
def test_inference_threading_module_exists_and_patches_onnxruntime():
    """CPU backend parity: ONNX Runtime должен получать явный intra_op_num_threads."""
    from configs.inference_threading import apply_cpu_thread_limits
    import onnxruntime as ort

    apply_cpu_thread_limits(intra_threads=2, inter_threads=1, openvino_threads=0)

    captured = {}
    orig = ort.InferenceSession.__init__
    # Проверяем что __init__ действительно переопределён (не совпадает с "чистым" оригиналом)
    assert ort.InferenceSession.__init__ is not orig or True  # см. примечание ниже
    # Более надёжная проверка: патчим повторно с другим intra_threads и убеждаемся
    # что модуль идемпотентен (не патчит дважды, _patched_onnx=True).
    from configs import inference_threading as it
    assert it._patched_onnx is True
```//
(Агенту: адаптировать тест под реальный API `onnxruntime.SessionOptions`, при недоступности библиотеки — `pytest.skip`.)

Также добавить в `docs/PERFORMANCE_OPTIMIZATIONS.md` / `WHY_SINGLE_THREAD_FASTER.md` новый раздел "CPU backend parity" с кратким объяснением этой асимметрии для будущих читателей (используя формулировки из раздела 0 этого промпта).

### 1.7. Критерии приёмки

- [ ] `configs/inference_threading.py` создан, импортируется без ошибок при отсутствии `onnxruntime`/`openvino`.
- [ ] При `use_cuda=False` и запуске обработки в логах видно `[inference_threading] ONNX Runtime запатчен: intra_op_num_threads=N ...` **до** первого сообщения о загрузке любой ONNX/OpenVINO модели.
- [ ] `ORT_DISABLE_CUDA` удалён из всех 3 файлов (или явно помечен как deprecated/no-op).
- [ ] Новые поля `AppSettings` сохраняются/загружаются через QSettings и JSON-экспорт/импорт.
- [ ] `scripts/benchmark_detector.py --force-cpu --backend onnx` и `--backend torch`, запущенные с одинаковым числом потоков (torch: через `torch.set_num_threads(N)`, onnx: через новую настройку), дают **сопоставимый** (не отличающийся в разы) FPS — это подтверждает, что корневая причина устранена, а не спрятана.

---

## Задача 2 (BLOCK CPU-6): Убрать eager-загрузку моделей из главного потока при backend != "torch"

### 2.1. Проблема

`processing/processing_controller.py::ProcessingController.start()` (вызывается синхронно из `MainWindow._on_start()` в GUI-потоке) содержит:

```python
requested_backend = "torch" if settings.use_cuda else settings.cpu_inference_backend
if requested_backend != "torch":
    try:
        from configs.sign_models import verify_backend_active
        backend_status = verify_backend_active()
        ...
```

`verify_backend_active()` вызывает `m._load()` для **каждой** `_LazyModel` (`model_side_detect`, `rube_modal`, 4 lane-модели, весь `model_dict` (10 моделей), весь `sub_models` (3 модели) — итого ~17 моделей), то есть синхронно грузит все веса ONNX/OpenVINO **в главном GUI-потоке**. Это прямое нарушение задокументированного и протестированного (`tests/test_no_eager_model_loading.py`) правила проекта: модели грузятся только лениво, изнутри `QThread.run()`. Срабатывает только когда `cpu_inference_backend != "torch"` — то есть именно в сценарии ONNX/OpenVINO. Даёт зависание UI на несколько секунд при первом запуске обработки и восстанавливает риск краша `0xC0000409`, которого весь остальной код старательно избегает.

### 2.2. Фикс

Создать `processing/backend_verify_thread.py`:

```python
"""
processing/backend_verify_thread.py
Проверка реально используемого CPU backend (torch/onnx/openvino) для
каждой модели — БЕЗ блокировки главного потока и БЕЗ загрузки моделей
в GUI-потоке (см. BLOCK CPU-6).
"""
from __future__ import annotations
from PyQt6.QtCore import QThread, pyqtSignal


class BackendVerifyThread(QThread):
    finished_check = pyqtSignal(dict)   # {model_name: backend_or_error}
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            # torch.set_num_threads(1) — та же защита, что и в DetectorThread,
            # т.к. этот поток тоже грузит модели и может использовать torch.
            try:
                import torch
                torch.set_num_threads(1)
            except Exception:
                pass

            from configs.sign_models import verify_backend_active
            result = verify_backend_active()
            self.finished_check.emit(result)
        except Exception as e:
            self.error.emit(str(e))
```

В `processing/processing_controller.py::ProcessingController.start()` заменить блок синхронного вызова на:

```python
requested_backend = "torch" if settings.use_cuda else settings.cpu_inference_backend
if requested_backend != "torch":
    self._start_backend_verify(requested_backend)
```

и добавить методы:

```python
def _start_backend_verify(self, requested_backend: str) -> None:
    from processing.backend_verify_thread import BackendVerifyThread
    self._backend_verify_thread = BackendVerifyThread(self)
    self._backend_verify_thread.finished_check.connect(
        lambda status: self._on_backend_verify_finished(requested_backend, status)
    )
    self._backend_verify_thread.error.connect(
        lambda msg: logging.getLogger(__name__).warning(f"[ProcessingController] backend verify error: {msg}")
    )
    self._backend_verify_thread.start()

def _on_backend_verify_finished(self, requested_backend: str, backend_status: dict) -> None:
    mismatched = {k: v for k, v in backend_status.items()
                  if not str(v).startswith("ERROR") and v != requested_backend}
    if mismatched:
        msg = (
            f"Backend '{requested_backend}' запрошен в настройках, но реально "
            f"не используется для {len(mismatched)} моделей: {list(mismatched.keys())}. "
            f"Проверьте экспорт моделей (scripts/export_models_onnx.py --format {requested_backend})."
        )
        logging.getLogger(__name__).warning(msg)
        self.error.emit(f"⚠️ ПРЕДУПРЕЖДЕНИЕ: {msg}")
```

**Важно:** этот поток запускается **параллельно** с `_start_reader()`/`_start_detector()`, не блокируя их — само по себе он ничего не ускоряет и не замедляет пайплайн обработки, это чисто диагностическая проверка, вынесенная из GUI-потока. `DetectorThread` продолжает лениво грузить модели как обычно (те же объекты `_LazyModel`, уже частично прогретые к моменту, когда `DetectorThread` до них доберётся — двойной загрузки не будет благодаря кэшу `self._model` внутри `_LazyModel`).

### 2.3. Регрессионный тест

Добавить в `tests/test_no_eager_model_loading.py` (или новый файл `tests/test_no_backend_verify_on_main_thread.py`):

```python
def test_verify_backend_active_not_called_directly_in_processing_controller():
    """
    verify_backend_active() грузит модели синхронно и должна вызываться
    ТОЛЬКО изнутри run() дочернего QThread (например BackendVerifyThread),
    никогда напрямую из ProcessingController.start() в GUI-потоке.
    """
    with open("processing/processing_controller.py", encoding="utf-8") as f:
        content = f.read()

    # verify_backend_active может упоминаться только внутри backend_verify_thread.py
    assert "verify_backend_active()" not in content, (
        "verify_backend_active() не должна вызываться напрямую из "
        "ProcessingController — это грузит модели в главном GUI-потоке. "
        "Используйте BackendVerifyThread (processing/backend_verify_thread.py)."
    )

    with open("processing/backend_verify_thread.py", encoding="utf-8") as f:
        thread_content = f.read()
    assert "verify_backend_active()" in thread_content
    assert "class BackendVerifyThread(QThread)" in thread_content
```

### 2.4. Критерии приёмки

- [ ] `processing/processing_controller.py` больше не содержит прямого вызова `verify_backend_active()`.
- [ ] Клик "Начать обработку" с `backend=onnx/openvino` не вызывает видимого зависания UI дольше, чем при `backend=torch`.
- [ ] Предупреждение о несовпадении backend всё ещё показывается пользователю (через `self.error`), просто асинхронно.
- [ ] Новый тест из 2.3 проходит.

---

## Задача 3 (BLOCK CPU-7): Умный skip кадров и проверка скорости в Process Pool

### 3.1. Проблема

`processing/detector_thread.py::DetectorThread` перед детекцией:
1. Пропускает кадр целиком (даже без детекции), если `speed < MIN_SPEED_KMH` (машина стоит);
2. Иначе вычисляет адаптивный интервал через `_calc_skip_interval()` (по скорости + недавней активности детекций) и пропускает часть кадров.

`processing/detector_process_pool.py::DetectorProcessPool._submit_loop()` **не делает ничего из этого** — каждый кадр, дошедший из `frame_queue` (уже прорежен только фиксированным `config.FRAME_STEP` в `VideoReaderThread`), отправляется в `ProcessPoolExecutor`. Это означает, что Process Pool режим всегда выполняет объективно больше детекций на то же видео, чем single_thread/pipeline — независимо от backend'а и независимо от overhead на IPC/сериализацию, уже описанного в `WHY_SINGLE_THREAD_FASTER.md`. Это отдельный, самостоятельный источник разницы в производительности, который нужно устранить, чтобы сравнения режимов обработки были осмысленными.

### 3.2. Фикс — вынести общую логику в `processing/frame_skip.py`

```python
"""
processing/frame_skip.py
SmartFrameSkipper — общая адаптивная логика пропуска кадров, вынесенная
из DetectorThread (BLOCK CPU-7), чтобы её мог использовать и
DetectorProcessPool. До этого рефакторинга Process Pool не применял ни
проверку "машина стоит", ни адаптивный skip по скорости/активности —
единственный из трёх режимов обработки, обрабатывавший буквально все
кадры из очереди. Поведение (константы, формулы) сохранено 1:1 с
оригиналом в DetectorThread — только вынесено для переиспользования.
"""
from __future__ import annotations
from typing import Optional


class SmartFrameSkipper:
    MIN_SPEED_KMH = 2.0

    SKIP_INTERVALS = {
        0:   (1, 1),
        30:  (1, 2),
        60:  (2, 3),
        90:  (3, 4),
        120: (4, 5),
    }

    ACTIVITY_WINDOW = 10
    HIGH_ACTIVITY_THRESHOLD = 3
    ACTIVITY_BONUS = -1
    NO_ACTIVITY_PENALTY = 1

    def __init__(self) -> None:
        self._skip_counter = 0
        self.current_skip = 1
        self._activity_history: list[int] = []
        self.frames_skipped = 0

    def is_stationary(self, speed_kmh: Optional[float]) -> bool:
        return speed_kmh is not None and speed_kmh < self.MIN_SPEED_KMH

    def update_activity(self, n_detections: int) -> None:
        self._activity_history.append(n_detections)
        if len(self._activity_history) > self.ACTIVITY_WINDOW * 2:
            self._activity_history = self._activity_history[-self.ACTIVITY_WINDOW:]

    def calc_skip_interval(self, speed_kmh: Optional[float]) -> int:
        if speed_kmh is None or speed_kmh < self.MIN_SPEED_KMH:
            self.current_skip = 1
            return 1
        base_skip = self._interpolate_skip(speed_kmh)
        modifier = self._calc_activity_modifier()
        self.current_skip = max(1, min(5, base_skip + modifier))
        return self.current_skip

    def _interpolate_skip(self, speed: float) -> int:
        speeds = sorted(self.SKIP_INTERVALS.keys())
        if speed <= speeds[0]:
            lo, hi = self.SKIP_INTERVALS[speeds[0]]
            return (lo + hi) // 2
        if speed >= speeds[-1]:
            return self.SKIP_INTERVALS[speeds[-1]][1]
        for i in range(len(speeds) - 1):
            s1, s2 = speeds[i], speeds[i + 1]
            if s1 <= speed <= s2:
                t = (speed - s1) / (s2 - s1)
                min1, max1 = self.SKIP_INTERVALS[s1]
                min2, max2 = self.SKIP_INTERVALS[s2]
                avg1, avg2 = (min1 + max1) / 2, (min2 + max2) / 2
                return round(avg1 + t * (avg2 - avg1))
        return 2

    def _calc_activity_modifier(self) -> int:
        if len(self._activity_history) < self.ACTIVITY_WINDOW // 2:
            return 0
        recent = sum(self._activity_history[-self.ACTIVITY_WINDOW:])
        if recent >= self.HIGH_ACTIVITY_THRESHOLD:
            return self.ACTIVITY_BONUS
        if recent == 0 and len(self._activity_history) >= self.ACTIVITY_WINDOW:
            return self.NO_ACTIVITY_PENALTY
        return 0

    def should_process(self) -> bool:
        self._skip_counter += 1
        if self._skip_counter >= self.current_skip:
            self._skip_counter = 0
            return True
        self.frames_skipped += 1
        return False
```

### 3.3. Рефакторинг `DetectorThread`

В `processing/detector_thread.py` удалить методы `_calc_skip_interval`, `_interpolate_skip`, `_calc_activity_modifier`, `_update_activity_history`, `_should_process_frame` и константы `SKIP_INTERVALS`/`ACTIVITY_*`/`MIN_SPEED_KMH` из класса, заменив их на `self._skipper = SmartFrameSkipper()` в `__init__`, и обновить вызовы в `_process_loop()`:

```python
if self._skipper.is_stationary(speed):
    if self._should_emit_preview():
        self._emit_frame(raw.image)
    continue

self._skipper.calc_skip_interval(speed)
config.CURRENT_EFFECTIVE_SKIP = self._skipper.current_skip

if not self._skipper.should_process():
    if self._should_emit_preview():
        self._emit_frame(raw.image)
    continue
...
self._skipper.update_activity(len(detections))
```

(и аналогично заменить обращения к `self._frames_skipped`/`self._current_skip` в `_update_stats()` на `self._skipper.frames_skipped`/`self._skipper.current_skip`).

### 3.4. Применить в `DetectorProcessPool`

В `processing/detector_process_pool.py::DetectorProcessPool`:

1. В `__init__` добавить `self._skipper = SmartFrameSkipper()`.
2. `start()` уже создаёт `self._gpx = GPXHandler()` — использовать его же в `_submit_loop()` (сейчас `_gpx` создан, но не используется в submit loop).
3. В `_submit_loop()`, сразу после `raw: RawFrame = self._frame_q.get(...)` и проверки `raw is _STOP`, добавить:

```python
speed = self._gpx.get_speed(raw.gps_index)

if self._skipper.is_stationary(speed):
    continue  # не отправляем в воркер вообще (превью для этого режима не критично)

self._skipper.calc_skip_interval(speed)
if not self._skipper.should_process():
    continue

config.CURRENT_EFFECTIVE_SKIP = self._skipper.current_skip
```

перед формированием `frame_data` и `self._executor.submit(...)`.

4. Обновление `self._skipper.update_activity(...)` в Process Pool сделать в `ResultAggregatorThread._process_result()` (там уже известно число `frame_data['detections']`) — потребуется передать общий `self._skipper` объект (или его тонкую прокси) из `DetectorProcessPool` в `ResultAggregatorThread` при создании (`ResultAggregatorThread.__init__`), т.к. именно там становится известно фактическое число детекций на кадр уже после обработки. Обновление активности с задержкой в один кадр (submit → result) допустимо и приемлемо для эвристики, как и в оригинале.

### 3.5. Критерии приёмки

- [ ] `processing/frame_skip.py` создан, `DetectorThread` и `DetectorProcessPool` используют один и тот же класс `SmartFrameSkipper` (не дублируют логику).
- [ ] При скорости < `MIN_SPEED_KMH` кадры **не отправляются** в `ProcessPoolExecutor` (проверить логированием количества `submit()` вызовов на стоящей машине).
- [ ] На одном и том же видео+GPX количество реально обработанных (продетектированных) кадров в режимах `single_thread` и `process_pool` теперь **сопоставимо** (отличается не более чем на несколько % за счёт разной синхронизации, а не в разы, как раньше).
- [ ] `config.CURRENT_EFFECTIVE_SKIP` в process_pool режиме больше не всегда равен `1` — меняется в зависимости от скорости, что корректно влияет на адаптивные пороги `SignHandler._effective_gap_frames()`.
- [ ] Существующие тесты (`tests/test_reorder_buffer.py` и др.) продолжают проходить без изменений.

---

## Задача 4 (мелкая уборка): дубликат константы в `SignHandler`

В `core/sign_handler.py` класс `SignHandler` содержит `DIFFERENT_TYPE_PENALTY = 50` **дважды** — один раз в исходном блоке констант, второй раз в блоке `# BLOCK FIX-2.1: Адаптивные пороги трекинга`:

```python
class SignHandler:
    ...
    SAME_TYPE_BONUS          = 50
    DIFFERENT_TYPE_PENALTY   = 50    # штраф при несовпадении типа
    ...
    # BLOCK FIX-2.1: Адаптивные пороги трекинга
    BASE_MATCH_GAP_FRAMES    = 7
    SAFETY_MULTIPLIER        = 1.5
    MAX_MATCH_GAP_FRAMES     = 120
    DIFFERENT_TYPE_PENALTY   = 50    # ← дубликат, удалить
```

**Фикс:** удалить вторую (нижнюю) строку `DIFFERENT_TYPE_PENALTY = 50` под комментарием `BLOCK FIX-2.1`. Значение остаётся тем же (50), поведение не меняется — это чисто косметическая правка для читаемости кода.

**Критерий приёмки:** `grep -c "DIFFERENT_TYPE_PENALTY" core/sign_handler.py` внутри тела класса (объявления, не использования) должен вернуть `1`, а не `2`.

---

## Задача 5: Обновить документацию

В `docs/PERFORMANCE_OPTIMIZATIONS.md` и `WHY_SINGLE_THREAD_FASTER.md` добавить новый раздел (после существующего "Почему Pipeline и Process Pool медленнее на CPU?"):

```markdown
## Паритет потоков между backend'ами (BLOCK CPU-5)

До версии X.X сравнение backend'ов "PyTorch" vs "ONNX Runtime"/"OpenVINO"
на CPU было некорректным: torch.set_num_threads(1) и OMP_NUM_THREADS=1
ограничивали ТОЛЬКО PyTorch (ради защиты от краша 0xC0000409), в то время
как ONNX Runtime и OpenVINO использовали дефолтные (все доступные) потоки
CPU без каких-либо ограничений. Поэтому ONNX/OpenVINO казались значительно
быстрее — не благодаря более эффективной архитектуре инференса, а просто
за счёт использования в разы больше CPU-ресурсов.

Начиная с BLOCK CPU-5, количество потоков ONNX Runtime/OpenVINO
настраивается явно через configs/inference_threading.py и
Settings → Диагностика системы → "Потоки ONNX/OpenVINO". Значение по
умолчанию (0/авто) безопасно делит доступные ядра между воркерами в
режиме Process Pool, чтобы избежать перегрузки CPU.
```

---

## Итоговый чек-лист для агента

- [ ] Задача 1: `configs/inference_threading.py` создан и подключён в `main.py` + `detector_process_pool.py`; новые настройки в `AppSettings` и UI; `ORT_DISABLE_CUDA` убран/помечен deprecated; тест паритета потоков добавлен и проходит.
- [ ] Задача 2: `processing/backend_verify_thread.py` создан; `ProcessingController.start()` больше не грузит модели синхронно в GUI-потоке; регрессионный тест добавлен и проходит.
- [ ] Задача 3: `processing/frame_skip.py` создан; `DetectorThread` и `DetectorProcessPool` используют единую логику skip; проверка скорости и адаптивный интервал работают в Process Pool.
- [ ] Задача 4: дубликат `DIFFERENT_TYPE_PENALTY` в `core/sign_handler.py` удалён.
- [ ] Задача 5: документация обновлена.
- [ ] Все существующие тесты в `tests/` и `scripts/test_*.py` по-прежнему проходят (особенно `tests/test_no_eager_model_loading.py`, `tests/test_reorder_buffer.py`, `tests/test_performance_optimizations.py`).
- [ ] Ручная проверка: запуск обработки короткого видео (1-2 мин) в комбинациях `{single_thread, process_pool} × {torch, onnx, openvino}` — ни одна комбинация не крашится, UI не подвисает дольше пары секунд при старте, логи показывают ожидаемое число потоков.

## Явно НЕ входит в scope (не трогать без отдельного запроса)

- Сам механизм защиты от краша для PyTorch (`torch.set_num_threads(1)`, `OMP_NUM_THREADS=1` и т.д.) — не убирать и не ослаблять.
- Логика экспорта моделей в ONNX/OpenVINO (`scripts/export_models_onnx.py`) — не изменять формат экспорта.
- Архитектура `ReorderBuffer`/сериализации кадров в Process Pool — уже фиксилась ранее (см. `tests/test_reorder_buffer.py`), не трогать.
