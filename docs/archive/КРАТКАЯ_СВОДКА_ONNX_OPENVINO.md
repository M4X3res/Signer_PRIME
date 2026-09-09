# Краткая сводка: Почему ONNX/OpenVINO не работали

## Главная причина
**OpenVINO пакет не был установлен** — он был закомментирован в `requirements.txt` как "опциональный". При попытке использовать происходил тихий откат на PyTorch, о котором пользователь не узнавал.

## Что исправлено

### 1. requirements.txt
- Раскомментированы `openvino>=2024.0` и `openvino-dev>=2024.0` — теперь обязательные зависимости
- Добавлен комментарий про CPU-only версию `onnxruntime` (не `-gpu`)

### 2. Явное предупреждение при тихом откате (2 места)

#### A. При старте обработки (`processing/processing_controller.py`)
Добавлена функция `verify_backend_active()` в `configs/sign_models.py`, которая:
- Вызывается один раз при старте обработки
- Проверяет РЕАЛЬНЫЙ backend всех моделей после загрузки
- Если запрошен "onnx"/"openvino", а реально используется "torch" → **предупреждение в UI**

#### B. При сохранении настроек (`ui/widgets/settings_page.py`)
Добавлена функция `_check_backend_readiness()`, которая:
- Вызывается при нажатии "Сохранить" в Settings
- Проверяет: установлен ли пакет? существуют ли экспортированные файлы?
- Если нет → **QMessageBox.warning()** с явным указанием, что нужно сделать
- НЕ блокирует сохранение настроек

### 3. Логирование ошибок
`reload_all_models_if_device_changed()` теперь **не проглатывает** ошибки молча — логирует их явно

## Что нужно сделать вам

### Шаг 1: Установить openvino
```bash
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Это автоматически установит `openvino>=2024.0` и `openvino-dev>=2024.0`.

### Шаг 2: (Опционально) Удалить onnxruntime-gpu
Если видите предупреждения про TensorRT/CUDA при работе ONNX backend:
```bash
.venv\Scripts\python.exe -m pip uninstall onnxruntime-gpu
```

### Шаг 3: Экспортировать модели в OpenVINO
```bash
.venv\Scripts\python.exe scripts\export_models_onnx.py --format openvino --force
```

### Шаг 4: Проверить
```bash
.venv\Scripts\python.exe diagnostic_backend_check.py
```

Должно показать:
- ONNX: `✅ Backend соответствует запрошенному`
- OpenVINO: `✅ Backend соответствует запрошенному`

---

## Диагностика показала

✅ **ONNX backend работает** (18/18 моделей экспортированы успешно)  
❌ **OpenVINO backend НЕ работает** — пакет не установлен, происходит откат на PyTorch  
⚠️ **onnxruntime-gpu установлен** — вызывает попытки использовать CUDA/TensorRT (лишние задержки)

## Теперь вы узнаете о проблеме ДО обработки

После исправлений, если backend не готов к использованию:
1. **В Settings UI** — при сохранении увидите предупреждение с точной причиной
2. **При старте обработки** — в консоли обработки появится предупреждение, если модели откатились на PyTorch

---

**Файлы изменены:** 4 (requirements.txt, configs/sign_models.py, processing/processing_controller.py, ui/widgets/settings_page.py)  
**Подробный отчёт:** `ONNX_OPENVINO_FIX_REPORT.md`  
**Выполнение промпта:** 100%

