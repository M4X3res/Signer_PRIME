"""
Простая проверка на eager loading без pytest.
"""
import os
import sys


def test_no_eager_models_file():
    """Проверяет, что configs/models.py не существует."""
    if os.path.exists("configs/models.py"):
        print("FAIL: configs/models.py exists! Remove it.")
        return False
    print("PASS: configs/models.py does not exist")
    return True


def test_no_eager_loading_imports():
    """Проверяет что нигде не импортируется старый eager-loading модуль."""
    forbidden_patterns = [
        "from configs import models",
        "from configs.models import",
        "import configs.models"
    ]
    
    violations = []
    
    for root, dirs, files in os.walk("."):
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['venv', 'venv_new', '__pycache__', 'build', 'dist']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                
                # Пропускаем сами тестовые файлы
                if 'test_no_eager_model_loading.py' in filepath or 'check_eager_loading.py' in filepath:
                    continue
                
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        for pattern in forbidden_patterns:
                            if pattern in content:
                                violations.append(f"{filepath}: contains '{pattern}'")
                except:
                    pass
    
    if violations:
        print(f"FAIL: Found forbidden imports:")
        for v in violations:
            print(f"  - {v}")
        return False
    
    print("PASS: No forbidden imports found")
    return True


def test_models_loaded_lazily():
    """Проверяет что sign_models.py использует ленивую загрузку."""
    try:
        with open("configs/sign_models.py", "r", encoding="utf-8") as f:
            content = f.read()
    except:
        print("FAIL: Cannot read configs/sign_models.py")
        return False
    
    checks = [
        ("_LazyModel" in content, "sign_models.py must use _LazyModel"),
        ("model_side_detect = _LazyModel" in content, "model_side_detect must be lazy"),
        ("rube_modal = _LazyModel" in content, "rube_modal must be lazy"),
    ]
    
    all_passed = True
    for check, msg in checks:
        if not check:
            print(f"FAIL: {msg}")
            all_passed = False
    
    if all_passed:
        print("PASS: Lazy loading configured correctly")
    
    return all_passed


if __name__ == "__main__":
    print("=" * 60)
    print("Check protection against eager-loading models")
    print("=" * 60)
    
    results = [
        test_no_eager_models_file(),
        test_no_eager_loading_imports(),
        test_models_loaded_lazily(),
    ]
    
    print("=" * 60)
    if all(results):
        print("ALL TESTS PASSED")
        sys.exit(0)
    else:
        print("SOME TESTS FAILED")
        sys.exit(1)
