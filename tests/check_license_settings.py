"""
tests/check_license_settings.py
Regression test для Задачи 1: Управление лицензией в настройках.
"""
import os
import sys

def test_license_settings_block():
    """Проверяет наличие блока управления лицензией в settings_page.py"""
    
    settings_page_path = "ui/widgets/settings_page.py"
    
    if not os.path.exists(settings_page_path):
        print(f"❌ Файл {settings_page_path} не найден")
        return False
    
    with open(settings_page_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверка 1: импорт LicenseManager и PLAN_DISPLAY_NAMES
    if 'from licensing.license_manager import LicenseManager' not in content:
        print("❌ Отсутствует импорт LicenseManager в settings_page.py")
        return False
    
    if 'PLAN_DISPLAY_NAMES' not in content:
        print("❌ Отсутствует импорт PLAN_DISPLAY_NAMES в settings_page.py")
        return False
    
    # Проверка 2: наличие группы "Лицензия"
    if '"Лицензия"' not in content and "'Лицензия'" not in content:
        print("❌ Группа 'Лицензия' не найдена в settings_page.py")
        return False
    
    # Проверка 3: наличие виджетов лицензии
    if '_license_status_label' not in content:
        print("❌ Отсутствует виджет _license_status_label")
        return False
    
    if '_btn_manage_license' not in content:
        print("❌ Отсутствует кнопка _btn_manage_license")
        return False
    
    if '_btn_refresh_license' not in content:
        print("❌ Отсутствует кнопка _btn_refresh_license")
        return False
    
    # Проверка 4: наличие методов управления лицензией
    if '_update_license_display' not in content:
        print("❌ Отсутствует метод _update_license_display")
        return False
    
    if '_open_license_dialog' not in content:
        print("❌ Отсутствует метод _open_license_dialog")
        return False
    
    if '_refresh_license_status' not in content:
        print("❌ Отсутствует метод _refresh_license_status")
        return False
    
    # Проверка 5: группа лицензии НЕ в _advanced_only_widgets
    # Ищем определение _advanced_only_widgets
    lines = content.split('\n')
    in_advanced_list = False
    license_group_in_advanced = False
    
    for i, line in enumerate(lines):
        if '_advanced_only_widgets = [' in line or '_advanced_only_widgets=[' in line:
            in_advanced_list = True
            # Ищем закрывающую скобку
            for j in range(i, min(i + 30, len(lines))):
                if 'license_group' in lines[j] and in_advanced_list:
                    license_group_in_advanced = True
                    break
                if ']' in lines[j] and in_advanced_list:
                    in_advanced_list = False
                    break
    
    if license_group_in_advanced:
        print("❌ Группа license_group найдена в _advanced_only_widgets (должна быть видна всегда)")
        return False
    
    print("✅ Блок управления лицензией корректно добавлен в настройки")
    return True


def test_plan_display_names_constant():
    """Проверяет наличие константы PLAN_DISPLAY_NAMES в license_manager.py"""
    
    license_manager_path = "licensing/license_manager.py"
    
    if not os.path.exists(license_manager_path):
        print(f"❌ Файл {license_manager_path} не найден")
        return False
    
    with open(license_manager_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if 'PLAN_DISPLAY_NAMES' not in content:
        print("❌ Константа PLAN_DISPLAY_NAMES не найдена в license_manager.py")
        return False
    
    if '"monthly"' not in content or '"Месячная подписка"' not in content:
        print("❌ PLAN_DISPLAY_NAMES не содержит ожидаемых значений")
        return False
    
    print("✅ Константа PLAN_DISPLAY_NAMES корректно определена")
    return True


def test_license_dialog_uses_constant():
    """Проверяет что license_dialog.py использует импортированную константу"""
    
    license_dialog_path = "ui/widgets/license_dialog.py"
    
    if not os.path.exists(license_dialog_path):
        print(f"❌ Файл {license_dialog_path} не найден")
        return False
    
    with open(license_dialog_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверка импорта
    if 'PLAN_DISPLAY_NAMES' not in content:
        print("❌ PLAN_DISPLAY_NAMES не импортирована в license_dialog.py")
        return False
    
    # Проверка использования
    if 'PLAN_DISPLAY_NAMES.get' not in content:
        print("❌ PLAN_DISPLAY_NAMES не используется в license_dialog.py")
        return False
    
    # Проверка что старый словарь plan_names удалён
    lines = content.split('\n')
    for line in lines:
        if 'plan_names = {' in line and 'PLAN_DISPLAY_NAMES' not in line:
            print("❌ Старый словарь plan_names всё ещё присутствует (дублирование)")
            return False
    
    print("✅ license_dialog.py корректно использует импортированную константу")
    return True


def test_main_window_property():
    """Проверяет наличие property для передачи license_manager в MainWindow"""
    
    main_window_path = "ui/main_window.py"
    
    if not os.path.exists(main_window_path):
        print(f"❌ Файл {main_window_path} не найден")
        return False
    
    with open(main_window_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    if '@property' not in content:
        print("❌ Property для license_manager не найден в main_window.py")
        return False
    
    if 'def license_manager' not in content:
        print("❌ Метод license_manager не найден в main_window.py")
        return False
    
    if '@license_manager.setter' not in content:
        print("❌ Setter для license_manager не найден в main_window.py")
        return False
    
    print("✅ MainWindow корректно передаёт license_manager в SettingsPage")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Проверка Задачи 1: Управление лицензией в настройках")
    print("=" * 60)
    
    results = [
        test_plan_display_names_constant(),
        test_license_dialog_uses_constant(),
        test_license_settings_block(),
        test_main_window_property(),
    ]
    
    print("=" * 60)
    if all(results):
        print("✅ Все проверки пройдены успешно!")
        sys.exit(0)
    else:
        print("❌ Некоторые проверки не прошли")
        sys.exit(1)
