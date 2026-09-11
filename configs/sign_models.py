"""
configs/sign_models.py
Ленивая загрузка YOLO/Keras моделей.

На Windows загрузка YOLO в главном потоке вместе с PyQt6
вызывает краш (конфликт DLL). Поэтому используем lazy loading:
модели создаются только при первом обращении, уже внутри QThread.

BLOCK M: Добавлена поддержка ONNX Runtime и OpenVINO для CPU-инференса.
"""
from __future__ import annotations
import os
import logging

logger = logging.getLogger(__name__)

_last_resolved_device: str | None = None
_last_resolved_backend: str | None = None


def _resolve_device() -> str:
    """
    Определяет device для YOLO-моделей на основе настроек и доступности CUDA.
    Возвращает "cuda:0" если use_cuda=True и CUDA доступна, иначе "cpu".
    """
    try:
        from configs.settings import get_app_settings
        import torch
        settings = get_app_settings()
        if settings.use_cuda and torch.cuda.is_available():
            device = "cuda:0"
            logger.debug(f"[sign_models] Device: {device} (CUDA доступна)")
            return device
    except Exception as e:
        logger.debug(f"[sign_models] Ошибка определения CUDA: {e}")
    
    logger.debug("[sign_models] Device: cpu")
    return "cpu"


def reload_all_models_if_device_changed() -> bool:
    """
    Вызывать ОДИН РАЗ в начале ProcessingController.start() (не на каждый
    кадр!). Если пользователь поменял 'Использовать CUDA' в Settings между
    прогонами в рамках одной сессии приложения, сбрасывает кэш всех
    _LazyModel, чтобы они перезагрузились на новом device при следующем
    обращении. См. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 4.
    
    BLOCK M: Также отслеживает изменение cpu_inference_backend.

    Returns:
        True если модели были сброшены (device или backend реально изменился).
    """
    global _last_resolved_device, _last_resolved_backend
    
    from configs.settings import get_app_settings
    settings = get_app_settings()
    
    # BLOCK M-FIX (BUG-2): синхронизируем ORT_DISABLE_CUDA с текущим use_cuda
    # DEPRECATED: ORT_DISABLE_CUDA не имеет эффекта, см. configs/inference_threading.py
    # Оставлено для обратной совместимости.
    if settings.use_cuda:
        os.environ.pop("ORT_DISABLE_CUDA", None)  # DEPRECATED, no-op
    else:
        os.environ["ORT_DISABLE_CUDA"] = "1"  # DEPRECATED, no-op
    
    current_device = _resolve_device()
    # REFACTOR-1: используем общую функцию вместо дублирования
    current_backend = _resolve_backend_name(settings)
    
    changed = (
        (_last_resolved_device is not None and _last_resolved_device != current_device)
        or (_last_resolved_backend is not None and _last_resolved_backend != current_backend)
    )
    
    if changed:
        logger.info(
            f"[sign_models] Device/Backend изменился "
            f"({_last_resolved_device}/{_last_resolved_backend} → "
            f"{current_device}/{current_backend}), сбрасываем кэш моделей"
        )
        for m in (model_side_detect, rube_modal, model_lane_detect, model_lane_segment):
            m._model = None
            m._device = None
            m._backend = None
        for m in model_dict.values():
            m._model = None
            m._device = None
            m._backend = None
        for m in sub_models.values():
            m._model = None
            m._device = None
            m._backend = None
        _last_resolved_device = current_device
        _last_resolved_backend = current_backend
        return True
    
    _last_resolved_device = current_device
    _last_resolved_backend = current_backend
    return False


