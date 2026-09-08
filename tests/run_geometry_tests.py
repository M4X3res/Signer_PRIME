"""
tests/run_geometry_tests.py
Простой runner для тестов без pytest.
"""
import sys
sys.path.insert(0, '.')

from core.intersection_geometry import (
    compute_sign_bearing,
    raycast_to_ways,
    aggregate_observations,
    WayHit,
)


def test_compute_sign_bearing_center():
    """Знак в центре кадра → bearing = gpx_azimuth."""
    result = compute_sign_bearing(
        gpx_azimuth=90.0,
        bbox_center_x=960,
        frame_width=1920,
        hfov_deg=120.0,
    )
    assert abs(result - 90.0) < 0.1, f"Expected 90.0, got {result}"
    print("[OK] test_compute_sign_bearing_center")


def test_compute_sign_bearing_right():
    """Знак справа от центра → bearing > gpx_azimuth."""
    result = compute_sign_bearing(
        gpx_azimuth=90.0,
        bbox_center_x=1440,
        frame_width=1920,
        hfov_deg=120.0,
    )
    assert abs(result - 120.0) < 0.1, f"Expected 120.0, got {result}"
    print("[OK] test_compute_sign_bearing_right")


def test_compute_sign_bearing_left():
    """Знак слева от центра → bearing < gpx_azimuth."""
    result = compute_sign_bearing(
        gpx_azimuth=90.0,
        bbox_center_x=480,
        frame_width=1920,
        hfov_deg=120.0,
    )
    assert abs(result - 60.0) < 0.1, f"Expected 60.0, got {result}"
    print("[OK] test_compute_sign_bearing_left")


def test_raycast_simple_cross():
    """Простой перекрёсток крест."""
    # Тестируем что raycast вообще находит пересечения
    ways = [
        {
            "id": "way1",
            "name": "Road1",
            "nodes": [(0.001, 0.0), (0.0, 0.0), (-0.001, 0.0)],
            "tags": {},
        },
    ]
    
    hit = raycast_to_ways(
        origin_lat=0.0005,
        origin_lon=0.0,
        bearing_deg=0.0,  # прямо на север
        ways=ways,
        max_distance_m=100.0,
    )
    
    assert hit is not None, "Expected hit, got None"
    print(f"[OK] test_raycast_simple_cross (hit distance={hit.distance_m:.1f}m)")


def test_raycast_t_intersection():
    """T-образный перекрёсток."""
    ways = [
        {"id": "way1", "name": "Road", "nodes": [(0.001, 0.0), (0.0, 0.0), (-0.001, 0.0)], "tags": {}},
    ]
    
    hit = raycast_to_ways(
        origin_lat=0.0005,
        origin_lon=0.0,
        bearing_deg=0.0,
        ways=ways,
        max_distance_m=100.0,
    )
    
    assert hit is not None
    print("[OK] test_raycast_t_intersection")


def test_aggregate_single():
    """Одно наблюдение → consistency = 1.0."""
    hits = [
        WayHit("way1", "Улица 1", 0.0, 0.0, 10.0, 5.0, 90.0),
    ]
    
    way_id, consistency, representative = aggregate_observations(hits)
    
    assert way_id == "way1"
    assert consistency == 1.0
    assert representative.way_id == "way1"
    print("[OK] test_aggregate_single")


def test_aggregate_mixed():
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
    print("[OK] test_aggregate_mixed")


if __name__ == "__main__":
    print("Running intersection_geometry tests...")
    try:
        test_compute_sign_bearing_center()
        test_compute_sign_bearing_right()
        test_compute_sign_bearing_left()
        test_raycast_simple_cross()
        test_raycast_t_intersection()
        test_aggregate_single()
        test_aggregate_mixed()
        print("\n[SUCCESS] All tests passed!")
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
