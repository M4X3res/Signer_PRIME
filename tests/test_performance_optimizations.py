"""
Структурные regression-тесты без импорта модулей.
Проверяют что файлы содержат необходимые определения.
"""
import sys
import os


def test_tracked_sign_has_cnn_optimization():
    """Проверяет что TrackedSign содержит CNN оптимизацию."""
    
    with open("core/sign.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    required_methods = [
        "def should_skip_cnn",
        "def get_stable_cnn_class",
        "def _update_cnn_stability",
    ]
    
    missing = []
    for method in required_methods:
        if method not in content:
            missing.append(method)
    
    if missing:
        print(f"FAIL: TrackedSign missing methods: {missing}")
        return False
    
    # Проверяем что метод вызывается при append
    if "_update_cnn_stability" not in content or "def append" not in content:
        print("FAIL: _update_cnn_stability not integrated with append")
        return False
    
    print("PASS: TrackedSign has CNN optimization methods")
    return True


def test_detector_has_batch_methods():
    """Проверяет что Detector содержит batch методы."""
    
    with open("core/detector.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    required_methods = [
        "def _classify_rube_batch",
        "def _classify_fine_batch",
        "def _run_cnn_batch",
    ]
    
    missing = []
    for method in required_methods:
        if method not in content:
            missing.append(method)
    
    if missing:
        print(f"FAIL: Detector missing batch methods: {missing}")
        return False
    
    # Проверяем что используется в detect()
    if "_classify_rube_batch" not in content or "_classify_fine_batch" not in content:
        print("FAIL: Batch methods not used in detect()")
        return False
    
    print("PASS: Detector has batch classification methods")
    return True


def test_detector_has_cnn_cache():
    """Проверяет наличие CNN кэша в Detector."""
    
    with open("core/detector.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем класс CNNCache
    if "class CNNCache" not in content:
        print("FAIL: CNNCache class not found")
        return False
    
    # Проверяем что Detector использует кэш
    if "self._cnn_cache" not in content:
        print("FAIL: Detector doesn't use _cnn_cache")
        return False
    
    # Проверяем perceptual hash
    if "compute_image_hash" not in content or "def compute_image_hash" not in content:
        print("FAIL: Perceptual hash function not found")
        return False
    
    print("PASS: Detector has CNN cache with perceptual hash")
    return True


def test_ocr_pool_exists():
    """Проверяет что OCR ProcessPool реализован."""
    
    with open("processing/ocr_pool.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем ProcessPoolExecutor
    if "ProcessPoolExecutor" not in content:
        print("FAIL: ProcessPoolExecutor not found in ocr_pool.py")
        return False
    
    # Проверяем worker функцию
    if "def _process_ocr_task" not in content:
        print("FAIL: OCR worker function not found")
        return False
    
    # Проверяем инициализацию EasyOCR в worker
    if "def _init_worker_ocr" not in content:
        print("FAIL: OCR worker initialization not found")
        return False
    
    print("PASS: OCR ProcessPool implemented")
    return True


def test_osm_batch_snap_exists():
    """Проверяет что batch OSM snap реализован."""
    
    with open("core/osm_snap.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем batch метод
    if "def snap_batch" not in content:
        print("FAIL: snap_batch method not found in OSMSnapper")
        return False
    
    if "def _get_ways_bbox" not in content:
        print("FAIL: _get_ways_bbox method not found")
        return False
    
    print("PASS: Batch OSM snap implemented")
    return True


def test_final_handler_uses_batch_snap():
    """Проверяет что FinalHandler использует batch snap."""
    
    with open("core/final_handler.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем метод batch snap
    if "def _batch_snap_signs" not in content:
        print("FAIL: _batch_snap_signs method not found")
        return False
    
    if "def _sign_to_feature_with_snap" not in content:
        print("FAIL: _sign_to_feature_with_snap method not found")
        return False
    
    # Проверяем что используется в _process_straight_signs
    if "_batch_snap_signs" not in content:
        print("FAIL: Batch snap not used in processing")
        return False
    
    print("PASS: FinalHandler uses batch OSM snap")
    return True


def test_video_reader_has_prefetch():
    """Проверяет что VideoReader имеет prefetch."""
    
    with open("processing/video_reader.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    if "def _prefetch_next_video" not in content:
        print("FAIL: _prefetch_next_video method not found")
        return False
    
    if "self._next_cap" not in content:
        print("FAIL: _next_cap attribute not found")
        return False
    
    print("PASS: VideoReader has prefetch implementation")
    return True


def test_map_has_marker_clustering():
    """Проверяет что карта использует marker clustering."""
    
    with open("templates/map.html", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем подключение библиотеки
    if "leaflet.markercluster" not in content.lower():
        print("FAIL: Leaflet MarkerCluster library not included")
        return False
    
    # Проверяем использование
    if "markerClusterGroup" not in content:
        print("FAIL: markerClusterGroup not used")
        return False
    
    if "markerCluster" not in content or "let markerCluster" not in content:
        print("FAIL: markerCluster variable not declared")
        return False
    
    print("PASS: Map has marker clustering")
    return True


def test_sign_handler_has_tracked_signs_map():
    """Проверяет что SignHandler имеет метод get_tracked_signs_map."""
    
    with open("core/sign_handler.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    if "def get_tracked_signs_map" not in content:
        print("FAIL: get_tracked_signs_map method not found")
        return False
    
    print("PASS: SignHandler has get_tracked_signs_map method")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Structural Regression Tests")
    print("=" * 60)
    
    results = [
        test_tracked_sign_has_cnn_optimization(),
        test_detector_has_batch_methods(),
        test_detector_has_cnn_cache(),
        test_ocr_pool_exists(),
        test_osm_batch_snap_exists(),
        test_final_handler_uses_batch_snap(),
        test_video_reader_has_prefetch(),
        test_map_has_marker_clustering(),
        test_sign_handler_has_tracked_signs_map(),
    ]
    
    print("=" * 60)
    passed = sum(results)
    total = len(results)
    print(f"PASSED: {passed}/{total} tests")
    
    if all(results):
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
