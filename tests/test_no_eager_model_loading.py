"""
Тест для предотвращения регрессий связанных с eager-loading моделей.

Eager загрузка YOLO моделей в главном потоке вызывает краш 0xC0000409
на Windows (конфликт DLL YOLO+Qt).
"""
import pytest
import os
import ast


def test_no_eager_models_file():
    """Проверяет, что configs/models.py не существует."""
    assert not os.path.exists("configs/models.py"), (
        "КРИТИЧНО: configs/models.py не должен существовать! "
        "Eager loading моделей вызывает краш при использовании с PyQt6."
    )


def test_no_eager_loading_imports():
    """Проверяет что нигде не импортируется старый eager-loading модуль."""
    forbidden_patterns = [
        "from configs import models",
        "from configs.models import",
        "import configs.models"
    ]
    
    violations = []
    
    for root, dirs, files in os.walk("."):
        # Пропускаем venv, .git и т.д.
        dirs[:] = [d for d in dirs if not d.startswith('.') and d not in ['venv', 'venv_new', '__pycache__', 'build', 'dist']]
        
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        for pattern in forbidden_patterns:
                            if pattern in content:
                                violations.append(f"{filepath}: содержит '{pattern}'")
                except:
                    pass
    
    assert not violations, f"Найдены запрещённые импорты:\n" + "\n".join(violations)


def test_models_loaded_lazily():
    """Проверяет что sign_models.py использует ленивую загрузку."""
    with open("configs/sign_models.py", "r", encoding="utf-8") as f:
        content = f.read()
    
    # Должен использовать _LazyModel
    assert "_LazyModel" in content, "sign_models.py должен использовать _LazyModel"
    assert "model_side_detect = _LazyModel" in content, "model_side_detect должен быть ленивым"
    assert "rube_modal = _LazyModel" in content, "rube_modal должен быть ленивым"
    
    # Не должно быть прямых вызовов YOLO() на уровне модуля
    tree = ast.parse(content)
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "YOLO":
                # YOLO() вызов на уровне модуля - ПЛОХО
                if isinstance(node, ast.Module):
                    pytest.fail("Найден прямой вызов YOLO() на уровне модуля в sign_models.py")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
