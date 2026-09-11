"""
configs/settings.py
Централизованный объект настроек приложения.
Сохраняется/загружается через QSettings между запусками.
"""
import os
from dataclasses import dataclass, field, asdict
from typing import Literal
from PyQt6.QtCore import QSettings


@dataclass
class AppSettings:
    """Настройки приложения с персистентностью."""
    
    # ── Обработка кадров ──────────────────────────────────────────
    frame_step_mode: Literal["auto", "manual"] = "auto"
    frame_step_manual: int = 5  # Используется только если mode == "manual"
    
    # ── Пороги уверенности (confidence) ───────────────────────────
    # ЗАДАЧА 5 (P1): Обновлены дефолты на рекомендуемые значения
    conf_side: float = 0.55   # YOLO side-detect (грубая детекция знака) [рекомендовано 0.4-0.7]
    conf_rube: float = 0.70   # YOLO rube классификация (грубая категория)
    conf_cnn: float = 0.60    # CNN fine классификация (точный тип)
    iou_threshold: float = 0.15  # IoU для NMS в YOLO [рекомендовано 0.1-0.2]
    
    # ── Дедупликация знаков ───────────────────────────────────────
    # ЗАДАЧА 5 (P1): Обновлены дефолты на рекомендуемые значения
    dedup_radius_track_m: float = 10.0   # SignHandler.NEARBY_SIGN_RADIUS_M [рекомендовано 8-15]
    dedup_radius_final_m: float = 20.0  # FinalHandler.DEDUP_RADIUS_M
    dedup_azimuth_deg: float = 40.0     # FinalHandler.DEDUP_AZIMUTH_DEG [рекомендовано 35-45]
    
    # ── Определение стороны знака и полосы (TASK 1) ───────────────
    # Ширина дороги и полос учитывается при группировке знаков
    default_lane_width_m: float = 3.5   # Дефолтная ширина полосы (м)
    default_lanes_count: int = 2        # Дефолтное число полос если OSM не содержит
    max_offset_multiplier: float = 1.5  # Макс офсет = road_width * multiplier
    
    # Пороги для определения дублей vs разных знаков
    duplicate_merge_distance_m: float = 5.0   # Два знака ближе этого расстояния = дубли
    duplicate_azimuth_diff_deg: float = 15.0  # Разница в азимуте для дубликатов
    duplicate_time_overlap_frames: int = 10   # Перекрытие по кадрам для merge
    
    # ── Геометрия перекрёстков (BLOCK H) ──────────────────────────
    camera_hfov_deg: float = 120.0      # Горизонтальный FOV камеры/видеорегистратора
                                        # (GoPro Hero ~120°, обычные dashcam ~90-110°)
    turn_ray_max_distance_m: float = 40.0  # Максимальная дистанция луча при raycast
    turn_use_bearing_geometry: bool = True  # Использовать bearing-based geometry (vs эвристику)
    # BLOCK N.3: turn_detection_radius_m удалён как неиспользуемый (дублирует turn_ray_max_distance_m)
    
    # ── Многопоточность ───────────────────────────────────────────
    # Task E: DEPRECATED - UI-выбор убран, всегда используется single_thread.
    # Поля оставлены только для совместимости десериализации старых настроек.
    processing_mode: Literal["single_thread", "pipeline", "process_pool"] = "single_thread"
    process_pool_workers: int = 0  # DEPRECATED (Task E)
    ocr_use_process_pool: bool = True  # DEPRECATED (Task E)
    ocr_pool_workers: int = 1  # DEPRECATED (Task E)
    
    # ── Вычисления (CPU/GPU) ──────────────────────────────────────
    use_cuda: bool = True  # Использовать CUDA для моделей YOLO и OCR, если доступна
    
    # ── CPU-инференс (BLOCK M) ─────────────────────────────────────
    cpu_inference_backend: Literal["torch", "onnx", "openvino"] = "torch"
    # Бэкенд для CPU-инференса. Игнорируется при use_cuda=True.
    # "torch" - PyTorch (по умолчанию, совместимость)
    # "onnx" - ONNX Runtime (требует экспорта моделей)
    # "openvino" - OpenVINO (требует экспорта моделей)
    
    # ── CPU-инференс: потоки ONNX/OpenVINO (BLOCK CPU-5) ──────────
    cpu_onnx_intra_threads: int = 0     # 0 = авто (cpu_count-1, либо cpu_count//workers в process_pool)
    cpu_onnx_inter_threads: int = 1
    cpu_openvino_threads: int = 0       # 0 = авто, та же логика
    
    # ── Пороги для lane detection (BLOCK P.1) ─────────────────────
    lane_conf_detect: float = 0.65   # Порог уверенности для model_lane_detect
    lane_conf_segment: float = 0.65  # Порог уверенности для model_lane_segment
    
    # ── CPU-оптимизация (BLOCK CPU) ───────────────────────────────
    # ЗАДАЧА 5 (P1): Обновлены дефолты на рекомендуемые значения
    preview_fps_limit: float = 10.0  # Максимальная частота обновления превью UI (кадр/сек) [рекомендовано 8-12]
    ocr_throttle_interval_frames: int = 8   # Минимальный интервал между OCR-вызовами для одного знака
    ocr_max_calls_per_sign: int = 6         # Максимальное число OCR-вызовов для одного знака
    
    # ── Отладка и логирование ─────────────────────────────────────
    verbose_log: bool = False
    save_error_frames: bool = False
    error_frames_dir: str = "./errorData"
    
    # ── Интерфейс ─────────────────────────────────────────────────
    theme: Literal["dark", "light"] = "dark"
    
    # ── UI режим страницы настроек (BLOCK SETTINGS-UX-1) ──────────
    settings_ui_mode: Literal["simple", "advanced"] = "simple"
    
    # ── Карта (подложка) ──────────────────────────────────────────
    map_tile_url: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
    map_tile_attribution: str = "© OpenStreetMap"
    map_tile_max_zoom: int = 19
    
    # ── Обновления ────────────────────────────────────────────────
    auto_check_updates: bool = True
    update_channel: Literal["stable", "beta"] = "stable"
    last_update_check_ts: float = 0.0  # timestamp последней проверки
    
    @classmethod
    def load(cls) -> "AppSettings":
        """Загрузить настройки из QSettings."""
        try:
            settings = QSettings("Signer", "RoadScanner")
            
            # Читаем каждое поле, используя значения по умолчанию
            defaults = cls()
            data = {}
            
            for field_name, field_obj in cls.__dataclass_fields__.items():
                try:
                    default_value = getattr(defaults, field_name)
                    
                    # QSettings возвращает строки для enum, конвертируем обратно
                    value = settings.value(field_name, default_value)
                    
                    # Определяем тип поля
                    field_type = field_obj.type
                    
                    # Приводим к правильному типу
                    # Проверяем bool
                    if field_type is bool:
                        if isinstance(value, str):
                            value = value.lower() in ('true', '1', 'yes')
                        elif not isinstance(value, bool):
                            value = bool(value) if value is not None else default_value
                    # Проверяем int
                    elif field_type is int:
                        if not isinstance(value, int):
                            value = int(value) if value is not None else default_value
                    # Проверяем float  
                    elif field_type is float:
                        if not isinstance(value, float):
                            value = float(value) if value is not None else default_value
                    # Для остальных типов (str, Literal) оставляем как есть
                    
                    data[field_name] = value
                    
                except Exception as e:
                    # Если любая ошибка для конкретного поля - используем default
                    print(f"[AppSettings] Ошибка поля {field_name}: {e}, используем default")
                    data[field_name] = getattr(defaults, field_name)
            
            return cls(**data)
            
        except Exception as e:
            print(f"[AppSettings] Критическая ошибка загрузки: {e}, используем defaults")
            import traceback
            traceback.print_exc()
            return cls()  # Возвращаем полностью дефолтные настройки
    
    def save(self) -> None:
        """Сохранить настройки в QSettings."""
        settings = QSettings("Signer", "RoadScanner")
        
        for field_name, value in asdict(self).items():
            settings.setValue(field_name, value)
        
        settings.sync()
    
    def reset_to_defaults(self) -> None:
        """Сбросить все настройки к значениям по умолчанию."""
        defaults = AppSettings()
        for field_name in self.__dataclass_fields__:
            setattr(self, field_name, getattr(defaults, field_name))
    
    def to_dict(self) -> dict:
        """Экспортировать в словарь для JSON."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        """Импортировать из словаря (JSON)."""
        # Фильтруем только известные поля
        valid_fields = {k: v for k, v in data.items() if k in cls.__dataclass_fields__}
        return cls(**valid_fields)


# Глобальный экземпляр настроек
_app_settings: AppSettings | None = None


def get_app_settings() -> AppSettings:
    """Получить глобальный экземпляр настроек (singleton)."""
    global _app_settings
    if _app_settings is None:
        _app_settings = AppSettings.load()
    return _app_settings


def reload_app_settings() -> AppSettings:
    """Принудительно перезагрузить настройки из QSettings."""
    global _app_settings
    _app_settings = AppSettings.load()
    return _app_settings
