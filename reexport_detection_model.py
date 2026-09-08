"""
Быстрый переэкспорт модели детекции с динамическим размером.
"""
import sys
import os

# Добавляем путь к проекту
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from ultralytics import YOLO

print("=" * 70)
print("ПЕРЕЭКСПОРТ МОДЕЛИ ДЕТЕКЦИИ С ДИНАМИЧЕСКИМ РАЗМЕРОМ")
print("=" * 70)

# Загружаем модель
model_path = "CNN_side/best.pt"
print(f"\n1. Загрузка модели: {model_path}")
model = YOLO(model_path, task="detect")

# Экспортируем в ONNX с dynamic=True
print(f"\n2. Экспорт в ONNX с dynamic=True...")
result = model.export(
    format="onnx",
    dynamic=True,
    simplify=True,
    opset=12
)
print(f"   ✅ Экспортировано: {result}")

# Проверяем размер входа
print(f"\n3. Проверка размера входа ONNX модели...")
import onnx
onnx_model = onnx.load(result)
for input_tensor in onnx_model.graph.input:
    print(f"   Name: {input_tensor.name}")
    shape = input_tensor.type.tensor_type.shape
    print(f"   Shape: ", end="")
    for dim in shape.dim:
        if dim.dim_value:
            print(f"{dim.dim_value}", end=" ")
        elif dim.dim_param:
            print(f"{dim.dim_param}", end=" ")
        else:
            print("dynamic", end=" ")
    print()

print("\n" + "=" * 70)
print("ГОТОВО! Теперь ONNX модель поддерживает динамический размер входа.")
print("=" * 70)
