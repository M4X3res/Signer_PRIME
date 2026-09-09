"""
Скрипт для массовой замены print() на logging.

Анализирует Python файлы и предлагает замены print() на logger.*()
на основе контекста (ошибки → error, предупреждения → warning и т.д.)
"""
import re
import sys
from pathlib import Path
from typing import List, Tuple

# Паттерны для определения уровня логирования
PATTERNS = [
    (r'(?i)(error|ошибк|exception|failed|fail\b)', 'error'),
    (r'(?i)(warning|warn|предупрежд|внимание)', 'warning'),
    (r'(?i)(debug|отладк)', 'debug'),
    (r'(?i)(success|успех|завершен|готов|ok\b)', 'info'),
    (r'(?i)(запуск|start|load|создан|открыт)', 'info'),
]

def detect_log_level(text: str) -> str:
    """Определяет уровень логирования по содержимому строки."""
    for pattern, level in PATTERNS:
        if re.search(pattern, text):
            return level
    return 'info'  # По умолчанию

def find_print_statements(file_path: Path) -> List[Tuple[int, str, str, str]]:
    """
    Находит все print() в файле.
    
    Returns:
        List of (line_num, original_line, message, suggested_level)
    """
    results = []
    
    try:
        content = file_path.read_text(encoding='utf-8')
    except Exception as e:
        print(f"Ошибка чтения {file_path}: {e}")
        return results
    
    # Паттерн для поиска print()
    # Поддерживает: print("..."), print(f"..."), print(var), print("...", var)
    pattern = r'print\s*\((.*?)\)'
    
    lines = content.split('\n')
    for i, line in enumerate(lines, 1):
        # Пропускаем комментарии
        stripped = line.strip()
        if stripped.startswith('#'):
            continue
        
        # Ищем print()
        matches = re.finditer(pattern, line)
        for match in matches:
            message = match.group(1)
            level = detect_log_level(line)
            results.append((i, line, message, level))
    
    return results

def generate_replacement(original_line: str, message: str, level: str) -> str:
    """Генерирует замену для строки с print()."""
    indent = len(original_line) - len(original_line.lstrip())
    indent_str = ' ' * indent
    
    # Простая замена: print(...) → logger.level(...)
    replaced = re.sub(r'print\s*\(', f'logger.{level}(', original_line, count=1)
    return replaced

def process_file(file_path: Path, dry_run: bool = True):
    """Обрабатывает файл: находит print() и предлагает замены."""
    prints = find_print_statements(file_path)
    
    if not prints:
        return
    
    print(f"\n{'='*70}")
    print(f"Файл: {file_path}")
    print(f"Найдено print(): {len(prints)}")
    print('=' * 70)
    
    for line_num, original, message, level in prints:
        replacement = generate_replacement(original, message, level)
        
        print(f"\nСтрока {line_num}:")
        print(f"  ❌ {original.strip()}")
        print(f"  ✅ {replacement.strip()}")
        print(f"  📊 Уровень: {level.upper()}")
    
    if not dry_run:
        print(f"\n⚠️  Автоматическая замена пока не реализована")
        print("Используйте IDE для замены или отредактируйте вручную")

def analyze_project(root_dir: Path, dry_run: bool = True):
    """Анализирует все Python файлы в проекте."""
    python_files = list(root_dir.rglob('*.py'))
    
    # Исключаем некоторые директории
    exclude_dirs = {'venv', '.venv', '__pycache__', '.git', 'build', 'dist'}
    python_files = [
        f for f in python_files 
        if not any(ex in f.parts for ex in exclude_dirs)
    ]
    
    print(f"Найдено Python файлов: {len(python_files)}")
    print(f"Режим: {'DRY RUN (только анализ)' if dry_run else 'ЗАМЕНА'}")
    
    total_prints = 0
    files_with_prints = 0
    
    for file_path in sorted(python_files):
        prints = find_print_statements(file_path)
        if prints:
            files_with_prints += 1
            total_prints += len(prints)
            process_file(file_path, dry_run=dry_run)
    
    print(f"\n{'='*70}")
    print(f"ИТОГО:")
    print(f"  Файлов с print(): {files_with_prints}")
    print(f"  Всего print(): {total_prints}")
    print('=' * 70)
    
    if total_prints > 0:
        print("\nРЕКОМЕНДАЦИИ:")
        print("1. Добавьте в начало каждого файла:")
        print("   import logging")
        print("   logger = logging.getLogger(__name__)")
        print("\n2. Замените print() на logger.*() согласно рекомендациям выше")
        print("\n3. Основной logging.basicConfig() уже настроен в main.py")

if __name__ == "__main__":
    project_root = Path(__file__).parent.parent
    
    # Анализируем только core/, processing/, server/, ui/
    dirs_to_check = ['core', 'processing', 'server', 'ui']
    
    print("🔍 Анализ использования print() в проекте RoadScanner")
    print()
    
    for dir_name in dirs_to_check:
        dir_path = project_root / dir_name
        if dir_path.exists():
            analyze_project(dir_path, dry_run=True)
