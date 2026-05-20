"""
core/sign.py
Трекируемый знак — накапливает данные по всем кадрам где был виден.
Рефакторинг Sign.py: типы, slots, методы разбиты по ответственности.
"""
from __future__ import annotations
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from core.converter import Converter
from core.frame import DetectedSign


@dataclass
class TrackedSign:
    """
    Знак который детектор видел в нескольких кадрах подряд.
    Накапливает историю позиций, CNN-результаты, координаты.
    """
    # ── Пиксельные координаты (история по кадрам) ─────────────────
    pixel_x:  list[int]   = field(default_factory=list)
    pixel_y:  list[int]   = field(default_factory=list)
    widths:   list[int]   = field(default_factory=list)
    heights:  list[int]   = field(default_factory=list)

    # ── Координаты автомобиля (EPSG:32635) ────────────────────────
    car_x:    list[float] = field(default_factory=list)
    car_y:    list[float] = field(default_factory=list)

    # ── Номера кадров ─────────────────────────────────────────────
    frame_numbers:    list[int] = field(default_factory=list)  # внутри видео
    abs_frame_numbers:list[int] = field(default_factory=list)  # глобальные

    # ── Классификация ─────────────────────────────────────────────
    yolo_results: list[str] = field(default_factory=list)  # классы YOLO
    cnn_results:  list[str] = field(default_factory=list)  # классы CNN
    side_results: list[bool]= field(default_factory=list)  # боковой?
    text_results: list[str] = field(default_factory=list)  # текст на знаке

    # ── Финальные атрибуты ────────────────────────────────────────
    azimuth:        float = 0.0
    is_left:        bool  = False
    is_turn:        bool  = False
    turn_direction: str   = "straight"
    number:         int   = 0        # позиция на повороте (0–8)
    number_sign:    int   = 0        # глобальный номер кадра фиксации
    distance:       Optional[float] = None

    # ── GPS координаты знака (заполняются после snap к OSM) ───────
    latitude:  Optional[float] = None
    longitude: Optional[float] = None

    # ── Уверенность (заполняется в FinalHandler после snap) ───────
    conf_cnn:      float = 0.0   # cnn_count / observation_count  [0..1]
    conf_placement:float = 0.0   # уверенность постановки на карту [0..1]
    conf_total:    float = 0.0   # итоговая = 0.5*cnn + 0.5*placement
    snap_distance: float = -1.0  # расстояние до ближайшего ребра дороги (м)
    azimuth_delta: float = 0.0   # расхождение GPX-курса и OSM-азимута (°)

    _converter: Converter = field(default_factory=Converter, repr=False)

    # ── Добавление данных из кадра ────────────────────────────────

    def append(self, det: DetectedSign) -> None:
        """Добавить одно обнаружение знака."""
        self.pixel_x.append(det.x)
        self.pixel_y.append(det.y)
        self.widths.append(det.w)
        self.heights.append(det.h)
        self.yolo_results.append(det.name_sign)
        self.cnn_results.append(det.number_sign)
        self.side_results.append(det.is_side)
        self.frame_numbers.append(det.frame_number)
        self.abs_frame_numbers.append(det.absolute_frame_number)
        if det.text_on_sign:
            self.text_results.append(det.text_on_sign)
        self._append_car_coord(det.latitude, det.longitude)

    def _append_car_coord(self, x: float, y: float) -> None:
        """Добавляет координату только если она изменилась."""
        if not self.car_x or x != self.car_x[-1]:
            self.car_x.append(x)
            self.car_y.append(y)

    def merge(self, other: "TrackedSign") -> None:
        """Объединить два знака в один (concat_two_object)."""
        self.pixel_x          += other.pixel_x
        self.pixel_y          += other.pixel_y
        self.widths           += other.widths
        self.heights          += other.heights
        self.yolo_results     += other.yolo_results
        self.cnn_results      += other.cnn_results
        self.side_results     += other.side_results
        self.text_results     += other.text_results
        self.frame_numbers    += other.frame_numbers
        self.abs_frame_numbers+= other.abs_frame_numbers
        self.car_x            += other.car_x
        self.car_y            += other.car_y

    # ── Статистика ────────────────────────────────────────────────

    def most_common(self, results: list[str]) -> tuple[str, int]:
        """Самый частый элемент списка. Возвращает (name, count)."""
        if not results:
            return ("", 0)
        name, count = Counter(results).most_common(1)[0]
        return (name, count)

    @property
    def best_yolo(self) -> str:
        return self.most_common(self.yolo_results)[0]

    @property
    def best_cnn(self) -> str:
        return self.most_common(self.cnn_results)[0]

    @property
    def best_side(self) -> bool:
        """True если знак чаще появлялся как боковой."""
        if not self.side_results:
            return False
        return sum(self.side_results) > len(self.side_results) / 2

    @property
    def cnn_count(self) -> int:
        """Сколько раз лучший CNN-класс встречается."""
        return self.most_common(self.cnn_results)[1]

    @property
    def observation_count(self) -> int:
        return len(self.frame_numbers)

    # ── Геометрия ─────────────────────────────────────────────────

    def pixel_vector_to(self, det: DetectedSign) -> float:
        """Евклидово расстояние от последней позиции до нового знака."""
        if not self.pixel_x:
            return 0.0
        dx = det.x - self.pixel_x[-1]
        dy = det.y - self.pixel_y[-1]
        return round((dx**2 + dy**2) ** 0.5, 1)

    def replace_car_coords_from_turn(self, turn_coords: list[tuple]) -> None:
        """Заменить координаты автомобиля точками поворота."""
        self.car_x.clear()
        self.car_y.clear()
        for lat, lon in turn_coords:
            x, y = self._converter.coordinateConverter(lat, lon, "epsg:4326", "epsg:32635")
            self.car_x.append(x)
            self.car_y.append(y)

    # ── Городские знаки ───────────────────────────────────────────

    def best_city_name(self) -> str:
        """
        Из text_results (список матчей difflib) выбирает
        наиболее вероятное название населённого пункта.
        """
        scores: dict[str, dict] = {}
        for item in self.text_results:
            if not isinstance(item, list):
                continue
            for accuracy, name in item:
                if name in scores:
                    scores[name]["accuracy"] += accuracy
                    scores[name]["count"]    += 1
                else:
                    scores[name] = {"accuracy": accuracy, "count": 1}
        if not scores:
            return ""
        return max(scores, key=lambda n: scores[n]["accuracy"])

    # ── Уверенность ──────────────────────────────────────────────

    def calc_confidence(
        self,
        snap_dist_m: float = -1.0,
        osm_azimuth: Optional[float] = None,
        gpx_azimuth: Optional[float] = None,
    ) -> None:
        """
        Вычисляет все метрики уверенности и записывает в поля.
        Вызывается из FinalHandler после OSM snap.

        conf_cnn:       cnn_count / observation_count
        conf_placement: взвешенная из 4 субметрик
        conf_total:     0.5 * conf_cnn + 0.5 * conf_placement
        """
        # ── 1. CNN уверенность ────────────────────────────────────
        self.conf_cnn = (
            self.cnn_count / self.observation_count
            if self.observation_count > 0 else 0.0
        )

        # ── 2. Уверенность постановки ─────────────────────────────

        # 2a. Стабильность трека (разброс pixel_x по кадрам)
        #     Чем меньше std, тем стабильнее знак → выше уверенность
        track_score = self._calc_track_stability()

        # 2b. Длина трека (наблюдений)
        #     Нормируем: 4 = 0.0, 20+ = 1.0
        obs = self.observation_count
        length_score = min(1.0, max(0.0, (obs - 4) / 16))

        # 2c. OSM snap качество
        #     snap_dist_m = -1 → snap не выполнялся (нейтральный балл 0.5)
        #     0–5м  → 1.0,  5–15м → linear,  >30м → 0.0
        if snap_dist_m < 0:
            snap_score = 0.5
        elif snap_dist_m <= 5:
            snap_score = 1.0
        elif snap_dist_m <= 30:
            snap_score = 1.0 - (snap_dist_m - 5) / 25
        else:
            snap_score = 0.0
        self.snap_distance = snap_dist_m

        # 2d. Расхождение азимутов GPX vs OSM
        #     0° → 1.0,  45°+ → 0.0
        if osm_azimuth is not None and gpx_azimuth is not None:
            delta = abs(osm_azimuth - gpx_azimuth) % 360
            if delta > 180:
                delta = 360 - delta
            self.azimuth_delta = delta
            az_score = max(0.0, 1.0 - delta / 45)
        else:
            az_score = 0.5  # нет данных — нейтральный балл

        # Взвешенная постановка
        self.conf_placement = (
            0.30 * track_score   +
            0.25 * length_score  +
            0.25 * snap_score    +
            0.20 * az_score
        )

        # ── 3. Итоговая ───────────────────────────────────────────
        self.conf_total = 0.50 * self.conf_cnn + 0.50 * self.conf_placement

    def _calc_track_stability(self) -> float:
        """
        Стабильность трека по pixel_x.
        std < 5px → 1.0,  std > 150px → 0.0.
        """
        if len(self.pixel_x) < 2:
            return 0.5
        mean = sum(self.pixel_x) / len(self.pixel_x)
        variance = sum((x - mean) ** 2 for x in self.pixel_x) / len(self.pixel_x)
        std = variance ** 0.5
        return max(0.0, 1.0 - std / 150)

    @property
    def confidence_label(self) -> str:
        """Текстовый уровень уверенности для UI."""
        t = self.conf_total
        if t >= 0.75:
            return "высокая"
        if t >= 0.50:
            return "средняя"
        if t >= 0.30:
            return "низкая"
        return "очень низкая"

    # ── Debug ─────────────────────────────────────────────────────

    def __repr__(self) -> str:
        x, y = ("?", "?")
        try:
            x, y = self._converter.coordinateConverter(
                self.car_x[-1], self.car_y[-1], "epsg:32635", "epsg:4326"
            )
            x, y = round(x, 5), round(y, 5)
        except Exception:
            pass
        return (
            f"TrackedSign(type={self.best_cnn!r}, "
            f"obs={self.observation_count}, "
            f"left={self.is_left}, "
            f"frames={self.frame_numbers[:3]}…, "
            f"coord=({x},{y}), az={self.azimuth:.1f})"
        )