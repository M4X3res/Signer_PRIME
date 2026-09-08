"""
tests/test_intersection_geometry.py
Unit-тесты для геометрической привязки знаков на перекрёстках.
"""
import math
import pytest
from core.intersection_geometry import (
    compute_sign_bearing,
    raycast_to_ways,
    aggregate_observations,
    WayHit,
)


# ── Тесты compute_sign_bearing ────────────────────────────────────

def test_compute_sign_bearing_center():
    """Знак в центре кадра → bearing = gpx_azimuth."""
    result = compute_sign_bearing(
        gpx_azimuth=90.0,
        bbox_center_x=960,   # центр 1920
        frame_width=1920,
        hfov_deg=120.0,
    )
    assert abs(result - 90.0) < 0.1


def test_compute_sign_bearing_right():
    """Знак справа от центра → bearing > gpx_azimuth."""
    result = compute_sign_bearing(
        gpx_azimuth=90.0,
        bbox_center_x=1440,  # 480px вправо от центра = +0.5 * 60° = +30°
        frame_width=1920,
        hfov_deg=120.0,
    )
    assert abs(result - 120.0) < 0.1  # 90 + 30


def test_compute_sign_bearing_left():
    """Знак слева от центра → bearing < gpx_azimuth."""
    result = compute_sign_bearing(
        gpx_azimuth=90.0,
        bbox_center_x=480,   # 480px влево от центра = -0.5 * 60° = -30°
        frame_width=1920,
        hfov_deg=120.0,
    )
    assert abs(result - 60.0) < 0.1  # 90 - 30


def test_compute_sign_bearing_wrap():
    """Проверка wrap-around через 360°."""
    result = compute_sign_bearing(
        gpx_azimuth=350.0,
        bbox_center_x=1440,
        frame_width=1920,
        hfov_deg=120.0,
    )
    # 350 + 30 = 380 → 20
    assert abs(result - 20.0) < 0.1


# ── Тесты raycast_to_ways ─────────────────────────────────────────

def test_raycast_simple_cross():
    """
    Простой перекрёсток "крест":
      - Север-юг: [(0.001, 0.0), (0.0, 0.0), (-0.001, 0.0)]
      - Запад-восток: [(0.0, -0.001), (0.0, 0.0), (0.0, 0.001)]
    
    Машина в (0.0005, 0.0), курс на север (0°), знак чуть левее.
    Луч на 350° должен пересечь западное ребро.
    """
    ways = [
        {
            "id": "way_north_south",
            "name": "Северная улица",
            "nodes": [(0.001, 0.0), (0.0, 0.0), (-0.001, 0.0)],
            "tags": {},
        },
        {
            "id": "way_west_east",
            "name": "Западная улица",
            "nodes": [(0.0, -0.001), (0.0, 0.0), (0.0, 0.001)],
            "tags": {},
        },
    ]
    
    hit = raycast_to_ways(
        origin_lat=0.0005,
        origin_lon=0.0,
        bearing_deg=350.0,  # почти на север, чуть влево
        ways=ways,
        max_distance_m=100.0,
    )
    
    assert hit is not None
    # Должен пересечь западное ребро (way_west_east)
    assert hit.way_name == "Западная улица"
    assert hit.distance_m < 100.0


def test_raycast_t_intersection():
    """
    T-образный перекрёсток (только 3 стороны):
      - Север: [(0.001, 0.0), (0.0, 0.0)]
      - Запад: [(0.0, -0.001), (0.0, 0.0)]
      - Восток: [(0.0, 0.0), (0.0, 0.001)]
    
    Машина едет с юга (из -0.001, 0.0) на север (курс 0°).
    Знак справа → bearing ~90° → должен попасть в восточное ребро.
    """
    ways = [
        {
            "id": "way_north",
            "name": "Север",
            "nodes": [(0.001, 0.0), (0.0, 0.0)],
            "tags": {},
        },
        {
            "id": "way_west",
            "name": "Запад",
            "nodes": [(0.0, -0.001), (0.0, 0.0)],
            "tags": {},
        },
        {
            "id": "way_east",
            "name": "Восток",
            "nodes": [(0.0, 0.0), (0.0, 0.001)],
            "tags": {},
        },
    ]
    
    hit = raycast_to_ways(
        origin_lat=-0.0005,
        origin_lon=0.0,
        bearing_deg=90.0,  # на восток
        ways=ways,
        max_distance_m=100.0,
    )
    
    assert hit is not None
    assert hit.way_name == "Восток"


def test_raycast_roundabout_exclusion():
    """
    Кольцо должно игнорироваться при exclude_roundabout=True.
    Луч проходит сквозь кольцо и попадает в выходящую дорогу.
    """
    ways = [
        {
            "id": "roundabout",
            "name": "Круговое движение",
            "nodes": [
                (0.0001, -0.0001),
                (0.0001, 0.0001),
                (-0.0001, 0.0001),
                (-0.0001, -0.0001),
                (0.0001, -0.0001),  # замкнутое кольцо
            ],
            "tags": {"junction": "roundabout"},
        },
        {
            "id": "exit_road",
            "name": "Выезд",
            "nodes": [(0.0, 0.0), (0.001, 0.0)],  # дорога на север
            "tags": {},
        },
    ]
    
    hit = raycast_to_ways(
        origin_lat=-0.0005,
        origin_lon=0.0,
        bearing_deg=0.0,  # на север
        ways=ways,
        max_distance_m=200.0,
        exclude_roundabout=True,
    )
    
    assert hit is not None
    assert hit.way_name == "Выезд"
    assert hit.way_id != "roundabout"


