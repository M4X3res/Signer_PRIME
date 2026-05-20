"""
configs/sign_models.py
Ленивая загрузка YOLO/Keras моделей.

На Windows загрузка YOLO в главном потоке вместе с PyQt6
вызывает краш (конфликт DLL). Поэтому используем lazy loading:
модели создаются только при первом обращении, уже внутри QThread.
"""
from __future__ import annotations
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")


class _LazyModel:
    """
    Обёртка для ленивой загрузки YOLO модели.
    Первый вызов загружает модель, последующие используют кеш.
    """
    def __init__(self, path_fn):
        self._path_fn = path_fn   # callable -> str
        self._model   = None

    def _load(self):
        if self._model is None:
            from ultralytics import YOLO
            self._model = YOLO(self._path_fn())
        return self._model

    def __call__(self, *args, **kwargs):
        return self._load()(*args, **kwargs)

    def predict(self, *args, **kwargs):
        return self._load().predict(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._load(), name)


def _p(rel: str):
    """Фабрика callable для resource_path."""
    def _get():
        from utils import resource_path
        return resource_path(rel)
    return _get


# Главная модель детекции знаков
model_side_detect = _LazyModel(_p("CNN_side/best.pt"))

# Грубая фильтрация
rube_modal = _LazyModel(_p("small_models/rude.pt"))

# Модели по категориям знаков
model_dict = {
    "blue":        _LazyModel(_p("small_models/blue.pt")),
    "treugolnik":  _LazyModel(_p("small_models/treugolnik.pt")),
    "krug":        _LazyModel(_p("small_models/krug.pt")),
    "red":         _LazyModel(_p("small_models/red.pt")),
    "servises":    _LazyModel(_p("small_models/servises.pt")),
    "tablichkaL":  _LazyModel(_p("small_models/tabl l.pt")),
    "tablichka__": _LazyModel(_p("small_models/tabl.pt")),
    "tupic":       _LazyModel(_p("small_models/tupic.pt")),
    "5.38":        _LazyModel(_p("small_models/5.38.pt")),
    "5.9.1-5.14":  _LazyModel(_p("small_models/5.9.1-5.14.pt")),
    "5.5-5.6":     _LazyModel(_p("small_models/one_side.pt")),
}

# Субмодели для треугольников
sub_models = {
    "danger":    _LazyModel(_p("small_models/danger.pt")),
    "pimicanie": _LazyModel(_p("small_models/pimicanie.pt")),
    "suzenie":   _LazyModel(_p("small_models/suzenie.pt")),
}

# Модели разметки полос
model_lane_detect  = _LazyModel(_p("lane_guidance_models/arrow_detect.pt"))
model_lane_segment = _LazyModel(_p("lane_guidance_models/arrow_segment.pt"))


class _LazyKeras:
    def __init__(self, path_fn):
        self._path_fn = path_fn
        self._model   = None

    def _load(self):
        if self._model is None:
            from keras.models import load_model
            self._model = load_model(self._path_fn())
        return self._model

    def predict(self, *args, **kwargs):
        return self._load().predict(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        return self._load()(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._load(), name)


class _LazyJoblib:
    def __init__(self, path_fn):
        self._path_fn = path_fn
        self._obj     = None

    def _load(self):
        if self._obj is None:
            import joblib
            self._obj = joblib.load(self._path_fn())
        return self._obj

    def transform(self, *args, **kwargs):
        return self._load().transform(*args, **kwargs)

    def inverse_transform(self, *args, **kwargs):
        return self._load().inverse_transform(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._load(), name)


sign_classificator        = _LazyKeras(_p("small_models/SignClassificator_v2.keras"))
sign_classificator_scaler = _LazyJoblib(_p("small_models/SignClassificator_scaler.pkl"))
sign_classificator_le     = _LazyJoblib(_p("small_models/SignClassificator_le.pkl"))