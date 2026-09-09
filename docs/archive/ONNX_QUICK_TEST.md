# Проверка работы ONNX моделей - Quick Test

## Быстрая проверка

### 1. Проверка выбора backend
```bash
.venv\Scripts\python.exe test_backend_selection.py
```

**Ожидаемый результат для CPU режима:**
```
use_cuda: False
cpu_inference_backend: onnx
Определённый device: cpu
Определённый backend: onnx
✅ КОРРЕКТНО: Используется onnx backend на CPU
ORT_DISABLE_CUDA: 1
```

### 2. Проверка загрузки ONNX моделей
```bash
.venv\Scripts\python.exe test_onnx_loading.py
```

**Ожидаемый результат:**
```
Тест 1: Загрузка model_side_detect...
  [sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
  ✅ model_side_detect загружена: backend=onnx

Тест 2: Загрузка rube_modal...
  [sign_models] Загружена ONNX-модель: rude.onnx (CPU mode)
  ✅ rube_modal загружена: backend=onnx

Тест 3: Проверка ONNX файлов...
  CNN_side/best.onnx: ✅ существует
  small_models/rude.onnx: ✅ существует
```

## Переключение режимов

### Включить CUDA (использовать GPU с PyTorch моделями)
1. Открыть настройки в приложении
2. Включить "Использовать CUDA"
3. Перезапустить обработку

**Или** изменить в `settings.json`:
```json
{
  "use_cuda": true
}
```

### Включить CPU с ONNX
1. Открыть настройки в приложении
2. Выключить "Использовать CUDA"
3. Выбрать "ONNX" в "CPU Inference Backend"
4. Перезапустить обработку

**Или** изменить в `settings.json`:
```json
{
  "use_cuda": false,
  "cpu_inference_backend": "onnx"
}
```

### Включить CPU с OpenVINO
```json
{
  "use_cuda": false,
  "cpu_inference_backend": "openvino"
}
```

### Включить CPU с PyTorch (fallback)
```json
{
  "use_cuda": false,
  "cpu_inference_backend": "torch"
}
```

## Проверка логов в приложении

После запуска обработки смотрите в `roadscan.log`:

### ✅ Успешная работа ONNX:
```
[INFO] __main__: CPU режим: ONNX Runtime будет использовать только CPU провайдеры
[DEBUG] configs.sign_models: [sign_models] CUDA выключена → используется onnx backend
[DEBUG] configs.sign_models: [sign_models] Device: cpu
[INFO] configs.sign_models: [sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
[DEBUG] configs.sign_models: [sign_models] ONNX predict: явно установлен device=cpu
```

### ✅ Успешная работа CUDA:
```
[DEBUG] configs.sign_models: [sign_models] CUDA включена → используется PyTorch backend
[DEBUG] configs.sign_models: [sign_models] Device: cuda:0 (CUDA доступна)
[INFO] configs.sign_models: [sign_models] Загружена PyTorch-модель: best.pt на device=cuda:0
```

### ❌ Проблемы (не должно быть):
- `Error when binding input: There's no data transfer registered`
- `property 'device' of 'YOLO' object has no setter`
- Warning'и о недоступности CUDA providers при CPU режиме

## Экспорт моделей в ONNX/OpenVINO

Если ONNX/OpenVINO модели отсутствуют:

```bash
# Экспорт в ONNX
python scripts/export_models_onnx.py --format onnx

# Экспорт в OpenVINO
python scripts/export_models_onnx.py --format openvino

# Экспорт только detection моделей
python scripts/export_models_onnx.py --format onnx --models detect

# Принудительный переэкспорт
python scripts/export_models_onnx.py --format onnx --force
```

## Troubleshooting

### Проблема: "ONNX-модель не найдена"
**Решение**: Запустите экспорт моделей (см. выше)

### Проблема: "Откат на PyTorch" в логах
**Причина**: ONNX модели не найдены или повреждены
**Решение**: Переэкспортируйте модели с `--force`

### Проблема: Низкая производительность на CPU
**Решение**: Используйте ONNX или OpenVINO вместо PyTorch на CPU
- ONNX: универсальный, хорошая производительность
- OpenVINO: максимальная производительность на Intel CPU

### Проблема: Worker процессы вылетают
**Причина**: Возможно недостаточно памяти
**Решение**: 
1. Уменьшите количество worker процессов в настройках
2. Используйте режим "single_thread" вместо "process_pool"