def verify_backend_active() -> dict[str, str]:
    """
    BLOCK FIX-4.1: принудительно грузит ВСЕ модели (если ещё не загружены) и
    возвращает {имя_модели: реальный_backend}. Вызывать один раз при старте
    обработки, чтобы явно предупредить пользователя, если запрошенный backend
    (ONNX/OpenVINO) фактически не используется хотя бы для одной модели —
    вместо тихого отката, о котором сейчас можно узнать только из roadscan.log.
    """
    # Импортируем все модели, которые будут определены ниже
    # (избегаем circular import, поэтому используем locals() после их определения)
    result = {}
    
    # Получаем все глобальные переменные, которые являются _LazyModel
    # Это будет работать, только если вызвать ПОСЛЕ определения всех моделей
    # Для безопасности, соберём список моделей вручную:
    try:
        all_models = {
            "model_side_detect": model_side_detect,
            "rube_modal": rube_modal,
            "model_lane_detect": model_lane_detect,
            "model_lane_segment": model_lane_segment,
        }
        # Добавляем модели из словарей
        for k, v in model_dict.items():
            all_models[f"model_dict[{k}]"] = v
        for k, v in sub_models.items():
            all_models[f"sub_models[{k}]"] = v
        
        for name, m in all_models.items():
            try:
                m._load()  # Принудительно загрузить модель
                result[name] = m._backend or "unknown"
            except Exception as e:
                result[name] = f"ERROR: {e}"
                logger.warning(f"[verify_backend_active] Не удалось загрузить {name}: {e}")
    except Exception as e:
        logger.error(f"[verify_backend_active] Критическая ошибка при проверке backend: {e}")
        result["_error"] = str(e)
    
    return result


def _resolve_backend_name(settings) -> str:
    """
    REFACTOR-1: Единая точка истины для выбора эффективного бэкенда.
    
    Логика была продублирована в _LazyModel._resolve_backend() и
    reload_all_models_if_device_changed(), что создавало риск рассинхронизации.
    Теперь оба места используют эту функцию.
    """
    return "torch" if settings.use_cuda else settings.cpu_inference_backend


