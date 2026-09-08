# Исправление выбора Backend для моделей (CUDA vs CPU) - Исправление ONNX

## Проблема

При использовании ONNX моделей в CPU режиме (`use_cuda=False`) возникала ошибка:
```
Error when binding input: There's no data transfer registered for copying tensors from 
Device:[DeviceType:1 MemoryType:0] (CUDA) to Device:[DeviceType:0 MemoryType:0] (CPU)
```

Это происходило по двум причинам:
1. Переменная окружения `ORT_DISABLE_CUDA` была жёстко прописана в `main.py` независимо от настройки `use_cuda`
2. Worker процессы (multiprocessing) не наследовали правильные настройки окружения
3. ONNX Runtime пытался использовать CUDA provider даже при явном отключении
4. Тензоры создавались на CUDA device вместо CPU

## Решение

### 1. Исправлен `main.py` - главный процесс

Переменная окружения `ORT_DISABLE_CUDA` теперь устанавливается **условно**:

```python
def setup_environment():
    # ...
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if not settings.use_cuda:
            # В CPU режиме отключаем CUDA провайдеры для ONNX Runtime
            os.environ["ORT_DISABLE_CUDA"] = "1"
            logger.info("CPU режим: ONNX Runtime будет использовать только CPU провайдеры")
    except Exception:
        # Если настройки недоступны, по умолчанию отключаем CUDA для ONNX
        os.environ.setdefault("ORT_DISABLE_CUDA", "1")
```

### 2. Исправлен `main.py` - worker процессы

Добавлена настройка `ORT_DISABLE_CUDA` для worker процессов **ДО** любых импортов:

```python
else:
    # Worker процессы
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    
    # BLOCK M: По умолчанию отключаем CUDA для ONNX в worker процессах
    os.environ.setdefault("ORT_DISABLE_CUDA", "1")
```

### 3. Исправлен `detector_process_pool.py` - worker функция

Добавлена настройка `ORT_DISABLE_CUDA` в начале функции `_worker_process_frame`:

```python
def _worker_process_frame(raw_frame_data: dict) -> dict:
    import os
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    # ...
    
    # BLOCK M: Настройка ONNX Runtime для CPU режима
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if not settings.use_cuda:
            os.environ["ORT_DISABLE_CUDA"] = "1"
    except Exception:
        os.environ.setdefault("ORT_DISABLE_CUDA", "1")
```

### 4. Усилена защита в `sign_models.py`

**A. Исправлена загрузка ONNX (убрана попытка установки read-only свойства):**

```python
# Загружаем модель
self._model = YOLO(onnx_path, task=self._task)

# Принудительно устанавливаем CPU device для predictor
# (не для самой модели, т.к. device - read-only property)
import torch
if hasattr(self._model, 'predictor') and self._model.predictor:
    self._model.predictor.device = torch.device("cpu")
```

**ВАЖНО**: У объекта `YOLO` свойство `device` является read-only property и не может быть установлено напрямую. Мы устанавливаем device только для predictor.

**B. Улучшен метод predict с установкой device после создания predictor:**

```python
def predict(self, *args, **kwargs):
    model = self._load()
    # Для ONNX backend принудительно указываем device=cpu
    if self._backend == "onnx" and 'device' not in kwargs:
        kwargs['device'] = 'cpu'
    
    # Вызываем predict
    result = model.predict(*args, **kwargs)
    
    # После первого вызова predictor создан, устанавливаем device
    if self._backend == "onnx" and hasattr(model, 'predictor') and model.predictor:
        import torch
        try:
            model.predictor.device = torch.device("cpu")
        except Exception:
            pass  # Игнорируем ошибки, device уже может быть установлен
    
    return result
```

**C. Улучшено логирование:**
- `_resolve_device()` - логирует выбранный device
- `_resolve_backend()` - логирует выбранный backend
- `_load()` - логирует загрузку каждой модели с указанием типа и device

## Как это работает

### При включенном CUDA (`use_cuda=True`)

1. **Device**: `cuda:0` (если CUDA доступна) или `cpu` (если недоступна)
2. **Backend**: `torch` (всегда)
3. **Модели**: Загружаются старые `.pt` файлы
4. **ONNX Runtime**: Не задействуется, переменная `ORT_DISABLE_CUDA` **не устанавливается**

**Пример лога:**
```
[sign_models] CUDA включена → используется PyTorch backend
[sign_models] Device: cuda:0 (CUDA доступна)
[sign_models] Загружена PyTorch-модель: best.pt на device=cuda:0
```

### При выключенном CUDA (`use_cuda=False`)

1. **Device**: `cpu` (всегда)
2. **Backend**: Определяется настройкой `cpu_inference_backend`:
   - `"torch"` - PyTorch на CPU (старые `.pt` файлы)
   - `"onnx"` - ONNX Runtime (требует `.onnx` файлы)
   - `"openvino"` - OpenVINO (требует `.xml` файлы)
