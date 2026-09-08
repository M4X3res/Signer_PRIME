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

TASK 4.1 — ONNX Runtime SessionOptions (применяются через monkey-patch,
    т.к. Ultralytics не экспонирует SessionOptions через публичный API):
    - graph_optimization_level = ORT_ENABLE_ALL
    - execution_mode = ORT_SEQUENTIAL
    - enable_mem_pattern = True
    - enable_cpu_mem_arena = True

TASK 4.2 — Кэширование скомпилированных моделей:
    - ONNX: optimized_model_filepath → <model>.opt.onnx (рядом с моделью)
    - OpenVINO: CACHE_DIR → .kiro/model_cache/openvino/

TASK 4.4 — OpenVINO PERFORMANCE_HINT = THROUGHPUT:
    - Применяется через Core.__init__ monkey-patch (set_property)
    - Дублируется в compile_model config как fallback

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
    Применяет ограничения потоков для ONNX Runtime и OpenVINO.
    
    Args:
        intra_threads: Число потоков для intra_op в ONNX Runtime (0 = не трогать дефолт)
        inter_threads: Число потоков для inter_op в ONNX Runtime
        openvino_threads: Число потоков для OpenVINO INFERENCE_NUM_THREADS (0 = не трогать)
        disable_cuda_providers: Явно запретить CUDA-провайдер в ONNX Runtime
    
    Note:
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
    """
    Патчит ONNX Runtime InferenceSession для установки потоков, отключения CUDA
    и применения оптимальных SessionOptions.

    TASK 4.1 — SessionOptions:
        Ultralytics создаёт onnxruntime.InferenceSession внутренне и не даёт
        прямого доступа к SessionOptions через публичный API YOLO/AutoBackend.
        Единственный надёжный способ — monkey-patch InferenceSession.__init__,
        который уже применяется здесь для управления потоками. Поэтому настройки
        4.1 добавлены сюда, а не в _LazyModel._load().

    TASK 4.2 — optimized_model_filepath:
        ORT может сохранить граф после graph optimization в .opt.onnx рядом с
        исходным файлом. При повторном запуске этот файл загружается быстрее.
        Путь вычисляется из первого позиционного аргумента (пути к .onnx файлу).
    """
    global _patched_onnx
    if _patched_onnx:
        return

    try:
        import onnxruntime as ort
    except ImportError:
        logger.debug("[inference_threading] ONNX Runtime не установлен, пропуск патча")
        return

    _orig_init = ort.InferenceSession.__init__

    def _patched_init(self, path_or_bytes, sess_options=None, providers=None, provider_options=None, **kwargs):
        if sess_options is None:
            sess_options = ort.SessionOptions()

        # ── TASK 4.1: Явные SessionOptions для максимальной производительности ──
        # graph_optimization_level: включить ВСЕ оптимизации графа (constant folding,
        # op fusion, layout optimization и т.д.)
        sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

        # execution_mode: ORT_SEQUENTIAL снижает overhead планировщика при CPU-инференсе
        # одиночных изображений (наш основной сценарий — sign per sign)
        sess_options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL

        # mem_pattern: включить переиспользование memory buffers между вызовами
        sess_options.enable_mem_pattern = True

        # cpu_mem_arena: разрешить ORT управлять своим memory arena (снижает число
        # системных alloc/free на горячем пути инференса)
        sess_options.enable_cpu_mem_arena = True

        # ── Управление потоками (существующая логика) ──
        if intra_threads > 0:
            sess_options.intra_op_num_threads = intra_threads
        if inter_threads > 0:
            sess_options.inter_op_num_threads = inter_threads

        # ── TASK 4.2: Кэширование скомпилированного (оптимизированного) графа ──
        # Если path_or_bytes — строка пути к .onnx файлу, сохраняем оптимизированную
        # модель рядом с исходной как <name>.opt.onnx. ORT загружает её быстрее при
        # повторном запуске (пропускает фазу оптимизации).
        if isinstance(path_or_bytes, (str, os.PathLike)):
            try:
                onnx_path = str(path_or_bytes)
                opt_path = os.path.splitext(onnx_path)[0] + ".opt.onnx"
                sess_options.optimized_model_filepath = opt_path
                logger.debug(
                    f"[inference_threading] ORT optimized_model_filepath → "
                    f"{os.path.basename(opt_path)}"
                )
            except Exception as _e:
                # Не критично — продолжаем без кэширования
                logger.debug(f"[inference_threading] Не удалось задать optimized_model_filepath: {_e}")

        # ── Отключение CUDA провайдеров (существующая логика) ──
        # Явно и по-настоящему (в отличие от мёртвого ORT_DISABLE_CUDA)
        # запрещаем CUDA-провайдер, когда просят CPU-only.
        if disable_cuda_providers:
            if providers:
                # Фильтруем только CPUExecutionProvider
                cpu_only = [p for p in providers if p == "CPUExecutionProvider"]
                providers = cpu_only if cpu_only else ["CPUExecutionProvider"]
            else:
                providers = ["CPUExecutionProvider"]

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
        f"disable_cuda_providers={disable_cuda_providers}, "
        f"graph_opt=ORT_ENABLE_ALL, exec_mode=ORT_SEQUENTIAL, "
        f"mem_pattern=True, cpu_mem_arena=True, "
        f"optimized_model_filepath=<model>.opt.onnx"
    )


