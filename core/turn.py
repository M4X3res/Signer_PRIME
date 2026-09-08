"""
core/turn.py
Turn — хранит данные об одном повороте: координаты, азимуты,
знаки, видимые в момент поворота.

Рефакторинг оригинального Turn.py:
  1. Заменены устаревшие импорты (GPXHandler → core.gpx_handler,
     Converter → core.converter), убраны pandas/csv
  2. Имена полей TrackedSign приведены к актуальным
     (pixel_coordinates_x → pixel_x, car_coordinates_x → car_x,
      sign.h → sign.heights, sign.w → sign.widths,
      turn_directions → turn_direction)
  3. Ленивая инициализация GPXHandler/Converter внутри методов
     (безопасно для Qt-потоков)
  4. Сохранена вся бизнес-логика оригинала без изменений
"""
from __future__ import annotations

import copy
import math
from typing import TYPE_CHECKING, Optional

import numpy as np

from configs import config

if TYPE_CHECKING:
    from core.sign import TrackedSign


class Turn:
    def __init__(self):
        self.signs:           list          = []
        self.signs_dict:      dict          = {}
        self.coordinates:     list          = []   # [(lat, lon), ...]
        self.azimuths:        list[float]   = []
        self.was_there_turn:  bool          = False
        self.turn_direction:  str           = "straight"   # ← было turn_directions
        self.turn_distance:   int           = 0
        self.frames:          list[int]     = []
        self.segment_length:  float         = 0
        self.last_index_of_gps: int         = 0
        
        # Мемоизированные сервисы (BLOCK 1: Performance fix)
        self._gpx_handler:       Optional[object] = None
        self._converter_instance: Optional[object] = None

    # ── Ленивые аксессоры к сервисам (мемоизированные) ────────────

    def _gpx(self):
        """GPXHandler — создаётся один раз за время жизни Turn (внутри QThread)."""
        if self._gpx_handler is None:
            from core.gpx_handler import GPXHandler
            self._gpx_handler = GPXHandler()
        return self._gpx_handler

    def _converter(self):
        """Converter — создаётся один раз за время жизни Turn."""
        if self._converter_instance is None:
            from core.converter import Converter
            self._converter_instance = Converter()
        return self._converter_instance

    # ── Сброс ─────────────────────────────────────────────────────

    def clean(self) -> None:
        self.signs            = []
        self.signs_dict       = {}
        self.coordinates      = []
        self.azimuths         = []
        self.was_there_turn   = False
        self.turn_direction   = "straight"
        self.turn_distance    = 0
        self.frames           = []
        self.segment_length   = 0
        self.last_index_of_gps = 0

    # ── Накопление данных ─────────────────────────────────────────

    def append_azimuths(self, item: float) -> None:
        gpx = self._gpx()
        if not self.azimuths:
            self.azimuths.append(gpx.get_azimuth(config.INDEX_OF_GPS))
            self.azimuths.append(item)
        else:
            if item != self.azimuths[-1]:
                self.azimuths.append(item)

    def append_coordinates(self, item: tuple) -> None:
        gpx = self._gpx()
        if not self.coordinates:
            self.coordinates.append(gpx.get_current_coordinate(config.INDEX_OF_GPS))
            self.coordinates.append(item)
        else:
            if item != self.coordinates[-1]:
                self.coordinates.append(item)

    def add_points(self) -> None:
        """
        Добавляет 3 GPS-точки начиная с last_index_of_gps + 2.
        Вызывается из SignHandler._handle_turn_end перед финализацией.
        """
        count_points       = 3
        coordinate_offset  = 2
        gpx = self._gpx()
        for index in range(count_points):
            index_of_gpx = self.last_index_of_gps + index + coordinate_offset
            self.append_coordinates(gpx.get_current_coordinate(index_of_gpx))
            self.append_azimuths(gpx.get_azimuth(index_of_gpx))

    # ── Определение поворота ──────────────────────────────────────

    def is_turn(self) -> bool:
        """
        True если машина сейчас в повороте.
        Определяет направление поворота и устанавливает was_there_turn.
        """
        gpx = self._gpx()
        delta = (gpx.get_azimuth(config.INDEX_OF_GPS + 1)
                 - gpx.get_azimuth(config.INDEX_OF_GPS))
        result = 355 > abs(delta) > 10
        if result:
            if abs(delta) > 300:
                self.turn_direction = "right" if delta < 0 else "left"
            else:
                self.turn_direction = "left" if delta < 0 else "right"
            self.was_there_turn = True
        return result

    # ── Расстановка знаков ────────────────────────────────────────

    def set_direction_signs(self) -> None:
        """Проставляет is_turn и turn_direction всем знакам поворота."""
        for sign in self.signs:
            sign.is_turn       = True
            sign.turn_direction = self.turn_direction   # ← было turn_directions

    def handle_turn(self) -> None:
        """Вычисляет позицию (number) каждого знака на повороте."""
        self.segment_length = len(self.frames) / 3
        for sign in self.signs:
            if len(sign.frame_numbers) > 3:
                sign.number = self._handle_sign(sign)

    def _handle_sign(self, sign) -> int:
        max_size   = self._calc_max_size(sign)
        min_size   = self._calc_min_size(sign)
        coeff_fr   = self._calc_coeff_frames(sign, min_size, max_size)

        if self._calc_diff_x(sign) > 1000 and coeff_fr > 150:
            return 7

        if sign.frame_numbers[-1] in self.frames:
            sign.distance = self.frames.index(sign.frame_numbers[-1])
        else:
            sign.distance = -1
            return 2

        if (sign.distance / self.segment_length) >= 2:
            if self.turn_direction == "right":
                if sign.pixel_x[1] - sign.pixel_x[-2] < 0:
                    return 7
            if coeff_fr < 150:
                return 5
            else:
                return 8

        if sign.pixel_x[1] - sign.pixel_x[-2] > 0:
            if sign.turn_direction == "left":
                return 8
            elif coeff_fr > 250:
                return 7
        elif self.turn_direction == "right" and coeff_fr > 150:
            return 7

        coeff_size = self._calc_coeff_size(min_size, max_size)
        if coeff_size < 5:
            return 5
        else:
            if coeff_fr > 250:
                return 2
            elif coeff_fr < 150:
                return 5
            elif max(sign.heights) < 100:   # ← было sign.h
                return 5
            else:
                return 2

    # ── Дедупликация ──────────────────────────────────────────────

    def is_duplicate_location(self, new_sign, radius_meters: float = 50) -> bool:
        """
        True если в self.signs уже есть знак с тем же number_sign
        в радиусе radius_meters от new_sign.
        """
        if not self.signs:
            return False
        for sign in self.signs:
            if sign.latitude is None or sign.longitude is None:
                continue
            dist = self.calculate_distance(
                sign.latitude, sign.longitude,
                new_sign.latitude, new_sign.longitude,
            )
            if dist <= radius_meters and sign.number_sign == new_sign.number_sign:
                return True
        return False

    # ── Расстояния ────────────────────────────────────────────────

    @staticmethod
    def calculate_distance(lat1: float, lon1: float,
                           lat2: float, lon2: float) -> float:
        """Haversine: расстояние в метрах между двумя WGS84-точками."""
        R     = 6_371_000.0
        phi1  = math.radians(lat1)
        phi2  = math.radians(lat2)
        dphi  = math.radians(lat2 - lat1)
        dlam  = math.radians(lon2 - lon1)
        a     = (math.sin(dphi / 2.0) ** 2
                 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2)
        return R * 2.0 * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))

    def update_sign_distance(self, sign) -> None:
        """
        Вычисляет sign.distance (метры) — расстояние от начала поворота
        до позиции знака. Использует car_x/car_y (EPSG:32635).
        """
        lat_sign = lon_sign = None
        conv = self._converter()

        if sign.car_x and sign.car_y:
            try:
                lat_sign, lon_sign = conv.coordinateConverter(
                    sign.car_x[-1], sign.car_y[-1],
                    "epsg:32635", "epsg:4326",
                )
            except Exception:
                pass

        # Fallback: прямые gps_lat/gps_lon если есть
        if lat_sign is None:
            lat_sign = getattr(sign, "gps_lat", None)
            lon_sign = getattr(sign, "gps_lon", None)

        if lat_sign is None or lon_sign is None:
            sign.distance = None
            return

        if self.coordinates:
            ref_lat, ref_lon = self.coordinates[0]
        else:
            ref_lat, ref_lon = self._gpx().get_current_coordinate(config.INDEX_OF_GPS)

        try:
            sign.distance = round(
                self.calculate_distance(ref_lat, ref_lon, lat_sign, lon_sign), 3
            )
        except Exception:
            sign.distance = None

    # ── Словарь по азимутам ───────────────────────────────────────

    def arr_to_dict(self) -> None:
        """Группирует signs по целому азимуту в signs_dict."""
        for item in self.signs:
            key = int(item.azimuth)
            if key in self.signs_dict:
                self.signs_dict[key].append(item)
            else:
                self.signs_dict[key] = [item]

    # ── Вспомогательные геометрические методы ────────────────────

    def _calc_diff_x(self, sign) -> float:
        return sign.pixel_x[-2] - min(sign.pixel_x)   # ← было pixel_coordinates_x

    def _calc_max_size(self, sign) -> float:
        max_idx = sign.widths.index(max(sign.widths))  # ← было sign.w
        return sign.widths[max_idx] * sign.heights[max_idx]

    def _calc_min_size(self, sign) -> float:
        min_idx = sign.widths.index(min(sign.widths))
        return sign.widths[min_idx] * sign.heights[min_idx]

    def _calc_coeff_frames(self, sign, min_size: float, max_size: float) -> float:
        return round((max_size - min_size) / len(sign.frame_numbers), 0)

    @staticmethod
    def _calc_coeff_size(min_size: float, max_size: float) -> float:
        if min_size == 0:
            return 0.0
        return round(max_size / min_size, 1)
