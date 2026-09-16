"""
Минимальный тест конвертации одной модели.
"""
import sys
sys.path.insert(0, '.')

from ultralytics import YOLO
from app.utils import resource_path

# Конвертируем одну модель
pt_path = resource_path("small_models/blue.pt")
print(f"Loading {pt_path}...")

model = YOLO(pt_path, task="classify")
print("Exporting to ONNX...")

result = model.export(format="onnx", dynamic=True, simplify=True, opset=12)
print(f"✓ Exported: {result}")
