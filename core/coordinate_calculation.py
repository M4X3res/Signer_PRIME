"""
core/coordinate_calculation.py
CoordinateCalculation — вычисление координат линии знака на карте.
Заменяет старый CoordinateCalculation.py.
"""
from __future__ import annotations

import math
from typing import TYPE_CHECKING

from geopy.distance import geodesic

from core.converter import Converter

if TYPE_CHECKING:
    from core.sign import TrackedSign


class CoordinateCalculation:
    _ONE_RADIAN = 57.2958

    def __init__(self):
        self._converter = Converter()

    # ── Главный метод: линия знака ────────────────────────────────

    def get_line(
        self, sign: "TrackedSign", coefficient: int
    ) -> tuple[float, float, float, float]:
        """
        Возвращает (lat1, lon1, lat2, lon2) — линию знака в WGS84.
        """
        x1, y1, x2, y2 = self._line_straight(sign, coefficient)
        lat1, lon1 = self._converter.coordinateConverter(
            x1, y1, "epsg:32635", "epsg:4326"
        )
        lat2, lon2 = self._converter.coordinateConverter(
            x2, y2, "epsg:32635", "epsg:4326"
        )
        return lat1, lon1, lat2, lon2

    def _line_straight(
        self, sign: "TrackedSign", coefficient: int
    ) -> tuple[float, float, float, float]:
        x_cur = sign.car_x[-1]
        y_cur = sign.car_y[-1]

        # Предыдущая точка — по азимуту назад на 5м
        lat_c, lon_c = self._converter.coordinateConverter(
            x_cur, y_cur, "epsg:32635", "epsg:4326"
        )
        az_back = (sign.azimuth + 180) % 360
        lat_p, lon_p = self.point_at_distance(lat_c, lon_c, az_back)
        x_prv, y_prv = self._converter.coordinateConverter(
            lat_p, lon_p, "epsg:4326", "epsg:32635"
        )

        return self.calculate_result_line(
            sign, coefficient, x_cur, y_cur, x_prv, y_prv
        )

    # ── Расчёт линии ──────────────────────────────────────────────

    @staticmethod
    def calculate_result_line(
        sign: "TrackedSign",
        coefficient: int,
        x_cur: float, y_cur: float,
        x_prv: float, y_prv: float,
    ) -> tuple[float, float, float, float]:
        dx = x_cur - x_prv
        dy = y_cur - y_prv

        is_side = sign.best_side

        if not is_side:
            if sign.is_left:
                if coefficient == 2:
                    x2, y2 = x_cur, y_cur
                else:
                    x2 = x_cur - dy * (coefficient - 2)
                    y2 = y_cur + dx * (coefficient - 2)
                x1 = x_cur - dy * (coefficient - 1)
                y1 = y_cur + dx * (coefficient - 1)
            else:
                x1 = x_cur + dy * coefficient
                y1 = y_cur - dx * coefficient
                x2 = x_cur + dy * (coefficient + 1)
                y2 = y_cur - dx * (coefficient + 1)
        else:
            if sign.is_left:
                x1 = x_cur - dy * (coefficient - 1)
                y1 = y_cur + dx * (coefficient - 1)
                x2 = x_prv - dy * (coefficient - 1)
                y2 = y_prv + dx * (coefficient - 1)
            else:
                x1 = x_cur + dy * coefficient
                y1 = y_cur - dx * coefficient
                x2 = x_prv + dy * coefficient
                y2 = y_prv - dx * coefficient

        return x1, y1, x2, y2

    # ── Вспомогательная геометрия ─────────────────────────────────

    @staticmethod
    def point_at_distance(
        lat: float, lon: float,
        azimuth_deg: float,
        distance_m: float = 5.0,
    ) -> tuple[float, float]:
        """Точка на расстоянии distance_m от (lat, lon) по азимуту."""
        R   = 6371000.0
        lat1 = math.radians(lat)
        lon1 = math.radians(lon)
        az   = math.radians(azimuth_deg)

        lat2 = math.asin(
            math.sin(lat1) * math.cos(distance_m / R)
            + math.cos(lat1) * math.sin(distance_m / R) * math.cos(az)
        )
        lon2 = lon1 + math.atan2(
            math.sin(az) * math.sin(distance_m / R) * math.cos(lat1),
            math.cos(distance_m / R) - math.sin(lat1) * math.sin(lat2),
        )
        return math.degrees(lat2), math.degrees(lon2)

    @staticmethod
    def bearing(
        lat1: float, lon1: float,
        lat2: float, lon2: float,
    ) -> float:
        """Азимут от точки 1 к точке 2 (0–360°)."""
        lat1r = math.radians(lat1)
        lat2r = math.radians(lat2)
        dlon  = math.radians(lon2 - lon1)
        x = math.sin(dlon) * math.cos(lat2r)
        y = (math.cos(lat1r) * math.sin(lat2r)
             - math.sin(lat1r) * math.cos(lat2r) * math.cos(dlon))
        return (math.degrees(math.atan2(x, y)) + 360) % 360

    @staticmethod
    def distance_m(
        lat1: float, lon1: float,
        lat2: float, lon2: float,
    ) -> float:
        """Расстояние в метрах между двумя WGS84 точками."""
        return geodesic((lat1, lon1), (lat2, lon2)).meters

    def calculate_azimuth_change(
        self, old_az: float, new_az: float
    ) -> float:
        delta = new_az - old_az
        if delta > 180:
            delta -= 360
        elif delta < -180:
            delta += 360
        return delta

    # ── Для совместимости с FinalHandler ─────────────────────────

    def calculation_distance(
        self, x1: float, y1: float,
        x2: float, y2: float,
    ) -> float:
        """Расстояние в метрах между двумя точками EPSG:32635."""
        lat1, lon1 = self._converter.coordinateConverter(
            x1, y1, "epsg:32635", "epsg:4326"
        )
        lat2, lon2 = self._converter.coordinateConverter(
            x2, y2, "epsg:32635", "epsg:4326"
        )
        return self.distance_m(lat1, lon1, lat2, lon2)

    def calculation_four_dots(self, turn) -> list:
        """
        Вычисляет 4 опорные точки поворота.
        Возвращает [start, end, rev_start, rev_end].
        Каждая точка: [lat, lon, lat2, lon2, azimuth]
        """
        if not turn.coordinates:
            return []

        coords   = turn.coordinates
        azimuths = turn.azimuths

        start = list(coords[0])  + [azimuths[0] if azimuths else 0]
        end   = list(coords[-1]) + [azimuths[-1] if azimuths else 0]

        # Упрощённые обратные точки
        az_offset = 60 if self._turn_direction(azimuths) >= 0 else -60
        lat_s, lon_s = coords[0]
        lat_e, lon_e = coords[-1]

        rev_lat_s, rev_lon_s = self.point_at_distance(
            lat_s, lon_s, (azimuths[0] + az_offset) % 360
            if azimuths else 0
        )
        rev_lat_e, rev_lon_e = self.point_at_distance(
            lat_s, lon_s, (azimuths[0] + az_offset / 2) % 360
            if azimuths else 0
        )

        rev_start = [rev_lat_s, rev_lon_s, lat_s, lon_s, azimuths[0] if azimuths else 0]
        rev_end   = [rev_lat_e, rev_lon_e, lat_e, lon_e, azimuths[-1] if azimuths else 0]

        return [start, end, rev_start, rev_end]

    def _turn_direction(self, azimuths: list) -> float:
        if len(azimuths) < 2:
            return 0
        return self.calculate_azimuth_change(azimuths[0], azimuths[-1])

    @staticmethod
    def calculate_new_line(
        old_line: list, new_point: list
    ) -> tuple[float, float]:
        lon1, lat1, lon2, lat2 = old_line
        az = CoordinateCalculation.bearing(lat1, lon1, lat2, lon2)
        new_lon, new_lat = new_point
        return CoordinateCalculation.point_at_distance(new_lat, new_lon, az)

    @staticmethod
    def calculate_direction(
        lon1: float, lat1: float,
        lon2: float, lat2: float,
    ) -> tuple[float, float]:
        az   = CoordinateCalculation.bearing(lat1, lon1, lat2, lon2)
        dist = CoordinateCalculation.distance_m(lat1, lon1, lat2, lon2)
        return az, dist