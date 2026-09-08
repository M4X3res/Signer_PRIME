"""
core/osm_snap.py
OSMSnapper — snap координат знака к ближайшему ребру дороги OSM.

Вместо координаты автомобиля + GPX-курс:
  1. Запрашиваем Overpass API — ближайшие дороги в радиусе
  2. Находим ближайшее ребро дороги (point-to-segment projection)
  3. Берём азимут из направления ребра, а не из GPX
  4. Возвращаем точку snap + корректный азимут

BLOCK 2.3.1: Персистентный кеш:
  - При первой обработке маршрута — загружаем OSM ways для всего bbox GPX-трека
  - Сохраняем в <video_dir>/<video_name>_osm_cache.json
  - При последующих запусках — читаем из локального файла, не бьём в Overpass
  - Полностью офлайн-режим после первого кеширования
"""
from __future__ import annotations

import json
import math
import os
import time
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Optional

import requests

from core.coordinate_calculation import CoordinateCalculation


@dataclass
class SnapResult:
    """Результат привязки к дороге."""
    lat:     float          # широта снэпнутой точки
    lon:     float          # долгота снэпнутой точки
    azimuth: float          # азимут ребра дороги
    distance_m: float = -1.0  # расстояние от оригинальной точки до дороги (м)
    road_name: str = ""     # название улицы если есть
    lanes: Optional[int] = None      # количество полос (из OSM tags)
    width: Optional[float] = None    # ширина дороги в метрах (из OSM tags)
    snapped: bool  = True   # False = snap не удался, вернули оригинал
    side_relative_to_way: Optional[bool] = None  # True = слева от направления way, False = справа (BLOCK I.1)


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
    REQUEST_TIMEOUT= 3       # секунд (было 2)
    CACHE_SIZE     = 512     # ячеек кеша
    MIN_REQUEST_INTERVAL = 0.3  # сек между запросами к Overpass (было 0.5)
    MAX_RETRIES    = 2       # максимум попыток

    # Типы дорог которые учитываем (OSM highway tag)
    ROAD_TYPES = {
        "motorway", "trunk", "primary", "secondary", "tertiary",
        "unclassified", "residential", "service",
        "motorway_link", "trunk_link", "primary_link",
        "secondary_link", "tertiary_link",
    }

    def __init__(self):
        self._last_request = 0.0
        self._cache: dict[tuple, list] = {}  # (cell_lat, cell_lon) → ways (в памяти)
        self._persistent_cache_path: Optional[Path] = None  # Путь к файлу кеша
        self._persistent_cache_loaded: bool = False  # Флаг загрузки из файла

    # ── Персистентный кеш (BLOCK 2.3.1) ──────────────────────────

    def set_cache_path(self, video_path: str) -> None:
        """
        Устанавливает путь к файлу персистентного кеша на основе пути к видео.
        
        Args:
            video_path: Путь к видеофайлу (например, "C:/videos/drive_20260824.mp4")
        
        Кеш будет сохранён как: "C:/videos/drive_20260824_osm_cache.json"
        """
        if not video_path:
            return
        
        video_dir = Path(video_path).parent
        video_name = Path(video_path).stem
        cache_filename = f"{video_name}_osm_cache.json"
        self._persistent_cache_path = video_dir / cache_filename
        
        # Пытаемся загрузить существующий кеш
        self._load_persistent_cache()
    
    def _load_persistent_cache(self) -> bool:
        """
        Загружает OSM ways из локального JSON-файла.
        
        Returns:
            True если кеш успешно загружен, False иначе
        """
        if not self._persistent_cache_path or not self._persistent_cache_path.exists():
            return False
        
        try:
            with open(self._persistent_cache_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Проверяем версию формата
            if data.get("version") != "1.0":
                print(f"[OSMSnapper] Устаревшая версия кеша, будет обновлён")
                return False
            
            # Загружаем ways
            cached_ways = data.get("ways", [])
            if not cached_ways:
                return False
            
            # Распределяем ways по ячейкам сетки для быстрого доступа
            # (как в оригинальном алгоритме)
            bbox = data.get("bbox", {})
            print(f"[OSMSnapper] Загружен локальный кеш: {len(cached_ways)} дорог, bbox={bbox}")
            
            # Сохраняем ways в специальную ячейку кеша "bbox"
            self._cache[("bbox_cache",)] = cached_ways
            self._persistent_cache_loaded = True
            
            return True
            
        except Exception as e:
            print(f"[OSMSnapper] Ошибка загрузки кеша: {e}")
            return False
    
    def _save_persistent_cache(self, bbox: dict, ways: list) -> None:
        """
        Сохраняет OSM ways в локальный JSON-файл.
        
        Args:
            bbox: Bounding box {"min_lat", "max_lat", "min_lon", "max_lon"}
            ways: Список OSM ways (формат как из _parse_ways)
        """
        if not self._persistent_cache_path:
            return
        
        try:
            cache_data = {
                "version": "1.0",
                "generated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                "bbox": bbox,
                "way_count": len(ways),
                "ways": ways
            }
            
            # Создаём директорию если не существует
            self._persistent_cache_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(self._persistent_cache_path, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, indent=2, ensure_ascii=False)
            
            print(f"[OSMSnapper] Кеш сохранён: {self._persistent_cache_path}")
            print(f"[OSMSnapper] Дорог в кеше: {len(ways)}, bbox={bbox}")
            
        except Exception as e:
            print(f"[OSMSnapper] Ошибка сохранения кеша: {e}")
    
    def clear_persistent_cache(self) -> bool:
        """
        Удаляет файл персистентного кеша (для принудительного обновления).
        
        Returns:
            True если кеш успешно удалён, False иначе
        """
        if not self._persistent_cache_path or not self._persistent_cache_path.exists():
            return False
        
        try:
            self._persistent_cache_path.unlink()
            self._cache.clear()
            self._persistent_cache_loaded = False
            print(f"[OSMSnapper] Кеш удалён: {self._persistent_cache_path}")
            return True
        except Exception as e:
            print(f"[OSMSnapper] Ошибка удаления кеша: {e}")
            return False

    # ── Batch операции (D.1) ──────────────────────────────────────

    def snap_batch(
        self,
        points: list[tuple[float, float]],  # [(lat, lon), ...]
        radius_m: float = DEFAULT_RADIUS,
    ) -> list[SnapResult]:
        """
        Batch снаппинг нескольких точек.
        Загружает дороги один раз для всего bounding box вместо per-point запросов.
        
        Args:
            points: Список координат (lat, lon)
            radius_m: Радиус поиска вокруг каждой точки
            
        Returns:
            Список SnapResult в том же порядке что и points
        """
        if not points:
            return []
        
        # Вычисляем bounding box всех точек
        lats = [p[0] for p in points]
        lons = [p[1] for p in points]
        
        min_lat, max_lat = min(lats), max(lats)
        min_lon, max_lon = min(lons), max(lons)
        
        # Расширяем bbox на radius_m (примерно)
        # 1° широты ≈ 111 км
        buffer_deg = radius_m / 111000.0
        min_lat -= buffer_deg
        max_lat += buffer_deg
        min_lon -= buffer_deg
        max_lon += buffer_deg
        
        # Загружаем все дороги в bbox один раз
        ways = self._get_ways_bbox(min_lat, max_lat, min_lon, max_lon)
        
        if not ways:
            # Нет дорог в области — возвращаем unsnapped результаты
            return [SnapResult(lat=lat, lon=lon, azimuth=0.0, snapped=False) 
                    for lat, lon in points]
        
        # Снаппим каждую точку к загруженным дорогам
        results = []
        for lat, lon in points:
            best = self._find_closest_segment(lat, lon, ways)
            if best is None:
                results.append(SnapResult(lat=lat, lon=lon, azimuth=0.0, snapped=False))
            else:
                snap_lat, snap_lon, azimuth, distance_m, road_name, lanes, width, side = best
                results.append(SnapResult(
                    lat=snap_lat,
                    lon=snap_lon,
                    azimuth=azimuth,
                    distance_m=distance_m,
                    road_name=road_name,
                    lanes=lanes,
                    width=width,
                    side_relative_to_way=side,
                    snapped=True,
                ))
        
        return results

    def _get_ways_bbox(
        self, 
        min_lat: float, 
        max_lat: float, 
        min_lon: float, 
        max_lon: float,
        force_reload: bool = False
    ) -> list:
        """
        Загружает все дороги в прямоугольной области.
        
        BLOCK 2.3.1: Поддержка персистентного кеша:
          - При первом вызове (если set_cache_path вызван) — пытается загрузить из файла
          - Если файла нет — запрашивает Overpass и сохраняет в файл
          - При повторных запусках — читает из файла, Overpass не вызывается
        
        Args:
            min_lat, max_lat, min_lon, max_lon: Bounding box
            force_reload: Принудительно перезагрузить из Overpass (игнорировать кеш)
        
        Returns:
            Список OSM ways
        """
        # BLOCK 2.3.1: Проверяем персистентный кеш
        if self._persistent_cache_loaded and not force_reload:
            cached_ways = self._cache.get(("bbox_cache",), [])
            if cached_ways:
                print(f"[OSMSnapper] Используется локальный кеш: {len(cached_ways)} дорог")
                return cached_ways
        
        # Кеша нет или force_reload — запрашиваем Overpass
        print(f"[OSMSnapper] Запрос OSM подложки из Overpass API...")
        
        # Rate limiting
        now = time.monotonic()
        wait = self.MIN_REQUEST_INTERVAL - (now - self._last_request)
        if wait > 0:
            time.sleep(wait)
        
        query = f"""
        [out:json][timeout:10];
        (
          way["highway"~"^({'|'.join(self.ROAD_TYPES)})$"]
            ({min_lat},{min_lon},{max_lat},{max_lon});
        );
        out body;
        >;
        out skel qt;
        """
        
        retry_count = 0
        while retry_count <= self.MAX_RETRIES:
            try:
                resp = requests.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    timeout=self.REQUEST_TIMEOUT * 3,  # Больший таймаут для bbox запроса
                )
                resp.raise_for_status()
                data = resp.json()
                self._last_request = time.monotonic()
                
                ways = self._parse_ways(data)
                
                # BLOCK 2.3.1: Сохраняем в персистентный кеш
                if self._persistent_cache_path and ways:
                    bbox_dict = {
                        "min_lat": min_lat,
                        "max_lat": max_lat,
                        "min_lon": min_lon,
                        "max_lon": max_lon
                    }
                    self._save_persistent_cache(bbox_dict, ways)
                    # Сохраняем в оперативный кеш
                    self._cache[("bbox_cache",)] = ways
                    self._persistent_cache_loaded = True
                
                return ways
                
            except (requests.Timeout, requests.ConnectionError) as e:
                retry_count += 1
                if retry_count > self.MAX_RETRIES:
                    print(f"[OSMSnapper] Batch request timeout after {self.MAX_RETRIES} retries: {e}")
                    return []
                time.sleep(0.2)
            except Exception as e:
                print(f"[OSMSnapper] Batch request error: {e}")
                return []
        
        return []

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

        snap_lat, snap_lon, azimuth, distance_m, road_name, lanes, width, side = best
        return SnapResult(
            lat=snap_lat,
            lon=snap_lon,
            azimuth=azimuth,
            distance_m=distance_m,
            road_name=road_name,
            lanes=lanes,
            width=width,
            side_relative_to_way=side,
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
        retry_count = 0
        while retry_count <= self.MAX_RETRIES:
            try:
                resp = requests.post(
                    self.OVERPASS_URL,
                    data={"data": query},
                    timeout=self.REQUEST_TIMEOUT,
                )
                resp.raise_for_status()
                data = resp.json()
                self._last_request = time.monotonic()
                
                ways = self._parse_ways(data)
                self._cache[cell] = ways

                # Ограничиваем кеш
                if len(self._cache) > self.CACHE_SIZE:
                    oldest = next(iter(self._cache))
                    del self._cache[oldest]

                return ways
            except (requests.Timeout, requests.ConnectionError) as e:
                retry_count += 1
                if retry_count > self.MAX_RETRIES:
                    print(f"[OSMSnapper] Timeout/Connection error after {self.MAX_RETRIES} retries: {e}")
                    self._cache[cell] = []
                    return []
                # Короткая пауза перед повторной попыткой
                time.sleep(0.2)
            except Exception as e:
                print(f"[OSMSnapper] Overpass error: {e}")
                self._cache[cell] = []
                return []

        self._cache[cell] = []
        return []

    def _build_query(self, lat: float, lon: float, radius_m: float) -> str:
        """Overpass QL запрос — дороги вокруг точки."""
        road_filter = "|".join(self.ROAD_TYPES)
        return f"""
[out:json][timeout:3];
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
            "lanes": int or None,     # Число полос (если есть в OSM)
            "width": float or None,   # Ширина дороги в метрах (если есть)
            "oneway": bool,           # Односторонняя дорога
            "junction": str,          # Тип перекрёстка (roundabout, ...)
            "tags": dict,             # Полный набор тегов
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
            tags = el.get("tags", {})
            name = tags.get("name", "")
            
            # Парсим lanes (количество полос)
            lanes = None
            lanes_str = tags.get("lanes", "")
            if lanes_str:
                try:
                    lanes = int(lanes_str)
                except ValueError:
                    pass
            
            # Парсим width (ширина дороги в метрах)
            width = None
            width_str = tags.get("width", "")
            if width_str:
                try:
                    # Убираем единицы измерения если есть
                    width_str = width_str.replace("m", "").replace("м", "").strip()
                    width = float(width_str)
                except ValueError:
                    pass
            
            # Парсим oneway
            oneway = tags.get("oneway", "no") == "yes"
            
            # Парсим junction
            junction = tags.get("junction", "")
            
            ways.append({
                "nodes": nodes, 
                "name": name,
                "lanes": lanes,
                "width": width,
                "oneway": oneway,
                "junction": junction,
                "tags": tags,
            })
        return ways

    # ── Геометрия ─────────────────────────────────────────────────

    def _find_closest_segment(
        self, lat: float, lon: float, ways: list[dict]
    ) -> Optional[tuple[float, float, float, float, str, Optional[int], Optional[float], Optional[bool]]]:
        """
        Для каждого ребра всех дорог вычисляет проекцию точки на отрезок.
        Возвращает (snap_lat, snap_lon, azimuth, distance_m, road_name, lanes, width, side) ближайшего.
        
        Returns:
            Tuple (snap_lat, snap_lon, azimuth, distance_m, road_name, lanes, width, side) или None
            - lanes: количество полос (может быть None)
            - width: ширина дороги в метрах (может быть None)
            - side: True = точка слева от направления way (p1→p2), False = справа (BLOCK I.1)
        """
        best_dist = float("inf")
        best: Optional[tuple] = None

        for way in ways:
            nodes     = way["nodes"]
            road_name = way["name"]
            lanes     = way.get("lanes")
            width     = way.get("width")

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
                    
                    # BLOCK I.1: Вычисляем сторону через векторное произведение
                    # Переводим в локальные метры для точного векторного произведения
                    side = self._compute_side_of_segment((lat, lon), p1, p2)
                    
                    best = (snap_pt[0], snap_pt[1], azimuth, best_dist, road_name, lanes, width, side)

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
    def _compute_side_of_segment(
        point: tuple[float, float],
        p1: tuple[float, float],
        p2: tuple[float, float],
    ) -> bool:
        """
        Определяет с какой стороны от направленного отрезка p1→p2 находится точка.
        Использует знак векторного произведения (p2-p1) × (point-p1) в локальных метрах.
        
        Args:
            point: точка для проверки (lat, lon)
            p1: начало отрезка (lat, lon)
            p2: конец отрезка (lat, lon)
        
        Returns:
            True если точка слева от направления p1→p2, False если справа
        
        Note:
            Используется для геометрического определения стороны знака относительно
            направления дороги, что надёжнее пиксельной эвристики (BLOCK I.1).
            
            В географических координатах: lat=Y (север-юг), lon=X (запад-восток).
            При движении на юг: восток=справа, запад=слева.
        """
        # Переводим в локальные метры относительно p1 (центр координат)
        lat0 = p1[0]
        m_per_lat = 111320.0
        m_per_lon = 111320.0 * math.cos(math.radians(lat0))
        
        # Вектор p1→p2 в метрах (lon, lat) → (X, Y)
        v1_x = (p2[1] - p1[1]) * m_per_lon  # дельта долготы (X)
        v1_y = (p2[0] - p1[0]) * m_per_lat  # дельта широты (Y)
        
        # Вектор p1→point в метрах
        v2_x = (point[1] - p1[1]) * m_per_lon
        v2_y = (point[0] - p1[0]) * m_per_lat
        
        # Векторное произведение (2D cross product): v1 × v2 = v1_x*v2_y - v1_y*v2_x
        # Положительный знак = точка слева от направления p1→p2 (в стандартной математической системе)
        # Отрицательный знак = точка справа от направления p1→p2
        #
        # ВАЖНО: Это определение "слева/справа" относительно направления OSM way (p1→p2),
        # НЕ относительно направления движения автомобиля! Если автомобиль едет в обратном
        # направлении (против way), стороны нужно инвертировать в FinalHandler.
        cross_product = v1_x * v2_y - v1_y * v2_x
        
        return cross_product > 0

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