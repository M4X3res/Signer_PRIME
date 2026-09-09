"""
scripts/diagnose_empty_geojson.py
Диагностика проблемы с пустым GeoJSON после обработки.
"""
import sys
import os
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_geojson(path):
    """Проверяет GeoJSON файл."""
    if not os.path.exists(path):
        print(f"[ERROR] Файл не существует: {path}")
        return False
    
    size = os.path.getsize(path)
    print(f"\n[INFO] Файл существует: {path}")
    print(f"[INFO] Размер файла: {size} bytes")
    
    if size == 0:
        print("[ERROR] Файл полностью пустой (0 bytes)!")
        return False
    
    try:
        with open(path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if not content.strip():
            print("[ERROR] Файл пустой (только пробелы)!")
            return False
        
        print(f"[INFO] Первые 200 символов:")
        print(content[:200])
        
        # Парсим JSON
        data = json.loads(content)
        
        if not isinstance(data, dict):
            print(f"[ERROR] GeoJSON не является объектом, тип: {type(data)}")
            return False
        
        print(f"\n[INFO] GeoJSON структура:")
        print(f"  - type: {data.get('type', 'MISSING')}")
        
        features = data.get('features', [])
        print(f"  - features: {len(features)}")
        
        if len(features) == 0:
            print("\n[WARNING] GeoJSON корректен, но НЕ СОДЕРЖИТ ЗНАКОВ!")
            print("[WARNING] Это означает что обработка НЕ нашла знаков, или произошла ошибка.")
            return False
        
        # Проверяем первый feature
        if features:
            first = features[0]
            print(f"\n[INFO] Первый знак:")
            print(f"  - type: {first.get('type', 'MISSING')}")
            print(f"  - geometry type: {first.get('geometry', {}).get('type', 'MISSING')}")
            props = first.get('properties', {})
            print(f"  - sign type: {props.get('type', 'MISSING')}")
            print(f"  - conf_total: {props.get('conf_total', 'MISSING')}")
        
        print(f"\n[SUCCESS] GeoJSON корректен, содержит {len(features)} знаков")
        return True
        
    except json.JSONDecodeError as e:
        print(f"[ERROR] Невалидный JSON: {e}")
        print(f"[ERROR] Позиция ошибки: строка {e.lineno}, колонка {e.colno}")
        return False
    except Exception as e:
        print(f"[ERROR] Ошибка при чтении: {e}")
        import traceback
        traceback.print_exc()
        return False

def check_logs():
    """Проверяет логи на наличие ошибок."""
    log_path = "roadscan.log"
    
    if not os.path.exists(log_path):
        print(f"\n[WARNING] Лог файл не найден: {log_path}")
        return
    
    print(f"\n[INFO] Проверка логов: {log_path}")
    
    with open(log_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = f.readlines()
    
    # Ищем последние 50 строк
    recent = lines[-50:]
    
    errors = []
    warnings = []
    important = []
    
    keywords_error = ['ERROR', 'ОШИБКА', 'Exception', 'Traceback', 'КРИТИЧЕСКАЯ']
    keywords_warning = ['WARNING', 'ВНИМАНИЕ', 'Failed', 'не удалось']
    keywords_important = [
        'save_result вызван',
        'прямолинейных знаков',
        'знаков на поворотах',
        'дедупликацию',
        'Сохраняем GeoJSON',
        'Сохранено'
    ]
    
    for line in recent:
        line_lower = line.lower()
        
        if any(kw.lower() in line_lower for kw in keywords_error):
            errors.append(line.strip())
        elif any(kw.lower() in line_lower for kw in keywords_warning):
            warnings.append(line.strip())
        elif any(kw in line for kw in keywords_important):
            important.append(line.strip())
    
    if errors:
        print(f"\n[ERROR] Найдено {len(errors)} ошибок в логах:")
        for err in errors[-10:]:  # Последние 10
            print(f"  {err}")
    
    if warnings:
        print(f"\n[WARNING] Найдено {len(warnings)} предупреждений:")
        for warn in warnings[-5:]:  # Последние 5
            print(f"  {warn}")
    
    if important:
        print(f"\n[INFO] Важные строки из логов:")
        for imp in important[-10:]:  # Последние 10
            print(f"  {imp}")
    
    if not errors and not warnings and not important:
        print("[INFO] Не найдено релевантных записей в последних 50 строках лога")

def main():
    print("="*70)
    print("ДИАГНОСТИКА ПУСТОГО GEOJSON")
    print("="*70)
    
    # 1. Проверяем config
    print("\n[1/3] Проверка конфигурации...")
    try:
        from configs import config
        
        geojson_path = config.PATH_TO_GEOJSON
        print(f"[INFO] Путь к GeoJSON из config: {geojson_path}")
        
        if not geojson_path:
            print("[ERROR] PATH_TO_GEOJSON не установлен в config!")
            print("[HINT] Проверьте что вы выбрали папку для сохранения результатов")
            return 1
        
    except Exception as e:
        print(f"[ERROR] Не удалось загрузить config: {e}")
        return 1
    
    # 2. Проверяем GeoJSON
    print("\n[2/3] Проверка GeoJSON файла...")
    geojson_ok = check_geojson(geojson_path)
    
    # 3. Проверяем логи
    print("\n[3/3] Проверка логов...")
    check_logs()
    
    # Итог
    print("\n" + "="*70)
    print("ДИАГНОЗ")
    print("="*70)
    
    if geojson_ok:
        print("\n[SUCCESS] GeoJSON в порядке, содержит знаки.")
        print("[INFO] Если на карте ничего не видно, проверьте:")
        print("  - Координаты знаков (возможно они за пределами видимой области)")
        print("  - Фильтры на карте (может быть скрыты определённые типы)")
        return 0
    else:
        print("\n[PROBLEM] GeoJSON пустой или повреждён!")
        print("\nВозможные причины:")
        print("  1. Обработка не нашла ни одного знака")
        print("     → Проверьте: пороги confidence, качество видео, наличие GPS")
        print("  2. Ошибка при обработке знаков")
        print("     → Проверьте логи выше на наличие Exception")
        print("  3. Ошибка при сохранении файла")
        print("     → Проверьте права на запись в папку результатов")
        print("  4. Процесс был прерван до завершения")
        print("     → Попробуйте обработать заново")
        
        print("\nРекомендуемые действия:")
        print("  1. Откройте roadscan.log и найдите последние записи FinalHandler")
        print("  2. Проверьте что видео содержит GPS-трек и знаки видны")
        print("  3. Попробуйте обработать короткий отрезок видео (30 сек)")
        print("  4. Проверьте Settings → пороги confidence (не слишком высокие?)")
        
        return 1

if __name__ == "__main__":
    sys.exit(main())
