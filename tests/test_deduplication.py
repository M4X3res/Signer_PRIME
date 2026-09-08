"""
tests/test_deduplication.py
Тесты для дедупликации знаков и геометрического определения стороны (BLOCK I).
"""
import pytest
from core.osm_snap import OSMSnapper, SnapResult
from core.sign import TrackedSign
from core.final_handler import FinalHandler
from configs.settings import AppSettings


class TestGeometricSideDetermination:
    """Тесты геометрического определения стороны знака (Шаг I.1)."""
    
    def test_side_determination_simple_north_south_road(self):
        """
        Синтетический way (прямая линия север→юг), знак справа/слева.
        Проверяем что side_relative_to_way корректно определяется.
        """
        snapper = OSMSnapper()
        
        # Создаём синтетический way: север→юг (lat уменьшается)
        # p1 = (53.910, 27.560) — север
        # p2 = (53.900, 27.560) — юг
        # Направление движения way: 180° (строго на юг)
        
        synthetic_ways = [{
            "name": "Test Road",
            "nodes": [
                (53.910, 27.560),  # p1 (север)
                (53.900, 27.560),  # p2 (юг)
            ],
            "lanes": 2,
            "width": 7.0,
        }]
        
        # Знак справа от направления way (восток от линии)
        sign_right = (53.905, 27.565)  # lon > 27.560 = восточнее = справа при движении на юг
        result_right = snapper._find_closest_segment(
            sign_right[0], sign_right[1], synthetic_ways
        )
        assert result_right is not None
        side_right = result_right[7]  # 8-й элемент tuple
        assert side_right == False, "Знак восточнее линии должен быть справа (False) при движении на юг"
        
        # Знак слева от направления way (запад от линии)
        sign_left = (53.905, 27.555)  # lon < 27.560 = западнее = слева при движении на юг
        result_left = snapper._find_closest_segment(
            sign_left[0], sign_left[1], synthetic_ways
        )
        assert result_left is not None
        side_left = result_left[7]
        assert side_left == True, "Знак западнее линии должен быть слева (True) при движении на юг"
    
    def test_side_determination_east_west_road(self):
        """
        Way направлен с запада на восток (lon увеличивается).
        """
        snapper = OSMSnapper()
        
        # Создаём синтетический way: запад→восток (lon увеличивается, lat постоянна)
        # p1 = (53.905, 27.550) — запад
        # p2 = (53.905, 27.570) — восток
        # Направление движения way: 90° (строго на восток)
        
        synthetic_ways = [{
            "name": "East-West Road",
            "nodes": [
                (53.905, 27.550),  # p1 (запад)
                (53.905, 27.570),  # p2 (восток)
            ],
            "lanes": 2,
            "width": 7.0,
        }]
        
        # Знак севернее линии = слева при движении на восток
        sign_north = (53.910, 27.560)  # lat > 53.905
        result_north = snapper._find_closest_segment(
            sign_north[0], sign_north[1], synthetic_ways
        )
        assert result_north is not None
        side_north = result_north[7]
        assert side_north == True, "Знак севернее линии должен быть слева (True) при движении на восток"
        
        # Знак южнее линии = справа при движении на восток
        sign_south = (53.900, 27.560)  # lat < 53.905
        result_south = snapper._find_closest_segment(
            sign_south[0], sign_south[1], synthetic_ways
        )
        assert result_south is not None
        side_south = result_south[7]
        assert side_south == False, "Знак южнее линии должен быть справа (False) при движении на восток"
    
    def test_side_determination_diagonal_road(self):
        """
        Way под углом (северо-запад → юго-восток).
        """
        snapper = OSMSnapper()
        
        # Диагональ: северо-запад → юго-восток
        synthetic_ways = [{
            "name": "Diagonal Road",
            "nodes": [
                (53.910, 27.550),  # p1 (северо-запад)
                (53.900, 27.570),  # p2 (юго-восток)
            ],
            "lanes": 2,
            "width": 7.0,
        }]
        
        # Знак северо-восточнее диагонали = справа при движении на юго-восток
        sign_ne = (53.912, 27.565)
        result_ne = snapper._find_closest_segment(
            sign_ne[0], sign_ne[1], synthetic_ways
        )
        assert result_ne is not None
        side_ne = result_ne[7]
        assert side_ne == False, "Знак северо-восточнее диагонали должен быть справа"
        
        # Знак юго-западнее диагонали = слева при движении на юго-восток
        sign_sw = (53.898, 27.545)
        result_sw = snapper._find_closest_segment(
            sign_sw[0], sign_sw[1], synthetic_ways
        )
        assert result_sw is not None
        side_sw = result_sw[7]
        assert side_sw == True, "Знак юго-западнее диагонали должен быть слева"


