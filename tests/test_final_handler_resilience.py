"""
tests/test_final_handler_resilience.py
Regression test для БАГ №3: один повреждённый знак не должен приводить к потере всех.

Проверяет, что _validate_signs_for_processing корректно отфильтровывает знаки
без car_x/car_y, и остальные знаки не теряются.
"""
import sys
from pathlib import Path
import io

# Устанавливаем UTF-8 для stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корень проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.final_handler import FinalHandler
from core.sign import TrackedSign


def test_validate_signs_for_processing():
    """
    Тестирует валидацию знаков перед обработкой.
    """
    print("=" * 60)
    print("TEST: FinalHandler sign validation resilience")
    print("=" * 60)
    
    # Создаём 3 нормальных знака и 1 "битый"
    print("\n[1] Creating test signs (3 normal + 1 broken)...")
    
    normal_signs = []
    for i in range(3):
        sign = TrackedSign()
        sign.cnn_results = [f"3.2{i}"]
        sign.frame_numbers = [100 + i]
        sign.car_x = [1000.0 + i * 10]
        sign.car_y = [2000.0 + i * 10]
        normal_signs.append(sign)
    
    # "Битый" знак без координат
    broken_sign = TrackedSign()
    broken_sign.cnn_results = ["3.24"]
    broken_sign.frame_numbers = [200]
    broken_sign.car_x = []  # Пустой!
    broken_sign.car_y = []  # Пустой!
    
    all_signs = normal_signs + [broken_sign]
    print(f"Created {len(all_signs)} signs total (3 valid, 1 broken)")
    
    # Тест: валидация должна вернуть только нормальные знаки
    print("\n[2] Testing _validate_signs_for_processing()...")
    handler = FinalHandler()
    
    valid_signs = handler._validate_signs_for_processing(all_signs)
    
    print(f"Valid signs returned: {len(valid_signs)}")
    print(f"Expected: 3")
    
    assert len(valid_signs) == 3, f"Expected 3 valid signs, got {len(valid_signs)}"
    
    # Проверяем что битый знак не в списке
    for sign in valid_signs:
        assert sign.car_x, "Found sign without car_x in valid list!"
        assert sign.car_y, "Found sign without car_y in valid list!"
    
    print("PASS: Broken sign filtered out, valid signs preserved")
    
    # Тест: проверка что битый знак был именно отфильтрован
    print("\n[3] Verifying broken sign was filtered...")
    filtered_types = [s.best_cnn for s in valid_signs]
    assert "3.24" not in filtered_types, "Broken sign (3.24) should not be in valid list!"
    print("PASS: Broken sign not present in filtered list")
    
    # Тест: все нормальные знаки остались
    print("\n[4] Verifying all normal signs preserved...")
    expected_types = {"3.20", "3.21", "3.22"}
    actual_types = {s.best_cnn for s in valid_signs}
    assert expected_types == actual_types, f"Expected {expected_types}, got {actual_types}"
    print("PASS: All normal signs preserved")
    
    print("\n" + "=" * 60)
    print("ALL TESTS PASSED")
    print("=" * 60)
    return True


if __name__ == "__main__":
    sys.stdout.flush()
    try:
        success = test_validate_signs_for_processing()
        sys.exit(0 if success else 1)
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
