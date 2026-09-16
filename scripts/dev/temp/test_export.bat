@echo off
rmdir /s /q small_models\blue_openvino_model 2>nul
.venv\Scripts\python.exe -c "from ultralytics import YOLO; model = YOLO('small_models/blue.pt'); result = model.export(format='openvino'); print(f'Done: {result}')"
dir small_models\blue_openvino_model
