"""
scripts/verify_block_h.py
Verification script для BLOCK H — Turn Geometry Implementation.

Проверяет что все компоненты установлены корректно.
"""
import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_module(module_name):
    """Проверка импорта модуля."""
    try:
        __import__(module_name)
        return True, "OK"
    except Exception as e:
        return False, str(e)

def check_function(module_name, function_name):
    """Проверка наличия функции в модуле."""
    try:
        module = __import__(module_name, fromlist=[function_name])
        if not hasattr(module, function_name):
            return False, f"Function {function_name} not found"
        return True, "OK"
    except Exception as e:
        return False, str(e)

def check_settings_field(field_name):
    """Проверка наличия поля в AppSettings."""
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if not hasattr(settings, field_name):
            return False, f"Field {field_name} not found"
        return True, f"= {getattr(settings, field_name)}"
    except Exception as e:
        return False, str(e)

def main():
    print("="*70)
    print("BLOCK H — Turn Geometry Implementation Verification")
    print("="*70)
    print()
    
    checks = []
    
    # 1. Проверка core/intersection_geometry.py
    print("[1/6] Проверка модуля intersection_geometry...")
    
    ok, msg = check_module("core.intersection_geometry")
    checks.append(("Module: core.intersection_geometry", ok, msg))
    print(f"  {'[OK]' if ok else '[FAIL]'} Import module: {msg}")
    
    if ok:
        ok, msg = check_function("core.intersection_geometry", "compute_sign_bearing")
        checks.append(("Function: compute_sign_bearing", ok, msg))
        print(f"  {'[OK]' if ok else '[FAIL]'} compute_sign_bearing: {msg}")
        
        ok, msg = check_function("core.intersection_geometry", "raycast_to_ways")
        checks.append(("Function: raycast_to_ways", ok, msg))
        print(f"  {'[OK]' if ok else '[FAIL]'} raycast_to_ways: {msg}")
        
        ok, msg = check_function("core.intersection_geometry", "aggregate_observations")
        checks.append(("Function: aggregate_observations", ok, msg))
        print(f"  {'[OK]' if ok else '[FAIL]'} aggregate_observations: {msg}")
    
    print()
    
    # 2. Проверка TrackedSign.bbox_centers_x/y
    print("[2/6] Проверка TrackedSign...")
    try:
        from core.sign import TrackedSign
        sign = TrackedSign()
        
        if hasattr(sign, 'bbox_centers_x'):
            checks.append(("TrackedSign.bbox_centers_x", True, "OK"))
            print(f"  [OK] bbox_centers_x field exists")
        else:
            checks.append(("TrackedSign.bbox_centers_x", False, "Field not found"))
            print(f"  [FAIL] bbox_centers_x field not found")
        
        if hasattr(sign, 'bbox_centers_y'):
            checks.append(("TrackedSign.bbox_centers_y", True, "OK"))
            print(f"  [OK] bbox_centers_y field exists")
        else:
            checks.append(("TrackedSign.bbox_centers_y", False, "Field not found"))
            print(f"  [FAIL] bbox_centers_y field not found")
    except Exception as e:
        checks.append(("TrackedSign", False, str(e)))
        print(f"  [FAIL] Error: {e}")
    
    print()
    
    # 3. Проверка FinalHandler methods
    print("[3/6] Проверка FinalHandler...")
    try:
        from core.final_handler import FinalHandler
        handler = FinalHandler()
        
        methods = [
            "_process_turn_signs",
            "_process_turn_signs_bearing",
            "_process_turn_signs_legacy"
        ]
        
        for method_name in methods:
            if hasattr(handler, method_name):
                checks.append((f"FinalHandler.{method_name}", True, "OK"))
                print(f"  [OK] {method_name} exists")
            else:
                checks.append((f"FinalHandler.{method_name}", False, "Not found"))
                print(f"  [FAIL] {method_name} not found")
    except Exception as e:
        checks.append(("FinalHandler", False, str(e)))
        print(f"  [FAIL] Error: {e}")
    
    print()
    
    # 4. Проверка настроек AppSettings
    print("[4/6] Проверка AppSettings...")
    
    fields = [
        "camera_hfov_deg",
        "turn_ray_max_distance_m",
        "turn_detection_radius_m",
        "turn_use_bearing_geometry"
    ]
    
    for field in fields:
        ok, msg = check_settings_field(field)
        checks.append((f"AppSettings.{field}", ok, msg))
        print(f"  {'[OK]' if ok else '[FAIL]'} {field}: {msg}")
    
    print()
    
    # 5. Проверка тестов
    print("[5/6] Проверка тестов...")
    
    test_files = [
        "tests/test_intersection_geometry.py",
        "tests/run_geometry_tests.py"
    ]
    
    for test_file in test_files:
        if os.path.exists(test_file):
            checks.append((f"Test file: {test_file}", True, "Exists"))
            print(f"  [OK] {test_file} exists")
        else:
            checks.append((f"Test file: {test_file}", False, "Not found"))
            print(f"  [FAIL] {test_file} not found")
    
    # Запуск тестов
    try:
        print()
        print("  Running tests...")
        import subprocess
        result = subprocess.run(
            [sys.executable, "tests/run_geometry_tests.py"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            checks.append(("Unit tests", True, "All passed"))
            print(f"  [OK] All unit tests passed")
            # Показываем вывод
            for line in result.stdout.split('\n'):
                if line.strip():
                    print(f"       {line}")
        else:
            checks.append(("Unit tests", False, f"Exit code: {result.returncode}"))
            print(f"  [FAIL] Tests failed with exit code {result.returncode}")
            print(result.stdout)
            print(result.stderr)
    except Exception as e:
        checks.append(("Unit tests", False, str(e)))
        print(f"  [FAIL] Error running tests: {e}")
    
    print()
    
    # 6. Проверка документации
    print("[6/6] Проверка документации...")
    
    docs = [
        "BLOCK_H_TURN_GEOMETRY_PREFLIGHT.md",
        "BLOCK_H_TURN_GEOMETRY_PARTIAL.md",
        "BLOCK_H_TURN_GEOMETRY_IMPLEMENTATION.md",
        "BLOCK_H_QUICK_SUMMARY.md"
    ]
    
    for doc in docs:
        if os.path.exists(doc):
            checks.append((f"Doc: {doc}", True, "Exists"))
            print(f"  [OK] {doc} exists")
        else:
            checks.append((f"Doc: {doc}", False, "Not found"))
            print(f"  [FAIL] {doc} not found")
    
    print()
    print("="*70)
    print("SUMMARY")
    print("="*70)
    
    passed = sum(1 for _, ok, _ in checks if ok)
    total = len(checks)
    
    print(f"\nTotal checks: {total}")
    print(f"Passed: {passed}")
    print(f"Failed: {total - passed}")
    
    if total - passed > 0:
        print("\nFailed checks:")
        for name, ok, msg in checks:
            if not ok:
                print(f"  - {name}: {msg}")
    
    print()
    
    if passed == total:
        print("[SUCCESS] All checks passed! BLOCK H is ready to use.")
        return 0
    else:
        print("[WARNING] Some checks failed. Review the output above.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
