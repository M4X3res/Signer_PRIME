"""
core/osm_snap.py
OSMSnapper — snap координат знака к ближайшему ребру дороги OSM.

Вместо координаты автомобиля + GPX-курс:
  1. Запрашиваем Overpass API — ближайшие дороги в радиусе
  2. Находим ближайшее ребро дороги (point-to-segment projection)
  3. Берём азимут из направления ребра, а не из GPX
  4. Возвращаем точку snap + корректный азимут

Кешируем ответы Overpass чтобы не запрашивать одно место дважды.
"""
from __future__ import annotations

import math
import time
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Optional

import requests

from core.coordinate_calculation import CoordinateCalculation


@dataclass
class SnapResult:
    """Результат привязки к дороге."""
    lat:     float          # широта снэпнутой точки
    lon:     float          # долгота снэпнутой точки
    azimuth: float          # азимут ребра дороги
    road_name: str = ""     # название улицы если есть
    snapped: bool  = True   # False = snap не удался, вернули оригинал


class OSMSnapper:
    """
    Привязывает GPS-координату знака к ближайшему ребру дороги OSM.

    Использование:
        snapper = OSMSnapper()
        result  = snapper.snap(lat=53.902, lon=27.561, radius_m=30)
        print(result.lat, result.lon, result.azimuth)
    """

    OVERPASS_URL   = "https://overpass-api.de/api/interpreter"
    DEFAULT_RADIUS = 30      # метров
    REQUEST_TIMEOUT= 5       # секунд
    CACHE_SIZE     = 512     # ячеек кеша
    MIN_REQUEST_INTERVAL = 0.5  # сек между запросами к Overpass

    # Типы дорог которые учитываем (OSM highway tag)
    ROAD_TYPES = {
        "motorway", "trunk", "primary", "secondary", "tertiary",
        "unclassified", "residential", "service",
        "motorway_link", "trunk_link", "primary_link",
        "secondary_link", "tertiary_link",
    }

    def __init__(self):
        self._last_request = 0.0
        self._cache: dict[tuple, list] = {}  # (cell_lat, cell_lon) → ways

    # ── Главный метод ─────────────────────────────────────────────

    def snap(
        self,
        lat: float,
        lon: float,
        radius_m: float = DEFAULT_RADIUS,
    ) -> SnapResult:
        """
        Привязывает точку (lat, lon) к ближайшему ребру дороги.
        При неудаче возвращает оригинальные координаты.
        """
        ways = self._get_ways(lat, lon, radius_m)
        if not ways:
            return SnapResult(lat=lat, lon=lon, azimuth=0.0, snapped=False)

        best = self._find_closest_segment(lat, lon, ways)
        if best is None:
            return SnapResult(lat=lat, lon=lon, azimuth=0.0, snapped=False)

        snap_lat, snap_lon, azimuth, road_name = best
        return SnapResult(
            lat=snap_lat,
            lon=snap_lon,
            azimuth=azimuth,
            road_name=road_name,
            snapped=True,
        )

    # ── Запрос к Overpass ─────────────────────────────────────────

    def _get_ways(self, lat: float, lon: float, radius_m: float) -> list:
        """
        Получает дороги в радиусе radius_m вокруг точки.
        Кеширует по ячейке сетки ~30м.
        """
        cell = (round(lat, 3), round(lon, 3))
        if cell in self._cache:
            return self._cache[cell]

        # Rate limiting
        now = time.monotonic()
        wait = self.MIN_REQUEST_INTERVAL - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)

        query = self._build_query(lat, lon, radius_m)
        try:
            resp = requests.post(
                self.OVERPASS_URL,
                data={"data": query},
                timeout=self.REQUEST_TIMEOUT,
            )
            resp.raise_for_status()
            data = resp.json()
            self._last_request = time.monotonic()
        except Exception as e:
            print(f"[OSMSnapper] Overpass error: {e}")
            self._cache[cell] = []
            return []

        ways = self._parse_ways(data)
        self._cache[cell] = ways

        # Ограничиваем кеш
        if len(self._cache) > self.CACHE_SIZE:
            oldest = next(iter(self._cache))
            del self._cache[oldest]

        return ways

    def _build_query(self, lat: float, lon: float, radius_m: float) -> str:
        """Overpass QL запрос — дороги вокруг точки."""
        road_filter = "|".join(self.ROAD_TYPES)
        return f"""
[out:json][timeout:5];
way(around:{radius_m},{lat},{lon})
  [highway~"^({road_filter})$"];
out geom;
"""

    def _parse_ways(self, data: dict) -> list[dict]:
        """
        Парсит ответ Overpass.
        Возвращает список:
          {
            "nodes": [(lat, lon), ...],
            "name":  "ул. Ленина",
          }
        """
        ways = []
        for el in data.get("elements", []):
            if el.get("type") != "way":
                continue
            geometry = el.get("geometry", [])
            if len(geometry) < 2:
                continue
            nodes = [(g["lat"], g["lon"]) for g in geometry]
            name  = el.get("tags", {}).get("name", "")
            ways.append({"nodes": nodes, "name": name})
        return ways

    # ── Геометрия ─────────────────────────────────────────────────

    def _find_closest_segment(
        self, lat: float, lon: float, ways: list[dict]
    ) -> Optional[tuple[float, float, float, str]]:
        """
        Для каждого ребра всех дорог вычисляет проекцию точки на отрезок.
        Возвращает (snap_lat, snap_lon, azimuth, road_name) ближайшего.
        """
        best_dist = float("inf")
        best: Optional[tuple] = None

        for way in ways:
            nodes    = way["nodes"]
            road_name= way["name"]

            for i in range(len(nodes) - 1):
                p1 = nodes[i]      # (lat, lon)
                p2 = nodes[i + 1]

                snap_pt = self._project_point_to_segment(
                    (lat, lon), p1, p2
                )
                dist = self._haversine(lat, lon, snap_pt[0], snap_pt[1])

                if dist < best_dist:
                    best_dist = dist
                    azimuth   = self._bearing(p1, p2)
                    best      = (snap_pt[0], snap_pt[1], azimuth, road_name)

        return best

    @staticmethod
    def _project_point_to_segment(
        p:  tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> tuple[float, float]:
        """
        Проекция точки p на отрезок p1-p2 в декартовых приближениях.
        Работает точно на расстояниях < 1 км.
        """
        # Переводим в "плоские" метры (приближение)
        lat0 = p1[0]
        m_per_lat = 111320.0
        m_per_lon = 111320.0 * math.cos(math.radians(lat0))

        ax = (p1[1] - p[1]) * m_per_lon
        ay = (p1[0] - p[0]) * m_per_lat
        bx = (p2[1] - p1[1]) * m_per_lon
        by = (p2[0] - p1[0]) * m_per_lat

        seg_len_sq = bx * bx + by * by
        if seg_len_sq == 0:
            return p1

        t = max(0.0, min(1.0, (-ax * bx - ay * by) / seg_len_sq))
        proj_lat = p1[0] + t * (p2[0] - p1[0])
        proj_lon = p1[1] + t * (p2[1] - p1[1])
        return (proj_lat, proj_lon)

    @staticmethod
    def _bearing(
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> float:
        """Азимут (0–360°) от p1 к p2."""
        lat1 = math.radians(p1[0])
        lat2 = math.radians(p2[0])
        dlon = math.radians(p2[1] - p1[1])

        x = math.sin(dlon) * math.cos(lat2)
        y = (math.cos(lat1) * math.sin(lat2)
             - math.sin(lat1) * math.cos(lat2) * math.cos(dlon))

        bearing = math.degrees(math.atan2(x, y))
        return (bearing + 360) % 360

    @staticmethod
    def _haversine(
        lat1: float, lon1: float,
        lat2: float, lon2: float,
    ) -> float:
        """Расстояние в метрах между двумя GPS точками."""
        R = 6371000.0
        φ1, φ2 = math.radians(lat1), math.radians(lat2)
        dφ = math.radians(lat2 - lat1)
        dλ = math.radians(lon2 - lon1)
        a  = (math.sin(dφ / 2) ** 2
              + math.cos(φ1) * math.cos(φ2) * math.sin(dλ / 2) ** 2)
        return 2 * R * math.atan2(math.sqrt(a), math.sqrt(1 - a))


# ── Синглтон ──────────────────────────────────────────────────────
_snapper: Optional[OSMSnapper] = None


def get_snapper() -> OSMSnapper:
    """Возвращает глобальный инстанс OSMSnapper."""
    global _snapper
    if _snapper is None:
        _snapper = OSMSnapper()
    return _snapper


def snap_sign(lat: float, lon: float, radius_m: float = 30) -> SnapResult:
    """
    Удобная функция-обёртка.
    Использование в FinalHandler:
        from core.osm_snap import snap_sign
        result = snap_sign(lat, lon)
        sign.latitude  = result.lat
        sign.longitude = result.lon
        sign.azimuth   = result.azimuth
    """
    return get_snapper().snap(lat, lon, radius_m)