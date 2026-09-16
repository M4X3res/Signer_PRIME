"""
Быстрый скрипт для конвертации моделей без вывода в консоль.
"""
import sys
import os

# Подавляем весь вывод
sys.stdout = open(os.devnull, 'w')
sys.stderr = open(os.devnull, 'w')

# Импортируем и запускаем экспорт
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from scripts.export_models_onnx import main, export_one, MODELS

# Конвертируем только критичные classify модели
classify_models = [(path, task) for path, task in MODELS if task == "classify"]

print(f"Starting export of {len(classify_models)} classify models...", file=sys.__stdout__)

success = 0
for pt_path, task in classify_models:
    try:
        result, export_path = export_one(pt_path, task, "onnx", force=False)
        if result:
            success += 1
            print(f"✓ {pt_path}", file=sys.__stdout__)
    except Exception as e:
        print(f"✗ {pt_path}: {e}", file=sys.__stdout__)

print(f"\nCompleted: {success}/{len(classify_models)} models", file=sys.__stdout__)