def _patch_openvino(openvino_threads: int) -> None:
    """
    Патчит OpenVINO Core для установки числа потоков, PERFORMANCE_HINT и CACHE_DIR.

    TASK 4.4 — PERFORMANCE_HINT:
        "THROUGHPUT" активирует асинхронный планировщик OV с batching внутри
        самого runtime — оптимально для последовательного потока изображений.
        Альтернатива "LATENCY" лучше при единичных запросах с минимальным временем
        отклика. В нашем сценарии (непрерывный видеопоток) THROUGHPUT предпочтительнее.

    TASK 4.2 — CACHE_DIR:
        OpenVINO может кэшировать скомпилированную под конкретный CPU модель.
        Повторная загрузка из кэша в 3-5x быстрее первичной компиляции.
        Кэш хранится в .kiro/model_cache/ рядом с корнем проекта.

    Патч применяется через Core.set_property() вместо monkey-patch compile_model,
    чтобы настройки действовали глобально и не зависели от того, как Ultralytics
    вызывает compile_model внутри AutoBackend.
    """
    global _patched_openvino
    if _patched_openvino:
        return

    try:
        import openvino as ov
    except ImportError:
        logger.debug("[inference_threading] OpenVINO не установлен, пропуск патча")
        return

    _orig_core_init = ov.Core.__init__

    def _patched_core_init(self, *args, **kwargs):
        _orig_core_init(self, *args, **kwargs)

        # ── TASK 4.4: PERFORMANCE_HINT = THROUGHPUT ──
        try:
            self.set_property("CPU", {"PERFORMANCE_HINT": "THROUGHPUT"})
            logger.debug("[inference_threading] OpenVINO: PERFORMANCE_HINT=THROUGHPUT применён")
        except Exception as _e:
            logger.debug(f"[inference_threading] OpenVINO: не удалось задать PERFORMANCE_HINT: {_e}")

        # ── Управление потоками (существующая логика, теперь через set_property) ──
        if openvino_threads > 0:
            try:
                self.set_property("CPU", {"INFERENCE_NUM_THREADS": str(openvino_threads)})
                logger.debug(
                    f"[inference_threading] OpenVINO: INFERENCE_NUM_THREADS={openvino_threads} применён"
                )
            except Exception as _e:
                logger.debug(f"[inference_threading] OpenVINO: не удалось задать INFERENCE_NUM_THREADS: {_e}")

        # ── TASK 4.2: CACHE_DIR ──
        try:
            cache_dir = _get_openvino_cache_dir()
            os.makedirs(cache_dir, exist_ok=True)
            self.set_property({"CACHE_DIR": cache_dir})
            logger.debug(f"[inference_threading] OpenVINO: CACHE_DIR={cache_dir}")
        except Exception as _e:
            logger.debug(f"[inference_threading] OpenVINO: не удалось задать CACHE_DIR: {_e}")

    ov.Core.__init__ = _patched_core_init

    # Также патчим compile_model для передачи threads через config (fallback)
    _orig_compile = ov.Core.compile_model

    def _patched_compile(self, model, device_name="CPU", config=None, *args, **kwargs):
        config = dict(config or {})
        # setdefault: не перезаписывать явно переданные значения
        config.setdefault("PERFORMANCE_HINT", "THROUGHPUT")
        if openvino_threads > 0:
            config.setdefault("INFERENCE_NUM_THREADS", str(openvino_threads))
        return _orig_compile(self, model, device_name, config, *args, **kwargs)

    ov.Core.compile_model = _patched_compile

    _patched_openvino = True
    logger.info(
        f"[inference_threading] OpenVINO запатчен: "
        f"INFERENCE_NUM_THREADS={openvino_threads or 'default'}, "
        f"PERFORMANCE_HINT=THROUGHPUT, "
        f"CACHE_DIR={_get_openvino_cache_dir()}"
    )


def _get_openvino_cache_dir() -> str:
    """
    Возвращает путь к директории кэша OpenVINO.
    Кэш хранится в .kiro/model_cache/ относительно корня проекта.
    """
    # __file__ → configs/inference_threading.py → родитель → корень проекта
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(project_root, ".kiro", "model_cache", "openvino")


def compute_safe_intra_threads(num_worker_processes: int = 1) -> int:
    """
    Безопасное число потоков на одну CPU-инференс-сессию с учётом того,
    сколько параллельных ПРОЦЕССОВ (Process Pool) на этой машине уже
    претендуют на CPU. Оставляет минимум 1 ядро на GUI/VideoReader поток.
    
    Args:
        num_worker_processes: Количество параллельных воркер-процессов
    
    Returns:
        Безопасное число потоков для одной сессии инференса
    
    Examples:
        single_thread / pipeline: num_worker_processes=1 → почти все ядра.
        process_pool с W воркерами: делим ядра между ними, чтобы избежать
        W * cpu_count() конкурирующих потоков.
    """
    cpu_count = os.cpu_count() or 4
    if num_worker_processes <= 1:
        # Single thread / pipeline: используем все ядра кроме одного (для GUI)
        return max(1, cpu_count - 1)
    
    # Process pool: делим ядра между воркерами
    return max(1, cpu_count // num_worker_processes)
