"""
configs/sign_config.py
Обратная совместимость — реэкспортирует всё из новых модулей.
Старые файлы (GPXHandler, Turn, CoordinateCalculation, Server)
продолжают работать без изменений.

НЕ добавляйте сюда новый код — используйте sign_data.py / sign_models.py.
"""

# ── Данные (без побочных эффектов) ────────────────────────────────
from configs.sign_data import (
    NAME_SIGNS_CNN         as name_signs_cnn,
    NAME_SUB_SIGNS_CNN     as name_sub_signs_cnn,
    TYPE_SIGNS_YOLO        as type_signs_yolo,
    SIGNS_WITH_TEXT        as signs_with_various_text,
    TYPE_SIGNS_WITH_TEXT   as type_signs_with_text,
    NAME_SIGNS_CITY        as name_signs_city,
    TYPE_SIGNS_CITY        as type_signs_city,
    NAMES_SIGNS_FOR_SIDE   as names_signs_for_side,
    NAMES_SIGNS_FOR_YOLO   as names_signs_for_YOLO,
    PLATE_SIGNS_WITH_TEXT  as plate_for_signatures_with_text,
    PLATE_SIGNS_WITHOUT_TEXT as plate_for_signatures_without_text,
    PLATE_SIGNS            as plate_for_signatures,
    CODES_SIGNS            as codes_signs,
    NAMES_SIGNS_BY_TYPE    as names_signs_by_type,
)

# ── Модели (грузятся один раз) ────────────────────────────────────
from configs.sign_models import (
    sign_classificator        as sign_classificator_model,
    sign_classificator_scaler,
    sign_classificator_le,
    model_lane_detect,
    model_lane_segment,
    rube_modal,
    model_dict,
    sub_models,
)

# warning_signs оставляем для совместимости
warning_signs: dict = {}