3. **Модели**: Загружаются в соответствии с выбранным backend
4. **ONNX Runtime**: Устанавливается `ORT_DISABLE_CUDA=1` в **трёх местах**:
   - Главный процесс (setup_environment)
   - Worker процессы (main.py)
   - Worker функция (detector_process_pool.py)
5. **Device enforcement**: При использовании ONNX явно устанавливается `device=cpu` при загрузке и при вызове predict

**Пример лога (ONNX):**
```
CPU режим: ONNX Runtime будет использовать только CPU провайдеры
[sign_models] CUDA выключена → используется onnx backend
[sign_models] Device: cpu
[sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
[sign_models] ONNX predict: явно установлен device=cpu
```

## Тестирование

Создан тестовый скрипт `test_backend_selection.py` для проверки логики:

```bash
.venv\Scripts\python.exe test_backend_selection.py
```

Скрипт проверяет:
1. Доступность CUDA
2. Текущие настройки (`use_cuda`, `cpu_inference_backend`)
3. Определённый device
4. Определённый backend
5. Значение переменной `ORT_DISABLE_CUDA`
6. Соответствие ожидаемому поведению

## Файлы изменены

1. **main.py** 
   - Условная установка `ORT_DISABLE_CUDA` в главном процессе
   - Установка `ORT_DISABLE_CUDA` для worker процессов
2. **processing/detector_process_pool.py**
   - Установка `ORT_DISABLE_CUDA` в функции `_worker_process_frame`
3. **configs/sign_models.py**
   - Улучшенное логирование выбора device и backend
   - Принудительная установка CPU device при загрузке ONNX
   - Явное указание `device=cpu` при вызове predict для ONNX
4. **test_backend_selection.py** - новый тестовый скрипт (создан)
5. **BACKEND_SELECTION_FIX.md** - эта документация

## Критические моменты

### Порядок установки переменных окружения

Переменная `ORT_DISABLE_CUDA` **должна быть установлена ДО** первого импорта `onnxruntime` (который происходит косвенно через `ultralytics`). Поэтому:

1. В главном процессе - устанавливается в `setup_environment()` перед импортом любых модулей
2. В worker процессах - устанавливается на самом верхнем уровне `main.py` в секции `else`
3. В worker функции - устанавливается в самом начале `_worker_process_frame` перед импортом detector

### Multiprocessing на Windows

Windows использует **spawn** для создания новых процессов (не fork как на Linux), поэтому:
- Worker процессы не наследуют переменные окружения автоматически
- Нужно явно устанавливать их в нескольких местах
- `freeze_support()` обязателен для работы multiprocessing в замороженных приложениях

### ONNX Runtime Providers

ONNX Runtime по умолчанию пытается использовать все доступные providers в порядке:
1. `CUDAExecutionProvider` (если CUDA доступна)
2. `TensorRTExecutionProvider` (если TensorRT доступен)
3. `CPUExecutionProvider` (fallback)

Установка `ORT_DISABLE_CUDA=1` отключает попытки использования CUDA/TensorRT providers.

## Рекомендации

### Для работы с CUDA (GPU):
1. Установите `use_cuda: True` в настройках
2. Убедитесь, что CUDA доступна (`torch.cuda.is_available()`)
3. Приложение автоматически загрузит `.pt` модели на GPU

### Для работы на CPU:
1. Установите `use_cuda: False` в настройках
2. Выберите предпочитаемый `cpu_inference_backend`:
   - `"torch"` - если не экспортировали модели в ONNX/OpenVINO
   - `"onnx"` - для ускоренного CPU инференса (требует экспорт)
   - `"openvino"` - для максимальной производительности на Intel CPU (требует экспорт)
3. Для экспорта моделей запустите:
   ```bash
   python scripts/export_models_onnx.py --format onnx
   # или
   python scripts/export_models_onnx.py --format openvino
   ```

## Проверка работоспособности

После запуска приложения проверьте логи:

**Успешная работа ONNX на CPU:**
```
10:05:08 [INFO] __main__: CPU режим: ONNX Runtime будет использовать только CPU провайдеры
10:05:10 [DEBUG] configs.sign_models: [sign_models] CUDA выключена → используется onnx backend
10:05:10 [DEBUG] configs.sign_models: [sign_models] Device: cpu
10:05:12 [INFO] configs.sign_models: [sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
10:05:15 [DEBUG] configs.sign_models: [sign_models] ONNX predict: явно установлен device=cpu
```

**Не должно быть:**
- ❌ Ошибок "Error when binding input: There's no data transfer registered"
- ❌ Warning'ов о недоступности CUDA providers
- ❌ Попыток копирования тензоров CUDA→CPU
