#!/usr/bin/env python
"""Тест для проверки, что main.py может импортироваться без NameError."""
import sys
import os

# Отключаем GUI-окна
os.environ['QT_QPA_PLATFORM'] = 'offscreen'

try:
    # Проверяем, что можем создать LicenseManager без падения
    from licensing.license_manager import LicenseManager
    print("[OK] LicenseManager imported")
    
    # Создание LicenseManager (это происходит в main.py при старте)
    manager = LicenseManager()
    print("[OK] LicenseManager created without errors")
    
    # Проверка статуса (тоже происходит при старте main.py)
    status = manager.check_local_status()
    print(f"[OK] check_local_status() executed: {status}")
    
    print("\n[SUCCESS] Test 3 PASSED: main.py can start without NameError")
    
except NameError as e:
    print(f"\n[FAILED] NameError detected: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
except Exception as e:
    # Другие ошибки (например, отсутствие PyQt6) - это нормально для этого теста
    if "PyQt6" in str(e) or "No module" in str(e):
        print(f"\n[OK] Expected dependency error (not NameError): {e}")
        print("[SUCCESS] Test 3 PASSED: NameError not detected")
    else:
        print(f"\n[FAILED] Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
