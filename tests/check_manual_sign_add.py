"""
tests/check_manual_sign_add.py
Regression test для Задачи 3: Ручное добавление знака на карте.
"""
import os
import sys
import re

def test_api_sign_create_fields():
    """Проверяет что api_sign_create правильно обрабатывает поле is_left"""
    
    map_server_path = "server/map_server.py"
    
    if not os.path.exists(map_server_path):
        print(f"❌ Файл {map_server_path} не найден")
        return False
    
    with open(map_server_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверка 1: наличие обработки is_left в теле запроса
    if 'is_left' not in content:
        print("❌ Поле is_left не обрабатывается в api_sign_create")
        return False
    
    # Проверка 2: left сохраняется как str(bool), а не "manually_added"
    lines = content.split('\n')
    in_api_sign_create = False
    left_field_correct = False
    manually_added_separate = False
    
    for i, line in enumerate(lines):
        if 'def api_sign_create' in line:
            in_api_sign_create = True
        elif in_api_sign_create and ('def ' in line or '@app.route' in line) and 'api_sign_create' not in line:
            in_api_sign_create = False
        
        if in_api_sign_create:
            # Проверяем что left формируется через str(is_left) или str(bool(...))
            if '"left":' in line and 'str(' in line and ('is_left' in line or 'bool' in line):
                left_field_correct = True
            
            # Проверяем что manually_added это отдельное поле
            if '"manually_added":' in line and 'True' in line:
                manually_added_separate = True
            
            # Проверяем что НЕТ старого варианта "left": "manually_added"
            if '"left": "manually_added"' in line or "'left': 'manually_added'" in line:
                print("❌ Найден старый паттерн 'left': 'manually_added' — должно быть через is_left")
                return False
    
    if not left_field_correct:
        print("❌ Поле 'left' не формируется корректно через str(is_left)")
        return False
    
    if not manually_added_separate:
        print("❌ Отдельное поле 'manually_added' не найдено")
        return False
    
    # Проверка 3: валидация координат
    if 'Invalid latitude' not in content and 'Invalid longitude' not in content:
        print("⚠️  Предупреждение: валидация координат не найдена (рекомендуется)")
    
    print("✅ api_sign_create правильно обрабатывает поля")
    return True


def test_map_html_add_button():
    """Проверяет наличие кнопки 'Добавить знак' в map.html"""
    
    map_html_path = "templates/map.html"
    
    if not os.path.exists(map_html_path):
        print(f"❌ Файл {map_html_path} не найден")
        return False
    
    with open(map_html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверяем наличие кнопки
    if 'Добавить знак' not in content:
        print("❌ Кнопка 'Добавить знак' не найдена в map.html")
        return False
    
    # Проверяем что кнопка вызывает togglePlacementMode
    if 'togglePlacementMode' not in content:
        print("❌ Функция togglePlacementMode не найдена")
        return False
    
    print("✅ Кнопка 'Добавить знак' добавлена")
    return True


def test_placement_mode_logic():
    """Проверяет логику режима размещения знака"""
    
    map_html_path = "templates/map.html"
    
    with open(map_html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверка 1: переменная placementMode
    if 'let placementMode' not in content:
        print("❌ Переменная placementMode не объявлена")
        return False
    
    # Проверка 2: функция togglePlacementMode
    if 'function togglePlacementMode' not in content:
        print("❌ Функция togglePlacementMode не найдена")
        return False
    
    # Проверка 3: изменение курсора на crosshair
    if 'cursor = \'crosshair\'' not in content and 'cursor = "crosshair"' not in content:
        print("❌ Курсор не меняется на crosshair в режиме размещения")
        return False
    
    # Проверка 4: обработчик клика по карте
    if 'map.once(\'click\'' not in content and 'map.once("click"' not in content:
        print("❌ Обработчик клика по карте не добавлен")
        return False
    
    # Проверка 5: обработчик Escape
    if 'Escape' not in content:
        print("⚠️  Предупреждение: обработчик Escape не найден (рекомендуется)")
    
    print("✅ Логика режима размещения корректна")
    return True


def test_create_sign_panel():
    """Проверяет наличие панели создания знака"""
    
    map_html_path = "templates/map.html"
    
    with open(map_html_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Проверка 1: функция openCreateSignPanel
    if 'function openCreateSignPanel' not in content:
        print("❌ Функция openCreateSignPanel не найдена")
        return False
    
    # Проверка 2: функция saveNewSign
    if 'function saveNewSign' not in content:
        print("❌ Функция saveNewSign не найдена")
        return False
    
    # Проверка 3: POST запрос к /api/sign
    if '${API}/sign' not in content and '`${API}/sign`' not in content:
        print("❌ POST запрос к /api/sign не найден")
        return False
    
    if "method: 'POST'" not in content and 'method: "POST"' not in content:
        print("❌ saveNewSign не использует метод POST")
        return False
    
    # Проверка 4: поле is_left передаётся в запросе
    if 'is_left' not in content:
        print("❌ Поле is_left не передаётся в запросе создания знака")
        return False
    
    # Проверка 5: перезагрузка знаков после создания
    if 'loadSigns()' not in content:
        print("❌ Знаки не перезагружаются после создания")
        return False
    
    # Проверка 6: выбор типа знака
    if 'create-type' not in content:
        print("❌ Селектор типа знака не найден")
        return False
    
    # Проверка 7: поля для координат, азимута, стороны
    required_fields = ['create-lat', 'create-lon', 'create-azimuth', 'create-side']
    for field in required_fields:
        if field not in content:
            print(f"❌ Поле '{field}' не найдено в панели создания")
            return False
    
    print("✅ Панель создания знака реализована корректно")
    return True


def test_final_handler_compatibility():
    """Проверяет что вручную добавленные знаки совместимы с final_handler"""
    
    # Проверяем что поле left хранится как строка "True"/"False"
    map_server_path = "server/map_server.py"
    
    with open(map_server_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Ищем где формируется feature в api_sign_create
    lines = content.split('\n')
    in_feature_creation = False
    left_as_string = False
    
    for line in lines:
        if 'feature = {' in line or 'properties' in line:
            in_feature_creation = True
        elif in_feature_creation and '}' in line:
            in_feature_creation = False
        
        if in_feature_creation and '"left":' in line:
            # Проверяем что это str(...), а не просто is_left
            if 'str(' in line:
                left_as_string = True
    
    if not left_as_string:
        print("❌ Поле 'left' не конвертируется в строку — несовместимо с final_handler")
        return False
    
    print("✅ Формат данных совместим с final_handler")
    return True


if __name__ == "__main__":
    print("=" * 60)
    print("Проверка Задачи 3: Ручное добавление знака на карте")
    print("=" * 60)
    
    results = [
        test_api_sign_create_fields(),
        test_map_html_add_button(),
        test_placement_mode_logic(),
        test_create_sign_panel(),
        test_final_handler_compatibility(),
    ]
    
    print("=" * 60)
    if all(results):
        print("✅ Все проверки пройдены успешно!")
        sys.exit(0)
    else:
        print("❌ Некоторые проверки не прошли")
        sys.exit(1)
