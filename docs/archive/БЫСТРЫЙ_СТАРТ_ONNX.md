# 🚀 Быстрый старт: Использование ONNX в CPU режиме

## ✅ Шаг 1: Экспорт моделей (один раз)

```bash
# Экспорт всех моделей в ONNX с динамическим размером
.venv\Scripts\python.exe scripts\export_models_onnx.py --format onnx --force
```

**Время**: ~30-40 секунд для всех 18 моделей

## ✅ Шаг 2: Настройка приложения

1. Откройте приложение
2. Перейдите в Settings (⚙️)
3. Снимите галочку "Использовать CUDA"
4. В "CPU Inference Backend" выберите "ONNX"
5. Нажмите "Сохранить"

**ИЛИ** отредактируйте `settings.json`:
```json
{
  "use_cuda": false,
  "cpu_inference_backend": "onnx"
}
```

## ✅ Шаг 3: Запуск

1. **ВАЖНО**: Закройте и перезапустите приложение (если оно было открыто)
2. Выберите папку с видео
3. Нажмите "Start Processing"

## 📊 Ожидаемые результаты

### Производительность (CPU режим):
- **PyTorch**: ~10-15 FPS (baseline)
- **ONNX**: ~15-25 FPS (↑ 50-70% быстрее)
- **OpenVINO**: ~20-30 FPS (↑ 100-150% быстрее на Intel CPU)

### Логи (должны быть):
```
✅ CPU режим: ONNX Runtime будет использовать только CPU провайдеры
✅ [sign_models] CUDA выключена → используется onnx backend
✅ [sign_models] Device: cpu
✅ [sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
✅ [Worker] Загрузка моделей детектора...
✅ [Worker] Модели загружены
```

### Логи (НЕ должно быть):
```
❌ Error when binding input: copying tensors CUDA→CPU
❌ property 'device' of 'YOLO' object has no setter
❌ Got invalid dimensions for input: images. Got: 608 Expected: 960
```

## ⚠️ Типичные проблемы

### Проблема 1: "Got invalid dimensions"
**Причина**: Приложение не было перезапущено после экспорта
**Решение**: Закройте и запустите приложение заново

### Проблема 2: "ONNX-модель не найдена"
**Причина**: Модели не были экспортированы
**Решение**: Запустите Шаг 1 (экспорт моделей)

### Проблема 3: "Откат на PyTorch" в логах
**Причина**: ONNX модели повреждены или не найдены
**Решение**: 
```bash
# Принудительный переэкспорт
.venv\Scripts\python.exe scripts\export_models_onnx.py --format onnx --force
```

### Проблема 4: Медленная обработка
**Причина**: Неправильный режим обработки
**Решение**: 
1. Settings → Processing Mode → "process_pool"
2. Settings → Process Pool Workers → Установите 4-8 (по количеству ядер CPU)

## 🧪 Тестирование

### Быстрый тест загрузки:
```bash
.venv\Scripts\python.exe test_onnx_loading.py
```

### Проверка размера модели:
```bash
.venv\Scripts\python.exe check_onnx_input_size.py
```

### Проверка выбора backend:
```bash
.venv\Scripts\python.exe test_backend_selection.py
```

## 🔄 Переключение режимов

### ONNX (CPU) → CUDA (GPU):
1. Settings → Включить "Использовать CUDA"
2. Сохранить
3. Перезапустить приложение

### ONNX → OpenVINO (Intel CPU):
1. Экспорт OpenVINO моделей:
   ```bash
   .venv\Scripts\python.exe scripts\export_models_onnx.py --format openvino --force
   ```
2. Settings → CPU Inference Backend → "OpenVINO"
3. Перезапустить приложение

### ONNX → PyTorch (CPU fallback):
1. Settings → CPU Inference Backend → "torch"
2. Сохранить (перезапуск не нужен, т.к. .pt файлы всегда доступны)

## 📚 Документация

- **BACKEND_SELECTION_FIX.md** - Подробное описание исправлений backend
- **ONNX_DYNAMIC_SHAPE_FIX.md** - Исправление динамического размера
- **ONNX_QUICK_TEST.md** - Инструкции по тестированию
- **ВАЖНО_ПЕРЕЗАПУСК_ПОСЛЕ_ЭКСПОРТА.md** - Важная информация о перезапуске

## ✅ Checklist

- [ ] Модели экспортированы в ONNX
- [ ] use_cuda = False
- [ ] cpu_inference_backend = "onnx"
- [ ] Приложение перезапущено после экспорта
- [ ] В логах нет ошибок
- [ ] Обработка работает
