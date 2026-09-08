"""
Тесты для TrackedSign.calc_confidence()
Проверяют расчет метрик уверенности распознавания.
"""
import pytest
from core.sign import TrackedSign


class TestCalcConfidence:
    """Тесты для метода calc_confidence."""

    def test_cnn_confidence_basic(self):
        """Базовый расчет CNN уверенности: cnn_count / observation_count."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 20
        sign.cnn_count = 15
        
        sign.calc_confidence()
        
        assert sign.conf_cnn == 0.75  # 15 / 20

    def test_cnn_confidence_zero_observations(self):
        """CNN уверенность при нуле наблюдений = 0.0."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 0
        sign.cnn_count = 0
        
        sign.calc_confidence()
        
        assert sign.conf_cnn == 0.0

    def test_cnn_confidence_perfect_stability(self):
        """100% стабильная классификация CNN."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 50
        sign.cnn_count = 50
        
        sign.calc_confidence()
        
        assert sign.conf_cnn == 1.0

    def test_placement_no_snap_data(self):
        """Уверенность постановки без данных snap (нейтральные баллы)."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 10
        sign.cnn_count = 8
        sign.pixel_x = [100, 102, 101, 103, 100, 102, 101, 103, 100, 102]
        
        # Без snap данных
        sign.calc_confidence(snap_dist_m=-1.0, osm_azimuth=None, gpx_azimuth=None)
        
        # conf_placement должна быть > 0 (track stability + length)
        assert 0.0 < sign.conf_placement < 1.0
        assert sign.snap_distance == -1.0
        assert sign.azimuth_delta == 0.0

    def test_placement_perfect_snap(self):
        """Отличный snap: близко к дороге (3м), совпадающий азимут."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 20
        sign.cnn_count = 18
        sign.pixel_x = [100] * 20  # Стабильный трек
        
        sign.calc_confidence(snap_dist_m=3.0, osm_azimuth=45.0, gpx_azimuth=47.0)
        
        # Snap расстояние 3м < 5м → snap_score = 1.0
        assert sign.snap_distance == 3.0
        # Разница азимутов 2° → az_score ≈ 0.96
        assert sign.azimuth_delta == 2.0
        # conf_placement должна быть высокой
        assert sign.conf_placement > 0.8

    def test_placement_poor_snap(self):
        """Плохой snap: далеко от дороги (40м), разные азимуты."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 15
        sign.cnn_count = 12
        sign.pixel_x = [100, 150, 120, 180, 110] * 3  # Нестабильный трек
        
        sign.calc_confidence(snap_dist_m=40.0, osm_azimuth=90.0, gpx_azimuth=45.0)
        
        # Snap расстояние 40м > 30м → snap_score = 0.0
        assert sign.snap_distance == 40.0
        # Разница азимутов 45° → az_score = 0.0
        assert sign.azimuth_delta == 45.0
        # conf_placement должна быть низкой
        assert sign.conf_placement < 0.5

    def test_placement_medium_snap(self):
        """Средний snap: умеренное расстояние (15м), небольшая разница азимутов."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 25
        sign.cnn_count = 22
        sign.pixel_x = [100, 102, 101, 103] * 6 + [100]  # Довольно стабильный
        
        sign.calc_confidence(snap_dist_m=15.0, osm_azimuth=120.0, gpx_azimuth=110.0)
        
        # Snap расстояние 15м: в диапазоне 5-30м → линейная интерполяция
        assert sign.snap_distance == 15.0
        # Разница азимутов 10° → az_score ≈ 0.78
        assert sign.azimuth_delta == 10.0
        # conf_placement должна быть средней-высокой
        assert 0.5 < sign.conf_placement < 0.85

    def test_total_confidence_calculation(self):
        """Общая уверенность = 50% CNN + 50% placement."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 30
        sign.cnn_count = 24  # CNN conf = 0.8
        sign.pixel_x = [100] * 30
        
        # Отличный snap
        sign.calc_confidence(snap_dist_m=2.0, osm_azimuth=180.0, gpx_azimuth=180.0)
        
        # conf_total = 0.5 * 0.8 + 0.5 * conf_placement
        expected = 0.5 * 0.8 + 0.5 * sign.conf_placement
        assert abs(sign.conf_total - expected) < 0.001

    def test_short_track_low_confidence(self):
        """Короткий трек (мало наблюдений) → низкая уверенность постановки."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 5  # Очень мало
        sign.cnn_count = 4
        sign.pixel_x = [100, 101, 100, 101, 100]
        
        sign.calc_confidence(snap_dist_m=5.0, osm_azimuth=0.0, gpx_azimuth=0.0)
        
        # Длина трека влияет: (5-4)/16 = 0.0625
        # conf_placement должна быть невысокой из-за короткого трека
        assert sign.conf_placement < 0.7

    def test_long_stable_track_high_confidence(self):
        """Длинный стабильный трек → высокая уверенность."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 50
        sign.cnn_count = 48
        sign.pixel_x = [100] * 50  # Абсолютно стабильный
        
        sign.calc_confidence(snap_dist_m=1.0, osm_azimuth=270.0, gpx_azimuth=271.0)
        
        # Все факторы отличные
        assert sign.conf_cnn > 0.95
        assert sign.conf_placement > 0.9
        assert sign.conf_total > 0.9

    def test_azimuth_wraparound(self):
        """Проверка корректной обработки wraparound азимутов (359° vs 1°)."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 20
        sign.cnn_count = 18
        sign.pixel_x = [100] * 20
        
        # 359° и 1° реально различаются на 2°, а не на 358°
        sign.calc_confidence(snap_dist_m=5.0, osm_azimuth=359.0, gpx_azimuth=1.0)
        
        # Должно быть 2°, а не 358°
        assert sign.azimuth_delta == 2.0

    def test_azimuth_180_degree_case(self):
        """Проверка 180° случая (max возможное расхождение)."""
        sign = TrackedSign(best_cnn="3.27", best_yolo="3.27")
        sign.observation_count = 20
        sign.cnn_count = 18
        sign.pixel_x = [100] * 20
        
        # Противоположные направления
        sign.calc_confidence(snap_dist_m=5.0, osm_azimuth=0.0, gpx_azimuth=180.0)
        
        # 180° → az_score = 0 (полное расхождение)
        assert sign.azimuth_delta == 180.0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
