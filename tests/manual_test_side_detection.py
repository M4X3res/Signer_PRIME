"""
tests/manual_test_side_detection.py
Manual test for geometric side detection (without pytest).
"""
import sys
sys.path.insert(0, '.')

from core.osm_snap import OSMSnapper


def test_side_determination_north_south():
    """Test: north to south way."""
    print("\n=== Test 1: North to South road (way p1 to p2) ===")
    snapper = OSMSnapper()
    
    synthetic_ways = [{
        "name": "Test Road",
        "nodes": [
            (53.910, 27.560),  # p1 (north)
            (53.900, 27.560),  # p2 (south)
        ],
        "lanes": 2,
        "width": 7.0,
    }]
    
    # Sign on the east - RIGHT of way direction p1->p2 (south)
    # But in geographic sense: east is on the left when looking TOWARDS p1 from p2
    # Cross product: v1=(0, -1), v2=(+1, -0.5)
    # cross = 0*(-0.5) - (-1)*(+1) = +1 > 0 => LEFT of way direction
    sign_east = (53.905, 27.565)
    result_east = snapper._find_closest_segment(
        sign_east[0], sign_east[1], synthetic_ways
    )
    side_east = result_east[7] if result_east else None
    print(f"Sign east of road: side={side_east}")
    print(f"  Way direction: north->south (v1 points south)")
    print(f"  Expected: True (east is LEFT when looking towards south)")
    assert side_east == True, "ERROR: East sign should be True (left of way direction)"
    
    # Sign on the west - LEFT of way direction p1->p2 (south)
    # Cross product gives negative => RIGHT
    sign_west = (53.905, 27.555)
    result_west = snapper._find_closest_segment(
        sign_west[0], sign_west[1], synthetic_ways
    )
    side_west = result_west[7] if result_west else None
    print(f"Sign west of road: side={side_west}")
    print(f"  Expected: False (west is RIGHT when looking towards south)")
    assert side_west == False, "ERROR: West sign should be False (right of way direction)"
    
    print("Test 1 PASSED")


def test_side_determination_east_west():
    """Test: west to east way."""
    print("\n=== Test 2: West to East road (way p1 to p2) ===")
    snapper = OSMSnapper()
    
    synthetic_ways = [{
        "name": "East-West Road",
        "nodes": [
            (53.905, 27.550),  # p1 (west)
            (53.905, 27.570),  # p2 (east)
        ],
        "lanes": 2,
        "width": 7.0,
    }]
    
    # Sign north = LEFT when way goes east (p1->p2)
    sign_north = (53.910, 27.560)
    result_north = snapper._find_closest_segment(
        sign_north[0], sign_north[1], synthetic_ways
    )
    side_north = result_north[7] if result_north else None
    print(f"Sign north: side={side_north}, expected True")
    assert side_north == True, "ERROR: North sign should be True (left)"
    
    # Sign south = RIGHT when way goes east (p1->p2)
    sign_south = (53.900, 27.560)
    result_south = snapper._find_closest_segment(
        sign_south[0], sign_south[1], synthetic_ways
    )
    side_south = result_south[7] if result_south else None
    print(f"Sign south: side={side_south}, expected False")
    assert side_south == False, "ERROR: South sign should be False (right)"
    
    print("Test 2 PASSED")


def test_side_determination_diagonal():
    """Test: diagonal way (northwest to southeast)."""
    print("\n=== Test 3: Diagonal NW to SE (way p1 to p2) ===")
    snapper = OSMSnapper()
    
    synthetic_ways = [{
        "name": "Diagonal Road",
        "nodes": [
            (53.910, 27.550),  # p1 (northwest)
            (53.900, 27.570),  # p2 (southeast)
        ],
        "lanes": 2,
        "width": 7.0,
    }]
    
    # Sign northeast of diagonal
    # Way goes southeast, NE point is... let's calculate:
    # v1 = (+0.020, -0.010) (SE direction)
    # v2_ne = (+0.015, +0.002) (NE of p1)
    # cross = (+0.020)*(+0.002) - (-0.010)*(+0.015)
    #       = +0.00004 + 0.00015 = +0.00019 > 0 => LEFT
    sign_ne = (53.912, 27.565)
    result_ne = snapper._find_closest_segment(
        sign_ne[0], sign_ne[1], synthetic_ways
    )
    side_ne = result_ne[7] if result_ne else None
    print(f"Sign NE of diagonal: side={side_ne}, expected True (left of SE direction)")
    assert side_ne == True, "ERROR: NE sign should be True (left)"
    
    # Sign southwest of diagonal
    # v2_sw = (-0.005, -0.012) (SW of p1)
    # cross = (+0.020)*(-0.012) - (-0.010)*(-0.005)
    #       = -0.00024 - 0.00005 = -0.00029 < 0 => RIGHT
    sign_sw = (53.898, 27.545)
    result_sw = snapper._find_closest_segment(
        sign_sw[0], sign_sw[1], synthetic_ways
    )
    side_sw = result_sw[7] if result_sw else None
    print(f"Sign SW of diagonal: side={side_sw}, expected False (right of SE direction)")
    assert side_sw == False, "ERROR: SW sign should be False (right)"
    
    print("Test 3 PASSED")


if __name__ == "__main__":
    try:
        test_side_determination_north_south()
        test_side_determination_east_west()
        test_side_determination_diagonal()
        print("\n" + "="*50)
        print("ALL GEOMETRIC SIDE DETECTION TESTS PASSED")
        print("="*50)
    except AssertionError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
