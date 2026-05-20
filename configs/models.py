"""
configs/sign_models.py
Загрузка YOLO/Keras моделей — один раз при старте приложения.
Все модели — синглтоны, импортируются из любого места.
"""
from ultralytics import YOLO
from keras.models import load_model
import joblib
import warnings

from utils import resource_path

warnings.filterwarnings("ignore", category=UserWarning, module="sklearn")

# ── Классификатор (Keras) ──────────────────────────────────────────
sign_classificator      = load_model(resource_path("small_models/SignClassificator_v2.keras"))
sign_classificator_scaler = joblib.load(resource_path("small_models/SignClassificator_scaler.pkl"))
sign_classificator_le   = joblib.load(resource_path("small_models/SignClassificator_le.pkl"))

# ── Главная модель детекции знаков ────────────────────────────────
model_side_detect = YOLO(resource_path("CNN_side/best.pt"))

# ── Грубая фильтрация (rude) ──────────────────────────────────────
rube_modal = YOLO(resource_path("small_models/rude.pt"))

# ── Модели по категориям знаков ───────────────────────────────────
model_dict: dict[str, YOLO] = {
    "blue":         YOLO(resource_path("small_models/blue.pt")),
    "treugolnik":   YOLO(resource_path("small_models/treugolnik.pt")),
    "krug":         YOLO(resource_path("small_models/krug.pt")),
    "red":          YOLO(resource_path("small_models/red.pt")),
    "servises":     YOLO(resource_path("small_models/servises.pt")),
    "tablichkaL":   YOLO(resource_path("small_models/tabl l.pt")),
    "tablichka__":  YOLO(resource_path("small_models/tabl.pt")),
    "tupic":        YOLO(resource_path("small_models/tupic.pt")),
    "5.38":         YOLO(resource_path("small_models/5.38.pt")),
    "5.9.1-5.14":   YOLO(resource_path("small_models/5.9.1-5.14.pt")),
    "5.5-5.6":      YOLO(resource_path("small_models/one_side.pt")),
}

# ── Субмодели для треугольников ───────────────────────────────────
sub_models: dict[str, YOLO] = {
    "danger":    YOLO(resource_path(r"small_models\danger.pt")),
    "pimicanie": YOLO(resource_path(r"small_models\pimicanie.pt")),
    "suzenie":   YOLO(resource_path(r"small_models\suzenie.pt")),
}

# ── Модели разметки полос ─────────────────────────────────────────
model_lane_detect  = YOLO(resource_path("lane_guidance_models/arrow_detect.pt"))
model_lane_segment = YOLO(resource_path("lane_guidance_models/arrow_segment.pt"))