def test_raycast_no_intersection():
    """Луч не пересекает ни один way → None."""
    ways = [
        {
            "id": "far_way",
            "name": "Далёкая дорога",
            "nodes": [(1.0, 1.0), (1.0, 1.001)],
            "tags": {},
        },
    ]
    
    hit = raycast_to_ways(
        origin_lat=0.0,
        origin_lon=0.0,
        bearing_deg=0.0,
        ways=ways,
        max_distance_m=50.0,
    )
    
    assert hit is None


def test_raycast_max_distance():
    """Пересечение есть, но дальше max_distance_m → None."""
    ways = [
        {
            "id": "way_far",
            "name": "Дорога",
            # Примерно 200м на север (0.002° ≈ 222м)
            "nodes": [(0.002, 0.0), (0.003, 0.0)],
            "tags": {},
        },
    ]
    
    hit = raycast_to_ways(
        origin_lat=0.0,
        origin_lon=0.0,
        bearing_deg=0.0,  # на север
        ways=ways,
        max_distance_m=100.0,  # слишком коротко
    )
    
    assert hit is None


# ── Тесты aggregate_observations ──────────────────────────────────

def test_aggregate_observations_single():
    """Одно наблюдение → consistency = 1.0."""
    hits = [
        WayHit(
            way_id="way1",
            way_name="Улица 1",
            intersection_lat=0.0,
            intersection_lon=0.0,
            distance_m=10.0,
            angle_diff_deg=5.0,
            way_azimuth=90.0,
        ),
    ]
    
    way_id, consistency, representative = aggregate_observations(hits)
    
    assert way_id == "way1"
    assert consistency == 1.0
    assert representative.way_id == "way1"


def test_aggregate_observations_multiple_same():
    """Все наблюдения одного way → consistency = 1.0."""
    hits = [
        WayHit("way1", "Улица 1", 0.0, 0.0, 10.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 11.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 12.0, 5.0, 90.0),
    ]
    
    way_id, consistency, representative = aggregate_observations(hits)
    
    assert way_id == "way1"
    assert consistency == 1.0
    assert representative.distance_m == 11.0  # медианный


def test_aggregate_observations_mixed():
    """7 из 10 наблюдений → way1, consistency = 0.7."""
    hits = [
        WayHit("way1", "Улица 1", 0.0, 0.0, 10.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 11.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 12.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 13.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 14.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 15.0, 5.0, 90.0),
        WayHit("way1", "Улица 1", 0.0, 0.0, 16.0, 5.0, 90.0),
        WayHit("way2", "Улица 2", 0.0, 0.0, 20.0, 15.0, 180.0),
        WayHit("way2", "Улица 2", 0.0, 0.0, 21.0, 15.0, 180.0),
        WayHit("way3", "Улица 3", 0.0, 0.0, 30.0, 25.0, 270.0),
    ]
    
    way_id, consistency, representative = aggregate_observations(hits)
    
    assert way_id == "way1"
    assert abs(consistency - 0.7) < 0.01
    assert representative.way_id == "way1"
    assert representative.distance_m == 13.0  # медианный из 7


def test_aggregate_observations_empty():
    """Пустой список → None."""
    way_id, consistency, representative = aggregate_observations([])
    
    assert way_id is None
    assert consistency == 0.0
    assert representative is None


# ── Интеграционный тест: полный пайплайн ──────────────────────────

def test_full_pipeline_cross_intersection():
    """
    Полный пайплайн:
      1. Машина едет на север (курс 0°) в точке (53.9, 27.56)
      2. Знак справа в кадре (bbox_center_x = 1440 из 1920)
      3. Перекрёсток "крест" с 4 дорогами
      4. Bearing → 30° (на северо-восток)
      5. Raycast должен попасть в восточную дорогу
    """
    # Синтетический перекрёсток (примерные координаты Минска)
    center_lat, center_lon = 53.9, 27.56
    offset = 0.0005  # ~55м
    
    ways = [
        {
            "id": "north",
            "name": "Северная",
            "nodes": [(center_lat, center_lon), (center_lat + offset, center_lon)],
            "tags": {},
        },
        {
            "id": "south",
            "name": "Южная",
            "nodes": [(center_lat, center_lon), (center_lat - offset, center_lon)],
            "tags": {},
        },
        {
            "id": "east",
            "name": "Восточная",
            "nodes": [(center_lat, center_lon), (center_lat, center_lon + offset)],
            "tags": {},
        },
        {
            "id": "west",
            "name": "Западная",
            "nodes": [(center_lat, center_lon), (center_lat, center_lon - offset)],
            "tags": {},
        },
    ]
    
    # Машина чуть южнее перекрёстка, едет на север
    car_lat, car_lon = center_lat - 0.0002, center_lon
    
    # Вычисляем bearing на знак
    bearing = compute_sign_bearing(
        gpx_azimuth=0.0,    # на север
        bbox_center_x=1440, # справа в кадре
        frame_width=1920,
        hfov_deg=120.0,
    )
    
    # Должно быть ~30° (северо-восток)
    assert 25.0 < bearing < 35.0
    
    # Raycast
    hit = raycast_to_ways(
        origin_lat=car_lat,
        origin_lon=car_lon,
        bearing_deg=bearing,
        ways=ways,
        max_distance_m=100.0,
    )
    
    assert hit is not None
    assert hit.way_name == "Восточная"
    assert hit.distance_m < 50.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
