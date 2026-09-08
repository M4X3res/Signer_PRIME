"""
Manual test for Block I (Steps I.2-I.3) without pytest.
Tests post-snap deduplication and sorting by distance.
"""
import sys
sys.path.insert(0, '.')

def test_merge_duplicates_same_way():
    """Test I.2: Signs on same road with similar distance_m should merge."""
    print("\n=== Test I.2.1: Merge duplicates on same road ===")
    
    from core.final_handler import FinalHandler
    from core.sign import TrackedSign
    from core.osm_snap import SnapResult
    from configs.settings import AppSettings
    
    handler = FinalHandler()
    settings = AppSettings()
    
    # Two signs with different coordinates (6m apart)
    sign1 = TrackedSign()
    sign1.cnn_results = ["1.1", "1.1", "1.1"]
    sign1.car_x = [100.0, 101.0, 102.0]
    sign1.car_y = [200.0, 201.0, 202.0]
    sign1.abs_frame_numbers = [10, 11, 12]
    
    sign2 = TrackedSign()
    sign2.cnn_results = ["1.1", "1.1"]
    sign2.car_x = [108.0, 109.0]
    sign2.car_y = [208.0, 209.0]
    sign2.abs_frame_numbers = [15, 16]
    
    # Mock snap results: both on same road, similar distance_m
    snap1 = SnapResult(
        lat=53.905, lon=27.560, azimuth=90.0,
        distance_m=5.0, road_name="Test Road",
        lanes=2, width=7.0, snapped=True,
        side_relative_to_way=True
    )
    snap2 = SnapResult(
        lat=53.905, lon=27.561, azimuth=90.0,
        distance_m=5.5, road_name="Test Road",
        lanes=2, width=7.0, snapped=True,
        side_relative_to_way=True
    )
    
    is_dup = handler._are_duplicates_post_snap(sign1, sign2, snap1, snap2, settings)
    print(f"Are duplicates: {is_dup}, expected True")
    assert is_dup == True, "Signs on same road with similar distance_m should be duplicates"
    
    merged_signs, merged_snaps = handler._merge_duplicates_post_snap(
        [sign1, sign2], [snap1, snap2], settings
    )
    print(f"Merged count: {len(merged_signs)}, expected 1")
    assert len(merged_signs) == 1, "Two duplicates should merge into one"
    
    obs_count = len(merged_signs[0].cnn_results)
    print(f"CNN results count: {obs_count}, expected 5")
    assert obs_count == 5, "CNN results count should be sum (3+2=5)"
    
    print("Test I.2.1 PASSED")


def test_no_merge_different_roads():
    """Test I.2: Signs on different roads should NOT merge."""
    print("\n=== Test I.2.2: No merge on different roads ===")
    
    from core.final_handler import FinalHandler
    from core.sign import TrackedSign
    from core.osm_snap import SnapResult
    from configs.settings import AppSettings
    
    handler = FinalHandler()
    settings = AppSettings()
    
    sign1 = TrackedSign()
    sign1.cnn_results = ["1.1", "1.1", "1.1"]
    sign1.car_x = [100.0]
    sign1.car_y = [200.0]
    
    sign2 = TrackedSign()
    sign2.cnn_results = ["1.1", "1.1"]
    sign2.car_x = [105.0]
    sign2.car_y = [205.0]
    
    snap1 = SnapResult(
        lat=53.905, lon=27.560, azimuth=90.0,
        distance_m=5.0, road_name="Street A",
        snapped=True, side_relative_to_way=True
    )
    snap2 = SnapResult(
        lat=53.906, lon=27.561, azimuth=90.0,
        distance_m=5.2, road_name="Street B",
        snapped=True, side_relative_to_way=True
    )
    
    is_dup = handler._are_duplicates_post_snap(sign1, sign2, snap1, snap2, settings)
    print(f"Are duplicates: {is_dup}, expected False")
    assert is_dup == False, "Signs on different roads should NOT be duplicates"
    
    print("Test I.2.2 PASSED")


def test_coefficient_ordered_by_distance():
    """Test I.3: Signs should be sorted by distance_m (ascending)."""
    print("\n=== Test I.3.1: Sorting by distance_m ===")
    
    from core.final_handler import FinalHandler
    from core.sign import TrackedSign
    from core.osm_snap import SnapResult
    
    handler = FinalHandler()
    
    sign1 = TrackedSign()
    sign1.car_x = [100.0]
    sign1.car_y = [200.0]
    sign1.cnn_results = ["1.1"]
    
    sign2 = TrackedSign()
    sign2.car_x = [102.0]
    sign2.car_y = [201.0]
    sign2.cnn_results = ["1.2"]
    
    sign3 = TrackedSign()
    sign3.car_x = [101.0]
    sign3.car_y = [199.0]
    sign3.cnn_results = ["1.3"]
    
    # Snap results with different distance_m (not in ascending order)
    snap1 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=12.0, snapped=True)
    snap2 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=5.0, snapped=True)
    snap3 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=20.0, snapped=True)
    
    sign_to_snap = {
        id(sign1): snap1,
        id(sign2): snap2,
        id(sign3): snap3,
    }
    
    sorted_signs = handler._sort_signs_by_distance([sign1, sign2, sign3], sign_to_snap)
    
    print(f"Sorted order: sign2 (5m), sign1 (12m), sign3 (20m)")
    print(f"Actual: {sorted_signs[0].best_cnn}, {sorted_signs[1].best_cnn}, {sorted_signs[2].best_cnn}")
    
    assert sorted_signs[0] is sign2, "Sign with distance_m=5 should be first"
    assert sorted_signs[1] is sign1, "Sign with distance_m=12 should be second"
    assert sorted_signs[2] is sign3, "Sign with distance_m=20 should be third"
    
    print("Test I.3.1 PASSED")


def test_signs_without_snap_go_last():
    """Test I.3: Signs without successful snap should go last."""
    print("\n=== Test I.3.2: Signs without snap go last ===")
    
    from core.final_handler import FinalHandler
    from core.sign import TrackedSign
    from core.osm_snap import SnapResult
    
    handler = FinalHandler()
    
    sign1 = TrackedSign()
    sign1.car_x = [100.0]
    sign1.car_y = [200.0]
    sign1.cnn_results = ["1.1"]
    
    sign2 = TrackedSign()
    sign2.car_x = [101.0]
    sign2.car_y = [201.0]
    sign2.cnn_results = ["1.2"]
    
    snap1 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=10.0, snapped=True)
    snap2 = SnapResult(lat=53.9, lon=27.5, azimuth=0, snapped=False)
    
    sign_to_snap = {id(sign1): snap1, id(sign2): snap2}
    
    sorted_signs = handler._sort_signs_by_distance([sign2, sign1], sign_to_snap)
    
    print(f"First sign has snap: {sign_to_snap[id(sorted_signs[0])].snapped}")
    print(f"Second sign has snap: {sign_to_snap[id(sorted_signs[1])].snapped}")
    
    assert sorted_signs[0] is sign1, "Sign with successful snap should be first"
    assert sorted_signs[1] is sign2, "Sign without snap should be last"
    
    print("Test I.3.2 PASSED")


if __name__ == "__main__":
    try:
        test_merge_duplicates_same_way()
        test_no_merge_different_roads()
        test_coefficient_ordered_by_distance()
        test_signs_without_snap_go_last()
        
        print("\n" + "="*60)
        print("ALL BLOCK I TESTS (I.2-I.3) PASSED")
        print("="*60)
    except AssertionError as e:
        print(f"\nERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
