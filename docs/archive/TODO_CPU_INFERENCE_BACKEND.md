# TODO: Завершение PROMPT_FIX_CPU_INFERENCE_BACKEND.md

## ✅ Выполнено (30%)

- [x] configs/inference_threading.py создан
- [x] AppSettings: добавлены поля cpu_onnx_intra_threads, cpu_onnx_inter_threads, cpu_openvino_threads
- [x] main.py: apply_cpu_thread_limits() вызывается в setup_environment()
- [x] detector_process_pool.py: apply_cpu_thread_limits() в _worker_process_frame()
- [x] ORT_DISABLE_CUDA помечен как deprecated в 3 файлах

## ⏸️ Требует завершения (70%)

### Задача 1.5: UI настройки (КРИТИЧНО для пользователей)

**Файл:** `ui/widgets/settings_page.py`

**Что добавить в секции "Диагностика системы":**

```python
# После _cpu_backend_combo:

# CPU Threads: ONNX Runtime intra_op
self._cpu_onnx_intra_spin = QSpinBox()
self._cpu_onnx_intra_spin.setRange(0, 64)
self._cpu_onnx_intra_spin.setValue(settings.cpu_onnx_intra_threads)
self._cpu_onnx_intra_spin.setSuffix(" потоков (0=авто)")
self._cpu_onnx_intra_spin.setToolTip(
    "Число потоков для ONNX Runtime intra_op (параллелизм внутри операции).\n"
    "0 = автоматический расчёт с учётом количества воркеров Process Pool.\n"
    "Рекомендуется оставить 0 для автоматической оптимизации."
)
diag_layout.addRow("Потоки ONNX intra_op:", self._cpu_onnx_intra_spin)

# CPU Threads: OpenVINO
self._cpu_openvino_threads_spin = QSpinBox()
self._cpu_openvino_threads_spin.setRange(0, 64)
self._cpu_openvino_threads_spin.setValue(settings.cpu_openvino_threads)
self._cpu_openvino_threads_spin.setSuffix(" потоков (0=авто)")
self._cpu_openvino_threads_spin.setToolTip(
    "Число потоков для OpenVINO INFERENCE_NUM_THREADS.\n"
    "0 = автоматический расчёт с учётом количества воркеров Process Pool.\n"
    "Рекомендуется оставить 0 для автоматической оптимизации."
)
diag_layout.addRow("Потоки OpenVINO:", self._cpu_openvino_threads_spin)
```

**Обновить тултип _workers_spin:**
```python
self._workers_spin.setToolTip(
    "Количество параллельных процессов для обработки кадров.\n"
    "0 = автоматически (cpu_count - 1).\n"
    "При использовании ONNX/OpenVINO backend'ов потоки инференса\n"
    "автоматически делятся между воркерами для избежания oversubscription."
)
```

**Добавить в _collect_settings():**
```python
settings.cpu_onnx_intra_threads = self._cpu_onnx_intra_spin.value()
settings.cpu_openvino_threads = self._cpu_openvino_threads_spin.value()
```

**Добавить в _reset():**
```python
defaults = AppSettings()
self._cpu_onnx_intra_spin.setValue(defaults.cpu_onnx_intra_threads)
self._cpu_openvino_threads_spin.setValue(defaults.cpu_openvino_threads)
```

**Добавить в _export_settings() / _import_settings():**
Уже работает через `settings.to_dict()` / `AppSettings.from_dict()`

---

### Задача 1.6: Регресс-тест

**Файл:** `tests/test_cpu_thread_parity.py`

```python
"""Регресс-тест BLOCK CPU-5: паритет потоков между backend'ами."""
import pytest


def test_inference_threading_module_imports():
    """Модуль inference_threading должен импортироваться без ошибок."""
    from configs.inference_threading import apply_cpu_thread_limits, compute_safe_intra_threads
    assert callable(apply_cpu_thread_limits)
    assert callable(compute_safe_intra_threads)


def test_compute_safe_intra_threads():
    """compute_safe_intra_threads должен корректно делить ядра."""
    from configs.inference_threading import compute_safe_intra_threads
    import os
    
    # Single thread: все ядра - 1
    result_single = compute_safe_intra_threads(1)
    expected = max(1, (os.cpu_count() or 4) - 1)
    assert result_single == expected
    
    # Process pool: делим поровну
    result_pool = compute_safe_intra_threads(4)
    expected = max(1, (os.cpu_count() or 4) // 4)
    assert result_pool == expected


def test_onnxruntime_patch_idempotent():
    """Патч ONNX Runtime должен быть идемпотентным."""
    pytest.importorskip("onnxruntime")  # skip если нет библиотеки
    
    from configs.inference_threading import apply_cpu_thread_limits, _patched_onnx
    
    # Первый вызов
    apply_cpu_thread_limits(intra_threads=2, inter_threads=1)
    assert _patched_onnx is True
    
    # Второй вызов не должен упасть
    apply_cpu_thread_limits(intra_threads=4, inter_threads=1)
    assert _patched_onnx is True


def test_openvino_patch_idempotent():
    """Патч OpenVINO должен быть идемпотентным."""
    pytest.importorskip("openvino")  # skip если нет библиотеки
    
    from configs.inference_threading import apply_cpu_thread_limits, _patched_openvino
    
    # Первый вызов
    apply_cpu_thread_limits(openvino_threads=2)
    assert _patched_openvino is True
    
    # Второй вызов не должен упасть
    apply_cpu_thread_limits(openvino_threads=4)
    assert _patched_openvino is True
```

