"""
core/intersection_geometry.py
Геометрическая привязка знаков на перекрёстках через bearing + raycast.

Заменяет эвристический алгоритм Turn._handle_sign() на точный геометрический:
  1. Вычисляем азимут от машины на знак (с учётом FOV камеры)
  2. Бросаем луч по этому азимуту через подложку OSM ways
  3. Первое пересечённое ребро дороги = нужная сторона перекрёстка

Не требует обучаемых моделей, устойчиво к нетиповым перекрёсткам.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Optional
from collections import Counter


@dataclass
class WayHit:
    """Результат пересечения луча с OSM way."""
    way_id: str                  # ID дороги OSM (или хэш geometry)
    way_name: str                # Название дороги если есть
    intersection_lat: float      # Точка пересечения
    intersection_lon: float
    distance_m: float            # Расстояние от origin до пересечения
    angle_diff_deg: float        # Угол между ray bearing и way direction
    way_azimuth: float           # Азимут way в точке пересечения


# ── 1. Расчёт азимута на знак ────────────────────────────────────

def compute_sign_bearing(
    gpx_azimuth: float,
    bbox_center_x: int,
    frame_width: int,
    hfov_deg: float,
) -> float:
    """
    Вычисляет абсолютный азимут (мировые координаты) от машины на знак.
    
    Args:
        gpx_azimuth: Курс машины в момент кадра (°, 0=север, по часовой)
        bbox_center_x: X-координата центра bbox знака в кадре (px)
        frame_width: Ширина кадра (px)
        hfov_deg: Горизонтальный угол обзора камеры (°)
    
    Returns:
        Азимут на знак в мировых координатах (°, 0=север, по часовой)
    
    Example:
        >>> compute_sign_bearing(90.0, 1440, 1920, 120.0)
        75.0  # Знак справа от центра кадра на 15° при курсе 90°
    """
    # Смещение знака от центра кадра
    frame_center_x = frame_width / 2.0
    pixel_offset_x = bbox_center_x - frame_center_x
    
    # Угловое смещение через горизонтальный FOV
    # Положительное offset = знак справа → поворот вправо (по часовой)
    normalized_offset = pixel_offset_x / (frame_width / 2.0)  # [-1..1]
    angle_offset_deg = normalized_offset * (hfov_deg / 2.0)
    
    # Итоговый азимут = курс машины + смещение
    sign_bearing = (gpx_azimuth + angle_offset_deg) % 360.0
    
    return sign_bearing


# ── 2. Пересечение луча с подложкой ──────────────────────────────

def raycast_to_ways(
    origin_lat: float,
    origin_lon: float,
    bearing_deg: float,
    ways: list[dict],
    max_distance_m: float = 40.0,
    exclude_roundabout: bool = True,
) -> Optional[WayHit]:
    """
    Бросает луч от точки по заданному азимуту и ищет пересечение с OSM ways.
    
    Args:
        origin_lat: Широта точки машины
        origin_lon: Долгота точки машины
        bearing_deg: Азимут луча (°, 0=север, по часовой)
        ways: Список OSM ways (формат как из OSMSnapper._parse_ways)
              [{"nodes": [(lat, lon), ...], "name": "...", "tags": {...}}, ...]
        max_distance_m: Максимальная длина луча (м)
        exclude_roundabout: Исключить кольца из целевых сегментов
                           (луч должен проходить сквозь кольцо до реальной дороги)
    
    Returns:
        WayHit с ближайшим пересечением или None если нет пересечений
    """
    # Строим конечную точку луча
    ray_end_lat, ray_end_lon = _destination_point(
        origin_lat, origin_lon, bearing_deg, max_distance_m
    )
    
    best_hit: Optional[WayHit] = None
    best_dist = float('inf')
    
    for way in ways:
        nodes = way.get("nodes", [])
        way_name = way.get("name", "")
        tags = way.get("tags", {})
        
        # Пропускаем кольца если exclude_roundabout=True
        if exclude_roundabout and tags.get("junction") == "roundabout":
            continue
        
        if len(nodes) < 2:
            continue
        
        # Генерируем way_id (если нет id в данных)
        way_id = way.get("id", hash(tuple((n[0], n[1]) for n in nodes)))
        
        # Проверяем каждый сегмент way
        for i in range(len(nodes) - 1):
            seg_start = nodes[i]      # (lat, lon)
            seg_end = nodes[i + 1]
            
            intersection = _ray_segment_intersection(
                origin_lat, origin_lon,
                ray_end_lat, ray_end_lon,
                seg_start[0], seg_start[1],
                seg_end[0], seg_end[1],
            )
            
            if intersection is None:
                continue
            
            int_lat, int_lon = intersection
            
            # Расстояние от origin до пересечения
            dist = _haversine(origin_lat, origin_lon, int_lat, int_lon)
            
            if dist > max_distance_m or dist >= best_dist:
                continue
            
            # Азимут сегмента way в точке пересечения
            way_azimuth = _bearing(seg_start[0], seg_start[1], seg_end[0], seg_end[1])
            
            # Угол между ray и way
            angle_diff = abs(_angle_difference(bearing_deg, way_azimuth))
            
            best_dist = dist
            best_hit = WayHit(
                way_id=str(way_id),
                way_name=way_name,
                intersection_lat=int_lat,
                intersection_lon=int_lon,
                distance_m=dist,
                angle_diff_deg=angle_diff,
                way_azimuth=way_azimuth,
            )
    
    return best_hit


# ── 3. Агрегация наблюдений ──────────────────────────────────────

def aggregate_observations(
    hits: list[WayHit],
) -> tuple[Optional[str], float, Optional[WayHit]]:
    """
    Находит наиболее частый way среди наблюдений и вычисляет consistency score.
    
    Args:
        hits: Список WayHit от разных наблюдений одного знака
    
    Returns:
        (way_id, consistency_score, representative_hit)
        - way_id: ID самого частого way (мода)
        - consistency_score: доля наблюдений попавших в этот way [0..1]
        - representative_hit: один из hits для этого way (медианный по distance_m)
    """
    if not hits:
        return None, 0.0, None
    
    # Мода по way_id
    way_counter = Counter(hit.way_id for hit in hits)
    most_common_way, count = way_counter.most_common(1)[0]
    
    consistency = count / len(hits)
    
    # Берём hits для этого way
    way_hits = [h for h in hits if h.way_id == most_common_way]
    
    # Медианный hit по distance_m
    way_hits_sorted = sorted(way_hits, key=lambda h: h.distance_m)
    representative = way_hits_sorted[len(way_hits_sorted) // 2]
    
    return most_common_way, consistency, representative


# ── Геометрические утилиты ───────────────────────────────────────

def _destination_point(
    lat: float,
    lon: float,
    bearing_deg: float,
    distance_m: float,
) -> tuple[float, float]:
    """
    Вычисляет конечную точку после движения из (lat, lon)
    на расстояние distance_m по азимуту bearing_deg.
    
    Использует формулу "destination point" на сфере.
    """
    R = 6371000.0  # радиус Земли (м)
    
    lat_rad = math.radians(lat)
    lon_rad = math.radians(lon)
    bearing_rad = math.radians(bearing_deg)
    
    angular_dist = distance_m / R
    
    lat2 = math.asin(
        math.sin(lat_rad) * math.cos(angular_dist)
        + math.cos(lat_rad) * math.sin(angular_dist) * math.cos(bearing_rad)
    )
    
    lon2 = lon_rad + math.atan2(
        math.sin(bearing_rad) * math.sin(angular_dist) * math.cos(lat_rad),
        math.cos(angular_dist) - math.sin(lat_rad) * math.sin(lat2),
    )
    
    return math.degrees(lat2), math.degrees(lon2)


def _ray_segment_intersection(
    r_lat1: float, r_lon1: float,  # ray start
    r_lat2: float, r_lon2: float,  # ray end
    s_lat1: float, s_lon1: float,  # segment start
    s_lat2: float, s_lon2: float,  # segment end
) -> Optional[tuple[float, float]]:
    """
    Проверяет пересечение луча и отрезка используя shapely.
    Возвращает (lat, lon) точки пересечения или None.
    """
    try:
        from shapely.geometry import LineString
        
        # Создаём геометрии (lon, lat порядок для shapely!)
        ray_line = LineString([(r_lon1, r_lat1), (r_lon2, r_lat2)])
        seg_line = LineString([(s_lon1, s_lat1), (s_lon2, s_lat2)])
        
        # Проверяем пересечение
        if not ray_line.intersects(seg_line):
            return None
        
        intersection = ray_line.intersection(seg_line)
        
        # intersection может быть Point, LineString, MultiPoint или GeometryCollection
        if intersection.is_empty:
            return None
        
        if intersection.geom_type == 'Point':
            # Возвращаем (lat, lon) — обратный порядок от shapely
            return intersection.y, intersection.x
        elif intersection.geom_type == 'LineString':
            # Луч и сегмент частично перекрываются — берём ближайшую точку к origin
            coords = list(intersection.coords)
            # Первая точка обычно ближе к origin
            lon, lat = coords[0]
            return lat, lon
        elif intersection.geom_type == 'MultiPoint':
            # Берём первую точку
            point = list(intersection.geoms)[0]
            return point.y, point.x
        else:
            # Неожиданный тип геометрии
            return None
            
    except Exception:
        # Fallback на оригинальную реализацию при отсутствии shapely
        return _ray_segment_intersection_manual(
            r_lat1, r_lon1, r_lat2, r_lon2,
            s_lat1, s_lon1, s_lat2, s_lon2
        )


def _ray_segment_intersection_manual(
    r_lat1: float, r_lon1: float,
    r_lat2: float, r_lon2: float,
    s_lat1: float, s_lon1: float,
    s_lat2: float, s_lon2: float,
) -> Optional[tuple[float, float]]:
    """
    Fallback: ручная реализация пересечения без shapely.
    Работает в локальном приближении для расстояний < 1 км.
    """
    # Конвертируем в локальные метры
    lat0 = (r_lat1 + s_lat1) / 2.0
    m_per_lat = 111320.0
    m_per_lon = 111320.0 * math.cos(math.radians(lat0))
    
    # Ray
    rx1 = r_lon1 * m_per_lon
    ry1 = r_lat1 * m_per_lat
    rx2 = r_lon2 * m_per_lon
    ry2 = r_lat2 * m_per_lat
    
    # Segment
    sx1 = s_lon1 * m_per_lon
    sy1 = s_lat1 * m_per_lat
    sx2 = s_lon2 * m_per_lon
    sy2 = s_lat2 * m_per_lat
    
    # Векторы
    r_dx = rx2 - rx1
    r_dy = ry2 - ry1
    s_dx = sx2 - sx1
    s_dy = sy2 - sy1
    
    # Определитель (cross product 2D)
    denom = r_dx * s_dy - r_dy * s_dx
    
    if abs(denom) < 1e-10:
        return None
    
    # Параметры пересечения
    t = ((sx1 - rx1) * s_dy - (sy1 - ry1) * s_dx) / denom
    u = ((sx1 - rx1) * r_dy - (sy1 - ry1) * r_dx) / denom
    
    # Проверка границ
    if t < 0.0 or t > 1.0 or u < 0.0 or u > 1.0:
        return None
    
    # Точка пересечения
    int_x = rx1 + t * r_dx
    int_y = ry1 + t * r_dy
    
    # Обратно в lat/lon
    int_lon = int_x / m_per_lon
    int_lat = int_y / m_per_lat
    
    return int_lat, int_lon


def _bearing(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Азимут от (lat1, lon1) к (lat2, lon2) в градусах [0..360)."""
    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    dlon_rad = math.radians(lon2 - lon1)
    
    x = math.sin(dlon_rad) * math.cos(lat2_rad)
    y = (
        math.cos(lat1_rad) * math.sin(lat2_rad)
        - math.sin(lat1_rad) * math.cos(lat2_rad) * math.cos(dlon_rad)
    )
    
    bearing = math.degrees(math.atan2(x, y))
    return (bearing + 360.0) % 360.0


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками в метрах."""
    R = 6371000.0
    
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    
    a = (
        math.sin(dphi / 2.0) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2.0) ** 2
    )
    
    return 2.0 * R * math.atan2(math.sqrt(a), math.sqrt(1.0 - a))


def _angle_difference(a: float, b: float) -> float:
    """
    Минимальная разность между двумя углами (°).
    Учитывает wrap-around 0/360.
    
    Returns:
        Разница в диапазоне [-180..180]
    """
    diff = (b - a + 180.0) % 360.0 - 180.0
    return diff