class TestDuplicateDetection:
    """Тесты второго прохода мержа дублей ПОСЛЕ snap (Шаг I.2)."""
    
    def test_merge_duplicates_same_way_close_distance(self):
        """
        Два TrackedSign одного типа, координаты различаются на 6м (за порогом pre-snap),
        но после snap оказываются на одном way с похожим distance_m → должны смержиться.
        """
        from core.final_handler import FinalHandler
        from core.sign import TrackedSign
        from core.osm_snap import SnapResult
        from configs.settings import AppSettings
        
        handler = FinalHandler()
        settings = AppSettings()
        
        # Создаём два знака с различающимися координатами (6м в EPSG:32635)
        sign1 = TrackedSign()
        sign1.cnn_results = ["1.1", "1.1", "1.1"]  # best_cnn = "1.1"
        sign1.car_x = [100.0, 101.0, 102.0]
        sign1.car_y = [200.0, 201.0, 202.0]
        sign1.abs_frame_numbers = [10, 11, 12]
        
        sign2 = TrackedSign()
        sign2.cnn_results = ["1.1", "1.1"]  # тот же best_cnn
        sign2.car_x = [108.0, 109.0]  # на 6-7м дальше
        sign2.car_y = [208.0, 209.0]
        sign2.abs_frame_numbers = [15, 16]
        
        # Замокированные snap результаты: оба на одной дороге, похожее distance_m
        snap1 = SnapResult(
            lat=53.905, lon=27.560, azimuth=90.0,
            distance_m=5.0, road_name="Test Road",
            lanes=2, width=7.0, snapped=True,
            side_relative_to_way=True
        )
        snap2 = SnapResult(
            lat=53.905, lon=27.561, azimuth=90.0,
            distance_m=5.5, road_name="Test Road",  # та же дорога
            lanes=2, width=7.0, snapped=True,
            side_relative_to_way=True
        )
        
        # Проверяем что они считаются дубликатами в post-snap проходе
        is_dup = handler._are_duplicates_post_snap(sign1, sign2, snap1, snap2, settings)
        assert is_dup == True, "Знаки на одной дороге с похожим distance_m должны быть дубликатами"
        
        # Проверяем мерж
        merged_signs, merged_snaps = handler._merge_duplicates_post_snap(
            [sign1, sign2], [snap1, snap2], settings
        )
        assert len(merged_signs) == 1, "Два дубликата должны смержиться в один"
        assert merged_signs[0].observation_count == 5, "Observation count должен быть суммой (3+2=5)"
    
    def test_no_merge_different_roads(self):
        """
        Два знака одного типа, но на разных дорогах (разные road_name) → НЕ должны смержиться.
        """
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
            distance_m=5.2, road_name="Street B",  # ДРУГАЯ дорога
            snapped=True, side_relative_to_way=True
        )
        
        is_dup = handler._are_duplicates_post_snap(sign1, sign2, snap1, snap2, settings)
        assert is_dup == False, "Знаки на разных дорогах НЕ должны быть дубликатами"
    
    def test_no_merge_large_distance_diff(self):
        """
        Два знака на одной дороге, но с большой разницей в distance_m (5м vs 15м) → НЕ должны смержиться.
        """
        from core.final_handler import FinalHandler
        from core.sign import TrackedSign
        from core.osm_snap import SnapResult
        from configs.settings import AppSettings
        
        handler = FinalHandler()
        settings = AppSettings()
        
        sign1 = TrackedSign()
        sign1.cnn_results = ["1.1", "1.1"]
        sign1.car_x = [100.0]
        sign1.car_y = [200.0]
        
        sign2 = TrackedSign()
        sign2.cnn_results = ["1.1", "1.1"]
        sign2.car_x = [105.0]
        sign2.car_y = [205.0]
        
        snap1 = SnapResult(
            lat=53.905, lon=27.560, azimuth=90.0,
            distance_m=5.0, road_name="Test Road",
            snapped=True, side_relative_to_way=True
        )
        snap2 = SnapResult(
            lat=53.905, lon=27.561, azimuth=90.0,
            distance_m=15.0, road_name="Test Road",  # БОЛЬШАЯ разница
            snapped=True, side_relative_to_way=False
        )
        
        is_dup = handler._are_duplicates_post_snap(sign1, sign2, snap1, snap2, settings)
        assert is_dup == False, "Знаки с большой разницей distance_m НЕ должны быть дубликатами"