class _LazyModel:
    """
    Обёртка для ленивой загрузки YOLO модели.
    Первый вызов загружает модель, последующие используют кеш.
    
    BLOCK M: Расширена для поддержки ONNX Runtime и OpenVINO backends.
    """
    def __init__(self, path_fn, task: str = None, onnx_path_fn=None, openvino_path_fn=None):
        """
        Args:
            path_fn: callable, возвращает путь к .pt файлу
            task: тип задачи ("detect", "classify", "segment") - обязателен для ONNX/OpenVINO
            onnx_path_fn: callable, возвращает путь к .onnx файлу
            openvino_path_fn: callable, возвращает путь к .xml файлу OpenVINO
        """
        self._path_fn = path_fn   # callable -> str
        self._task = task
        self._onnx_path_fn = onnx_path_fn
        self._openvino_path_fn = openvino_path_fn
        self._model   = None
        self._device  = None      # кешируем device при первой загрузке
        self._backend = None      # реально загруженный backend

    def _resolve_backend(self) -> str:
        """Определяет, какой backend использовать на основе настроек."""
        from configs.settings import get_app_settings
        settings = get_app_settings()
        
        # REFACTOR-1: используем общую функцию вместо дублирования логики
        backend = _resolve_backend_name(settings)
        
        # Логируем выбор
        if settings.use_cuda:
            logger.debug("[sign_models] CUDA включена → используется PyTorch backend")
        else:
            logger.debug(f"[sign_models] CUDA выключена → используется {backend} backend")
        
        return backend

    def _load(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO
        
        backend = self._resolve_backend()
        self._device = _resolve_device()
        
        # Пытаемся загрузить с предпочитаемым backend
        if backend == "onnx" and self._onnx_path_fn:
            onnx_path = self._onnx_path_fn()
            if os.path.exists(onnx_path):
                try:
                    # BLOCK M: Для ONNX явно указываем CPU режим
                    # Загружаем модель (Ultralytics автоматически определит backend по расширению)
                    self._model = YOLO(onnx_path, task=self._task)
                    
                    # Принудительно устанавливаем CPU device для predictor
                    # (не для самой модели, т.к. device - read-only property)
                    import torch
                    if hasattr(self._model, 'predictor') and self._model.predictor:
                        self._model.predictor.device = torch.device("cpu")
                    
                    self._backend = "onnx"
                    logger.info(f"[sign_models] Загружена ONNX-модель: {os.path.basename(onnx_path)} (CPU mode)")
                except Exception as e:
                    logger.warning(
                        f"[sign_models] Ошибка загрузки ONNX {onnx_path}: {e}. "
                        f"Откат на PyTorch."
                    )
                    self._model = None
            else:
                logger.warning(
                    f"[sign_models] ONNX-модель не найдена: {onnx_path}. "
                    f"Запустите scripts/export_models_onnx.py. Откат на PyTorch."
                )
        
        elif backend == "openvino" and self._openvino_path_fn:
            ov_path = self._openvino_path_fn()
            if os.path.exists(ov_path):
                try:
                    self._model = YOLO(ov_path, task=self._task)
                    self._backend = "openvino"
                    logger.info(f"[sign_models] Загружена OpenVINO-модель: {os.path.basename(ov_path)}")
                except Exception as e:
                    logger.warning(
                        f"[sign_models] Ошибка загрузки OpenVINO {ov_path}: {e}. "
                        f"Откат на PyTorch."
                    )
                    self._model = None
            else:
                logger.warning(
                    f"[sign_models] OpenVINO-модель не найдена: {ov_path}. "
                    f"Откат на PyTorch."
                )
        
        # Если не загрузили через ONNX/OpenVINO, используем PyTorch
        if self._model is None:
            pt_path = self._path_fn()
            self._model = YOLO(pt_path)
            # .to() валиден только для torch-backend
            try:
                self._model.to(self._device)
                logger.info(
                    f"[sign_models] Загружена PyTorch-модель: {os.path.basename(pt_path)} "
                    f"на device={self._device}"
                )
            except Exception as e:
                # Некоторые версии ultralytics могут не поддерживать .to() для всех backend
                logger.debug(f"[sign_models] .to({self._device}) не применён: {e}")
                logger.info(f"[sign_models] Загружена PyTorch-модель: {os.path.basename(pt_path)}")
            self._backend = "torch"

        return self._model

    def _predict_kwargs_with_cpu_pin(self, kwargs: dict) -> dict:
        """
        BLOCK M-FIX (BUG-1/BUG-6): принудительно указывает device='cpu' для
        ONNX/OpenVINO backend, если вызывающий код не указал device явно.

        Без этого шага Ultralytics AutoBackend может попытаться создать сессию
        с CUDAExecutionProvider даже когда пользователь явно выбрал CPU-бэкенд —
        именно этот класс ошибок был описан в BACKEND_SELECTION_FIX.md
        ("Error when binding input... CUDA -> CPU").
        """
        if self._backend in ("onnx", "openvino") and 'device' not in kwargs:
            kwargs['device'] = 'cpu'
            logger.debug(
                f"[sign_models] {self._backend} inference: явно установлен device=cpu"
            )
        return kwargs

    def _reassert_cpu_predictor(self, model) -> None:
        """Дополнительная защита: устанавливаем CPU device для predictor после создания."""
        if self._backend in ("onnx", "openvino") and hasattr(model, 'predictor') and model.predictor:
            import torch
            try:
                model.predictor.device = torch.device("cpu")
            except Exception:
                pass

    def predict(self, *args, **kwargs):
        model = self._load()
        kwargs = self._predict_kwargs_with_cpu_pin(kwargs)
        result = model.predict(*args, **kwargs)
        self._reassert_cpu_predictor(model)
        return result

    def __call__(self, *args, **kwargs):
        # ВАЖНО (BUG-1 fix): раньше здесь был прямой self._load()(*args, **kwargs),
        # который полностью обходил device='cpu' инъекцию из predict(). Основной
        # путь классификации знаков (core/detector.py: _run_cnn_model, _run_cnn_batch,
        # включая суб-модели треугольников) вызывает модели именно через __call__,
        # а не через .predict() — поэтому этот баг фактически сводил на нет весь
        # CPU-backend фикс для реальной классификации. YOLO.__call__ у Ultralytics —
        # это alias на predict(), так что делегирование здесь безопасно и не меняет
        # публичный контракт.
        return self.predict(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._load(), name)


def _p(rel: str):
    """Фабрика callable для resource_path."""
    def _get():
        from app.utils import resource_path
        return resource_path(rel)
    return _get


def _p_onnx(rel: str):
    """Фабрика callable для ONNX-пути (замена .pt на .onnx)."""
    def _get():
        from app.utils import resource_path
        base = os.path.splitext(rel)[0]
        return resource_path(f"{base}.onnx")
    return _get


def _p_openvino(rel: str):
    """
    Фабрика callable для OpenVINO-пути.
    Ultralytics принимает путь к ДИРЕКТОРИИ *_openvino_model, а не к .xml файлу внутри.
    """
    def _get():
        from app.utils import resource_path
        base = os.path.splitext(rel)[0]
        # Возвращаем путь к директории, а не к .xml файлу
        ov_dir = f"{base}_openvino_model"
        return resource_path(ov_dir)
    return _get


# Главная модель детекции знаков
model_side_detect = _LazyModel(
    _p("CNN_side/best.pt"),
    task="detect",
    onnx_path_fn=_p_onnx("CNN_side/best.pt"),
    openvino_path_fn=_p_openvino("CNN_side/best.pt")
)

# Грубая фильтрация
rube_modal = _LazyModel(
    _p("small_models/rude.pt"),
    task="classify",
    onnx_path_fn=_p_onnx("small_models/rude.pt"),
    openvino_path_fn=_p_openvino("small_models/rude.pt")
)

# Модели по категориям знаков
model_dict = {
    "blue": _LazyModel(
        _p("small_models/blue.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/blue.pt"),
        openvino_path_fn=_p_openvino("small_models/blue.pt")
    ),
    "treugolnik": _LazyModel(
        _p("small_models/treugolnik.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/treugolnik.pt"),
        openvino_path_fn=_p_openvino("small_models/treugolnik.pt")
    ),
    "krug": _LazyModel(
        _p("small_models/krug.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/krug.pt"),
        openvino_path_fn=_p_openvino("small_models/krug.pt")
    ),
    "red": _LazyModel(
        _p("small_models/red.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/red.pt"),
        openvino_path_fn=_p_openvino("small_models/red.pt")
    ),
    "servises": _LazyModel(
        _p("small_models/servises.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/servises.pt"),
        openvino_path_fn=_p_openvino("small_models/servises.pt")
    ),
    "tablichkaL": _LazyModel(
        _p("small_models/tabl l.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/tabl l.pt"),
        openvino_path_fn=_p_openvino("small_models/tabl l.pt")
    ),
    "tablichka__": _LazyModel(
        _p("small_models/tabl.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/tabl.pt"),
        openvino_path_fn=_p_openvino("small_models/tabl.pt")
    ),
    "tupic": _LazyModel(
        _p("small_models/tupic.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/tupic.pt"),
        openvino_path_fn=_p_openvino("small_models/tupic.pt")
    ),
    "5.38": _LazyModel(
        _p("small_models/5.38.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/5.38.pt"),
        openvino_path_fn=_p_openvino("small_models/5.38.pt")
    ),
    "5.9.1-5.14": _LazyModel(
        _p("small_models/5.9.1-5.14.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/5.9.1-5.14.pt"),
        openvino_path_fn=_p_openvino("small_models/5.9.1-5.14.pt")
    ),
    "5.5-5.6": _LazyModel(
        _p("small_models/one_side.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/one_side.pt"),
        openvino_path_fn=_p_openvino("small_models/one_side.pt")
    ),
}

# Субмодели для треугольников
sub_models = {
    "danger": _LazyModel(
        _p("small_models/danger.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/danger.pt"),
        openvino_path_fn=_p_openvino("small_models/danger.pt")
    ),
    "pimicanie": _LazyModel(
        _p("small_models/pimicanie.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/pimicanie.pt"),
        openvino_path_fn=_p_openvino("small_models/pimicanie.pt")
    ),
    "suzenie": _LazyModel(
        _p("small_models/suzenie.pt"),
        task="classify",
        onnx_path_fn=_p_onnx("small_models/suzenie.pt"),
        openvino_path_fn=_p_openvino("small_models/suzenie.pt")
    ),
}

# Модели разметки полос
model_lane_detect = _LazyModel(
    _p("lane_guidance_models/arrow_detect.pt"),
    task="detect",
    onnx_path_fn=_p_onnx("lane_guidance_models/arrow_detect.pt"),
    openvino_path_fn=_p_openvino("lane_guidance_models/arrow_detect.pt")
)
model_lane_segment = _LazyModel(
    _p("lane_guidance_models/arrow_segment.pt"),
    task="segment",
    onnx_path_fn=_p_onnx("lane_guidance_models/arrow_segment.pt"),
    openvino_path_fn=_p_openvino("lane_guidance_models/arrow_segment.pt")
)

# BLOCK 2.3.4: Удалены неиспользуемые классы _LazyKeras, _LazyJoblib
# и закомментированные модели sign_classificator (Keras-модель позиции знака).
# Эти модели нигде не вызывались (проверено grep по всему проекту).
# Bearing-based геометрия (BLOCK H) заменила эвристику полностью.