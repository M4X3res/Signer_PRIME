"""
scripts/test_settings_ui.py
Тестирует создание SettingsPage без запуска полного приложения.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def test_settings_page():
    """Тестирует создание SettingsPage."""
    from PyQt6.QtWidgets import QApplication
    
    print("Создаём QApplication...")
    app = QApplication(sys.argv)
    
    try:
        print("Импортируем SettingsPage...")
        from ui.widgets.settings_page import SettingsPage
        
        print("Создаём SettingsPage...")
        page = SettingsPage()
        
        print("\n[SUCCESS] SettingsPage создан успешно!")
        print("\nПроверка наличия виджетов Turn Geometry:")
        
        widgets = [
            ('_turn_use_bearing_toggle', 'Toggle для bearing geometry'),
            ('_camera_fov_spin', 'SpinBox для FOV камеры'),
            ('_turn_ray_dist_spin', 'SpinBox для дистанции луча'),
            ('_turn_radius_spin', 'SpinBox для радиуса детекции'),
        ]
        
        all_ok = True
        for attr_name, description in widgets:
            if hasattr(page, attr_name):
                print(f"  [OK] {attr_name}: {description}")
            else:
                print(f"  [FAIL] {attr_name}: НЕ НАЙДЕН!")
                all_ok = False
        
        if all_ok:
            print("\n[SUCCESS] Все виджеты Turn Geometry созданы корректно!")
            
            # Тестируем сохранение
            print("\nТестируем _collect_settings()...")
            try:
                page._collect_settings()
                print("[OK] _collect_settings() выполнен без ошибок")
                
                # Проверяем что значения сохранились
                print(f"\nТекущие настройки Turn Geometry:")
                print(f"  - turn_use_bearing_geometry: {page._settings.turn_use_bearing_geometry}")
                print(f"  - camera_hfov_deg: {page._settings.camera_hfov_deg}")
                print(f"  - turn_ray_max_distance_m: {page._settings.turn_ray_max_distance_m}")
                print(f"  - turn_detection_radius_m: {page._settings.turn_detection_radius_m}")
                
            except Exception as e:
                print(f"[FAIL] Ошибка в _collect_settings(): {e}")
                import traceback
                traceback.print_exc()
                all_ok = False
        
        return 0 if all_ok else 1
        
    except Exception as e:
        print(f"\n[FAIL] Ошибка при создании SettingsPage: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_settings_page())