class TestCoefficientSorting:
    """Тесты сортировки знаков внутри группы по cross-track расстоянию (Шаг I.3)."""
    
    def test_coefficient_ordered_by_distance(self):
        """
        3 синтетических TrackedSign с одинаковым положением, но разными snap_result.distance_m
        (5м, 12м, 20м) → проверить, что итоговый порядок coefficient соответствует возрастанию расстояния.
        """
        from core.final_handler import FinalHandler
        from core.sign import TrackedSign
        from core.osm_snap import SnapResult
        
        handler = FinalHandler()
        
        # Три знака в одной позиции
        sign1 = TrackedSign()
        sign1.car_x = [100.0]
        sign1.car_y = [200.0]
        sign1.cnn_results = ["1.1"]
        
        sign2 = TrackedSign()
        sign2.car_x = [102.0]  # близко к sign1 (округлится к той же группе)
        sign2.car_y = [201.0]
        sign2.cnn_results = ["1.2"]
        
        sign3 = TrackedSign()
        sign3.car_x = [101.0]
        sign3.car_y = [199.0]
        sign3.cnn_results = ["1.3"]
        
        # Snap результаты с разными distance_m (не в порядке возрастания!)
        snap1 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=12.0, snapped=True)
        snap2 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=5.0, snapped=True)   # БЛИЖЕ
        snap3 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=20.0, snapped=True)  # ДАЛЬШЕ
        
        sign_to_snap = {
            id(sign1): snap1,
            id(sign2): snap2,
            id(sign3): snap3,
        }
        
        # Сортируем
        sorted_signs = handler._sort_signs_by_distance([sign1, sign2, sign3], sign_to_snap)
        
        # Проверяем порядок: sign2 (5м), sign1 (12м), sign3 (20м)
        assert sorted_signs[0] is sign2, "Знак с distance_m=5 должен быть первым"
        assert sorted_signs[1] is sign1, "Знак с distance_m=12 должен быть вторым"
        assert sorted_signs[2] is sign3, "Знак с distance_m=20 должен быть третьим"
    
    def test_signs_without_snap_go_last(self):
        """
        Знаки с неудавшимся snap должны идти в конец списка (после всех успешных snap).
        """
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
        
        # sign1 с успешным snap, sign2 без snap
        snap1 = SnapResult(lat=53.9, lon=27.5, azimuth=90, distance_m=10.0, snapped=True)
        snap2 = SnapResult(lat=53.9, lon=27.5, azimuth=0, snapped=False)  # Snap не удался
        
        sign_to_snap = {id(sign1): snap1, id(sign2): snap2}
        
        sorted_signs = handler._sort_signs_by_distance([sign2, sign1], sign_to_snap)
        
        assert sorted_signs[0] is sign1, "Знак с успешным snap должен быть первым"
        assert sorted_signs[1] is sign2, "Знак без snap должен быть вторым (последним)"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])


class TestDeduplicationLargeRadius:
    """Тесты дедупликации с большими радиусами (BLOCK N.1)."""
    
    def test_dedup_large_radius_150m(self):
        """
        Два фичи на расстоянии 150м при dedup_radius_final_m=200 должны мержиться.
        """
        from core.final_handler import FinalHandler
        from configs.settings import AppSettings
        from geojson import Feature, LineString
        
        settings = AppSettings()
        settings.dedup_radius_final_m = 200.0  # Большой радиус
        settings.dedup_azimuth_deg = 45.0
        
        handler = FinalHandler(settings)
        
        # Два фичи одного типа, одной стороны, на расстоянии ~150м
        # Используем синтетические координаты: расстояние по широте ~150м
        # (1 градус широты ≈ 111 км, 150м ≈ 0.00135°)
        feat1 = Feature(
            geometry=LineString([
                [27.560, 53.905],
                [27.561, 53.906]
            ]),
            properties={
                "type": "1.1",
                "left": "right",
                "azimuth": 90.0,
                "length": 10,
            }
        )
        
        feat2 = Feature(
            geometry=LineString([
                [27.560, 53.9064],  # ~150м севернее feat1
                [27.561, 53.9074]
            ]),
            properties={
                "type": "1.1",
                "left": "right",
                "azimuth": 92.0,  # в пределах 45° от feat1
                "length": 8,
            }
        )
        
        # Дедуплицируем
        result = handler._deduplicate([feat1, feat2])
        
        # При радиусе 200м должны смержиться (остаться 1 фича)
        assert len(result) == 1, (
            f"При dedup_radius_final_m=200м два фичи на расстоянии ~150м "
            f"должны смержиться, но получено {len(result)} фич"
        )
    
    def test_dedup_small_radius_150m(self):
        """
        Те же два фичи на расстоянии 150м при dedup_radius_final_m=20 НЕ должны мержиться.
        """
        from core.final_handler import FinalHandler
        from configs.settings import AppSettings
        from geojson import Feature, LineString
        
        settings = AppSettings()
        settings.dedup_radius_final_m = 20.0  # Дефолтный малый радиус
        settings.dedup_azimuth_deg = 45.0
        
        handler = FinalHandler(settings)
        
        feat1 = Feature(
            geometry=LineString([
                [27.560, 53.905],
                [27.561, 53.906]
            ]),
            properties={
                "type": "1.1",
                "left": "right",
                "azimuth": 90.0,
                "length": 10,
            }
        )
        
        feat2 = Feature(
            geometry=LineString([
                [27.560, 53.9064],  # ~150м севернее feat1
                [27.561, 53.9074]
            ]),
            properties={
                "type": "1.1",
                "left": "right",
                "azimuth": 92.0,
                "length": 8,
            }
        )
        
        # Дедуплицируем
        result = handler._deduplicate([feat1, feat2])
        
        # При радиусе 20м НЕ должны смержиться (остаться 2 фичи)
        assert len(result) == 2, (
            f"При dedup_radius_final_m=20м два фичи на расстоянии ~150м "
            f"НЕ должны смержиться, но получено {len(result)} фич"
        )
