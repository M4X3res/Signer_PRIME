"""
scripts/build/test_obfuscation.py

Тестовый скрипт для проверки структуры PyArmor обфускации
БЕЗ полной пересборки через prepare_release.bat.

Использование:
    1. Запустите обфускацию: python scripts/build/obfuscate_licensing.py
    2. Запустите этот скрипт: python scripts/build/test_obfuscation.py
    3. Проверьте вывод - должны быть два runtime с правильными импортами
"""
import os
import sys
from pathlib import Path

# Настройка UTF-8 вывода для Windows консоли
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')


def check_runtime_structure():
    """Проверить структуру PyArmor runtime после обфускации."""
    
    root = Path(__file__).parent.parent.parent
    obf_dir = root / "build" / "obfuscated"
    
    print("=" * 70)
    print("PyArmor Runtime Structure Check")
    print("=" * 70)
    print()
    
    if not obf_dir.exists():
        print("ERROR: build/obfuscated/ не найдена")
        print("Запустите сначала: python scripts/build/obfuscate_licensing.py")
        return 1
    
    print(f"Checking: {obf_dir}")
    print()
    
    # Ищем все pyarmor_runtime директории
    runtime_dirs = []
    for item in obf_dir.rglob("pyarmor_runtime_*"):
        if item.is_dir():
            rel_path = item.relative_to(obf_dir)
            runtime_dirs.append((item, rel_path))
    
    if not runtime_dirs:
        print("ERROR: Не найдено ни одного pyarmor_runtime_*")
        return 1
    
    print(f"Found {len(runtime_dirs)} runtime director{'y' if len(runtime_dirs) == 1 else 'ies'}:")
    print()
    
    expected_count = 2
    if len(runtime_dirs) != expected_count:
        print(f"WARNING: Expected {expected_count} runtimes, found {len(runtime_dirs)}")
    
    # Проверяем каждый runtime
    root_runtime_found = False
    nested_runtime_found = False
    
    for rt_dir, rel_path in runtime_dirs:
        parts = rel_path.parts
        is_root = len(parts) == 1
        
        print("-" * 70)
        print(f"Runtime: {rel_path}")
        print(f"Type: {'ROOT (for main.py)' if is_root else 'NESTED (for licensing/*)'}")
        print(f"Full path: {rt_dir}")
        print()
        
        # Проверяем __init__.py
        init_file = rt_dir / "__init__.py"
        if not init_file.exists():
            print("ERROR: __init__.py not found")
            continue
        
        # Читаем первые строки __init__.py
        with open(init_file, 'r', encoding='utf-8') as f:
            first_lines = [f.readline().strip() for _ in range(10)]
        
        print("__init__.py (first 10 lines):")
        for i, line in enumerate(first_lines, 1):
            if line:
                print(f"  {i}: {line}")
        print()
        
        # Анализируем импорты
        has_relative_import = any('from ..' in line or 'from .' in line for line in first_lines)
        has_absolute_import = any('from pyarmor_runtime' in line for line in first_lines)
        
        if is_root:
            root_runtime_found = True
            print("Expected: Absolute import or self-contained implementation")
            if has_relative_import and not has_absolute_import:
                print("PROBLEM: Contains relative import (should be absolute/self-contained)")
            else:
                print("OK: Appears to be correct root runtime")
        else:
            nested_runtime_found = True
            print("Expected: Relative import or self-contained (for nested module)")
            print("OK: Nested runtime structure")
        
        print()
    
    print("=" * 70)
    print("Summary")
    print("=" * 70)
    
    issues = []
    
    if not root_runtime_found:
        issues.append("ERROR: Root runtime (pyarmor_runtime_*/) not found")
    else:
        print("OK: Root runtime found")
    
    if not nested_runtime_found:
        issues.append("ERROR: Nested runtime (licensing/pyarmor_runtime_*/) not found")
    else:
        print("OK: Nested runtime found")
    
    if issues:
        print()
        for issue in issues:
            print(issue)
        return 1
    
    print()
    print("SUCCESS: Structure looks correct!")
    print()
    print("Next steps:")
    print("  1. Check the import patterns above match expectations")
    print("  2. Run full build: scripts\\build\\prepare_release.bat")
    print("  3. Test the built executable: dist\\Signer\\Signer.exe")
    
    return 0


if __name__ == "__main__":
    sys.exit(check_runtime_structure())
