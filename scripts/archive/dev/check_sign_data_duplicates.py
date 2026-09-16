"""
Скрипт для проверки дублирующихся ключей в configs/sign_data.py.

Парсит файл через AST, находит все словари и проверяет на дублирующиеся ключи.
"""
import ast
import sys
from pathlib import Path

def check_dict_duplicates(dict_node, dict_name):
    """Проверяет дубликаты ключей в AST узле Dict."""
    keys = []
    duplicates = []
    
    for i, key in enumerate(dict_node.keys):
        if isinstance(key, ast.Constant):
            key_value = key.value
            
            # Ищем дубликаты
            for j, existing_key in enumerate(keys):
                if existing_key == key_value:
                    value = dict_node.values[i]
                    old_value = dict_node.values[j]
                    
                    # Получаем значения
                    if isinstance(value, ast.Constant):
                        val_str = repr(value.value)
                    else:
                        val_str = ast.unparse(value)
                    
                    if isinstance(old_value, ast.Constant):
                        old_val_str = repr(old_value.value)
                    else:
                        old_val_str = ast.unparse(old_value)
                    
                    duplicates.append({
                        'key': key_value,
                        'first_value': old_val_str,
                        'first_line': old_value.lineno,
                        'second_value': val_str,
                        'second_line': value.lineno,
                    })
                    break
            
            keys.append(key_value)
    
    return duplicates

def analyze_sign_data():
    """Анализирует configs/sign_data.py на дубликаты."""
    sign_data_path = Path(__file__).parent.parent / "configs" / "sign_data.py"
    
    if not sign_data_path.exists():
        print(f"❌ Файл не найден: {sign_data_path}")
        return False
    
    print(f"🔍 Анализ файла: {sign_data_path}")
    print()
    
    # Читаем и парсим файл
    source = sign_data_path.read_text(encoding='utf-8')
    try:
        tree = ast.parse(source, filename=str(sign_data_path))
    except SyntaxError as e:
        print(f"❌ Ошибка парсинга: {e}")
        return False
    
    # Ищем все словари на уровне модуля
    found_issues = False
    
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            # Получаем имя переменной
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                var_name = node.targets[0].id
                
                # Проверяем, это словарь?
                if isinstance(node.value, ast.Dict):
                    duplicates = check_dict_duplicates(node.value, var_name)
                    
                    if duplicates:
                        found_issues = True
                        print(f"⚠️  Словарь '{var_name}' содержит дубликаты ключей:")
                        print()
                        
                        for dup in duplicates:
                            print(f"   Ключ: {repr(dup['key'])}")
                            print(f"   • Строка {dup['first_line']}: {dup['first_value']}")
                            print(f"   • Строка {dup['second_line']}: {dup['second_value']} (ПЕРЕЗАПИШЕТ первое!)")
                            print()
    
    if not found_issues:
        print("✅ Дубликатов ключей не найдено!")
        return True
    else:
        print("❌ Найдены дубликаты ключей! Требуется ручное исправление.")
        return False

if __name__ == "__main__":
    success = analyze_sign_data()
    sys.exit(0 if success else 1)
