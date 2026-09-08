"""
Regression test для DashboardPage.
Проверяет что UI компоненты инициализируются правильно.
"""
import sys
import os


def test_dashboard_page_structure():
    """Проверяет структуру DashboardPage."""
    
    with open("ui/widgets/dashboard_page.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Проверяем наличие класса DashboardPage
    if "class DashboardPage(QWidget):" not in content:
        print("FAIL: DashboardPage class not found")
        return False
    
    # Проверяем наличие VideoScanWorker
    if "class VideoScanWorker(QThread):" not in content:
        print("FAIL: VideoScanWorker class not found")
        return False
    
    # Проверяем что используются правильные атрибуты (не _stats_cards из старой версии)
    required_attrs = [
        "_stat_videos",
        "_stat_gpx",
        "_stat_ready",
        "_video_scan_worker",
        "_pick_video",
        "_pick_gpx",
        "_pick_geojson",
    ]
    
    missing = []
    for attr in required_attrs:
        if attr not in content:
            missing.append(attr)
    
    if missing:
        print(f"FAIL: Missing required attributes: {missing}")
        return False
    
    # Проверяем что старый атрибут _stats_cards НЕ используется
    if "_stats_cards" in content:
        print("FAIL: Old attribute _stats_cards found (should not exist)")
        return False
    
    print("PASS: DashboardPage structure is correct")
    return True


def test_videoscanworker_signals():
    """Проверяет что VideoScanWorker имеет правильные сигналы."""
    
    with open("ui/widgets/dashboard_page.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Находим определение VideoScanWorker
    if "class VideoScanWorker(QThread):" not in content:
        print("FAIL: VideoScanWorker not found")
        return False
    
    # Проверяем сигналы
    required_signals = [
        "finished = pyqtSignal",
        "error = pyqtSignal",
    ]
    
    missing = []
    for signal in required_signals:
        if signal not in content:
            missing.append(signal)
    
    if missing:
        print(f"FAIL: Missing signals: {missing}")
        return False
    
    print("PASS: VideoScanWorker has correct signals")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("DashboardPage Regression Test")
    print("=" * 60)
    
    results = [
        test_dashboard_page_structure(),
        test_videoscanworker_signals(),
    ]
    
    print("=" * 60)
    if all(results):
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
