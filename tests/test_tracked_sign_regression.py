"""
Regression tests для TrackedSign и calc_confidence.
Защита от повторных циклов "исправил-откатил" в cnn_count логике.
"""
import sys
import os

# Добавляем корневую директорию в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_tracked_sign_basic_structure():
    """Проверяет базовую структуру TrackedSign."""
    from core.sign import TrackedSign
    
    sign = TrackedSign()
    
    # Проверяем наличие обязательных полей
    required_fields = [
        'pixel_x', 'pixel_y', 'widths', 'heights',
        'car_x', 'car_y',
        'frame_numbers', 'abs_frame_numbers',
        'yolo_results', 'cnn_results', 'side_results', 'text_results',
        'azimuth', 'is_left', 'is_turn',
        'latitude', 'longitude',
        'conf_cnn', 'conf_placement', 'conf_total',
    ]
    
    for field in required_fields:
        if not hasattr(sign, field):
            print(f"FAIL: Missing field '{field}' in TrackedSign")
            return False
    
    print("PASS: TrackedSign has all required fields")
    return True


def test_tracked_sign_cnn_stability():
    """Проверяет механизм стабильности CNN."""
    from core.sign import TrackedSign
    
    sign = TrackedSign()
    
    # Проверяем наличие методов оптимизации
    if not hasattr(sign, 'should_skip_cnn'):
        print("FAIL: Missing method 'should_skip_cnn'")
        return False
    
    if not hasattr(sign, 'get_stable_cnn_class'):
        print("FAIL: Missing method 'get_stable_cnn_class'")
        return False
    
    if not hasattr(sign, '_update_cnn_stability'):
        print("FAIL: Missing method '_update_cnn_stability'")
        return False
    
    # Проверяем что по умолчанию не стабилен
    if sign.should_skip_cnn():
        print("FAIL: New sign should not be stable")
        return False
    
    print("PASS: TrackedSign CNN stability mechanism exists")
    return True


def test_calc_confidence_exists():
    """Проверяет наличие calc_confidence метода."""
    from core.sign import TrackedSign
    
    sign = TrackedSign()
    
    if not hasattr(sign, 'calc_confidence'):
        print("FAIL: Missing method 'calc_confidence'")
        return False
    
    # Проверяем что метод вызываемый
    if not callable(sign.calc_confidence):
        print("FAIL: 'calc_confidence' is not callable")
        return False
    
    print("PASS: calc_confidence method exists")
    return True


def test_best_properties_exist():
    """Проверяет наличие best_* свойств."""
    from core.sign import TrackedSign
    
    sign = TrackedSign()
    
    # Добавляем тестовые данные
    sign.cnn_results = ['1.1', '1.1', '1.2']
    sign.yolo_results = ['blue', 'blue', 'blue']
    sign.side_results = [False, False, True]
    
    # Проверяем свойства
    properties = ['best_cnn', 'best_yolo', 'best_side']
    
    for prop in properties:
        if not hasattr(sign, prop):
            print(f"FAIL: Missing property '{prop}'")
            return False
    
    print("PASS: best_* properties exist")
    return True


def test_observation_count():
    """Проверяет observation_count свойство."""
    from core.sign import TrackedSign
    from core.frame import DetectedSign
    
    sign = TrackedSign()
    
    if not hasattr(sign, 'observation_count'):
        print("FAIL: Missing property 'observation_count'")
        return False
    
    # Проверяем начальное значение
    if sign.observation_count != 0:
        print(f"FAIL: Initial observation_count should be 0, got {sign.observation_count}")
        return False
    
    # Добавляем наблюдение
    det = DetectedSign(
        x=100, y=200, w=50, h=50,
        name_sign='blue',
        number_sign='1.1',
        is_side=False,
        frame_number=1,
        absolute_frame_number=1,
        latitude=53.9,
        longitude=27.5,
        text_on_sign=''
    )
    sign.append(det)
    
    if sign.observation_count != 1:
        print(f"FAIL: After 1 append, observation_count should be 1, got {sign.observation_count}")
        return False
    
    print("PASS: observation_count works correctly")
    return True


def test_detector_batch_methods_exist():
    """Проверяет наличие batch методов в Detector."""
    from core.detector import Detector
    
    detector = Detector()
    
    batch_methods = [
        '_classify_rube_batch',
        '_classify_fine_batch',
        '_run_cnn_batch',
    ]
    
    for method in batch_methods:
        if not hasattr(detector, method):
            print(f"FAIL: Missing method '{method}' in Detector")
            return False
    
    print("PASS: Detector batch methods exist")
    return True


def test_cnn_cache_exists():
    """Проверяет наличие CNN кэша в Detector."""
    from core.detector import Detector
    
    detector = Detector()
    
    if not hasattr(detector, '_cnn_cache'):
        print("FAIL: Missing '_cnn_cache' in Detector")
        return False
    
    # Проверяем методы кэша
    if not hasattr(detector._cnn_cache, 'get'):
        print("FAIL: CNN cache missing 'get' method")
        return False
    
    if not hasattr(detector._cnn_cache, 'put'):
        print("FAIL: CNN cache missing 'put' method")
        return False
    
    if not hasattr(detector._cnn_cache, 'hit_rate'):
        print("FAIL: CNN cache missing 'hit_rate' property")
        return False
    
    print("PASS: CNN cache exists and has required methods")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("TrackedSign and Detector Regression Tests")
    print("=" * 60)
    
    results = [
        test_tracked_sign_basic_structure(),
        test_tracked_sign_cnn_stability(),
        test_calc_confidence_exists(),
        test_best_properties_exist(),
        test_observation_count(),
        test_detector_batch_methods_exist(),
        test_cnn_cache_exists(),
    ]
    
    print("=" * 60)
    if all(results):
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