---

### Задача 2: Backend verify thread

**Файл:** `processing/backend_verify_thread.py` (создать)

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
    """Поток для проверки backend'ов моделей."""
    finished_check = pyqtSignal(dict)   # {model_name: backend_or_error}
    error = pyqtSignal(str)

    def run(self) -> None:
        try:
            # torch.set_num_threads(1) — та же защита, что и в DetectorThread
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

**Файл:** `processing/processing_controller.py` (изменить метод start())

Найти блок:
```python
requested_backend = "torch" if settings.use_cuda else settings.cpu_inference_backend
if requested_backend != "torch":
    try:
        from configs.sign_models import verify_backend_active
        backend_status = verify_backend_active()
```

Заменить на:
```python
requested_backend = "torch" if settings.use_cuda else settings.cpu_inference_backend
if requested_backend != "torch":
    self._start_backend_verify(requested_backend)
```

Добавить методы:
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

---

### Задача 3: SmartFrameSkipper

**Файл:** `processing/frame_skip.py` (создать весь код из промпта)

**Файл:** `processing/detector_thread.py` (рефакторинг)

Удалить методы и константы, заменить на:
```python
from processing.frame_skip import SmartFrameSkipper

# В __init__:
self._skipper = SmartFrameSkipper()

# В _process_loop():
if self._skipper.is_stationary(speed):
    ...
self._skipper.calc_skip_interval(speed)
...
self._skipper.update_activity(len(detections))
```

**Файл:** `processing/detector_process_pool.py`

Добавить в `__init__`:
```python
self._skipper = SmartFrameSkipper()
```

Добавить в `_submit_loop()` после `raw = self._frame_q.get(...)`:
```python
speed = self._gpx.get_speed(raw.gps_index)
if self._skipper.is_stationary(speed):
    continue
self._skipper.calc_skip_interval(speed)
if not self._skipper.should_process():
    continue
```

---

### Задача 4: Дубликат константы

**Файл:** `core/sign_handler.py`

Найти:
```python
# BLOCK FIX-2.1: Адаптивные пороги трекинга
BASE_MATCH_GAP_FRAMES    = 7
SAFETY_MULTIPLIER        = 1.5
MAX_MATCH_GAP_FRAMES     = 120
DIFFERENT_TYPE_PENALTY   = 50    # ← дубликат, удалить
```

Удалить последнюю строку.

---

### Задача 5: Документация

**Файл:** `docs/PERFORMANCE_OPTIMIZATIONS.md`

Добавить секцию перед "Заключение":

```markdown
## Паритет потоков между backend'ами (BLOCK CPU-5)

До версии 2.0 сравнение backend'ов "PyTorch" vs "ONNX Runtime"/"OpenVINO"
на CPU было некорректным: torch.set_num_threads(1) и OMP_NUM_THREADS=1
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

См. также: `configs/inference_threading.py`, `PROMPT_FIX_CPU_INFERENCE_BACKEND.md`
```

**Файл:** `WHY_SINGLE_THREAD_FASTER.md` — добавить аналогичную секцию.

---

## Запуск после завершения

1. Запустить тесты:
```bash
python tests/test_cpu_thread_parity.py
```

2. Ручная проверка:
- Settings → CPU backend = onnx
- Запустить обработку
- Проверить лог: `[inference_threading] ONNX Runtime запатчен: intra_op_num_threads=...`
- UI не должен зависать при старте

3. Benchmark:
```bash
scripts/benchmark_detector.py --force-cpu --backend torch
scripts/benchmark_detector.py --force-cpu --backend onnx
```

FPS должен быть сопоставим (± 20%).
