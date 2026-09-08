"""
tests/test_final_handler_return_value.py
Regression test для БАГ №4: save_result() должен возвращать реальное количество записанных features.

Проверяет, что возвращаемое значение соответствует количеству features в файле.
"""
import sys
import os
import tempfile
from pathlib import Path
import io

# Устанавливаем UTF-8 для stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корень проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from configs import config
from core.final_handler import FinalHandler
from core.sign import TrackedSign
import geojson


def test_save_result_return_value():
    """
    Тестирует что save_result() возвращает корректное количество записанных features.
    """
    print("=" * 60)
    print("TEST: FinalHandler save_result() return value")
    print("=" * 60)
    
    # Создаём временный файл для теста
    with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.geojson') as f:
        temp_geojson = f.name
    
    print(f"\n[1] Using temporary file: {temp_geojson}")
    
    try:
        # Создаём тестовые знаки с минимальными данными
        print("\n[2] Creating test signs...")
        test_signs = []
        for i in range(3):
            sign = TrackedSign()
            sign.cnn_results = [f"3.2{i}"]
            sign.frame_numbers = [100 + i]
            sign.car_x = [1000.0 + i * 10]
            sign.car_y = [2000.0 + i * 10]
            sign.yolo_results = [f"3.2{i}"]
            sign.side_results = [False]
            test_signs.append(sign)
        
        print(f"Created {len(test_signs)} test signs")
        
        # Подменяем путь к GeoJSON на временный
        original_path = config.PATH_TO_GEOJSON
        config.PATH_TO_GEOJSON = temp_geojson
        
        # Вызываем save_result()
        print("\n[3] Calling save_result()...")
        handler = FinalHandler()
        returned_count = handler.save_result(test_signs, turns=[])
        
        print(f"Returned count: {returned_count}")
        
        # Проверяем что файл создан
        assert os.path.exists(temp_geojson), "GeoJSON file was not created"
        print("PASS: GeoJSON file created")
        
        # Читаем файл и проверяем количество features
        print("\n[4] Reading saved GeoJSON...")
        with open(temp_geojson, 'r', encoding='utf-8') as f:
            data = geojson.load(f)
        
        actual_count = len(data['features'])
        print(f"Features in file: {actual_count}")
        
        # Проверка: возвращённое значение должно совпадать с количеством в файле
        assert returned_count == actual_count, \
            f"Return value mismatch: returned {returned_count}, but file has {actual_count}"
        
        print("PASS: Return value matches file content")
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        return False
        
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    finally:
        # Cleanup
        config.PATH_TO_GEOJSON = original_path
        if os.path.exists(temp_geojson):
            os.remove(temp_geojson)
            print(f"\nCleanup: Removed {temp_geojson}")


if __name__ == "__main__":
    sys.stdout.flush()
    success = test_save_result_return_value()
    sys.exit(0 if success else 1)
