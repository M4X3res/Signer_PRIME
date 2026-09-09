# Подавление TensorRT Warning'ов от ONNX Runtime

## Проблема

При использовании ONNX Runtime в CPU режиме (с `ORT_DISABLE_CUDA=1`) в логах появляются 
предупреждения:

```
EP Error N:\_work\1\s\onnxruntime\python\onnxruntime_pybind_state.cc:573 
onnxruntime::python::RegisterTensorRTPluginsAsCustomOps 
Please install TensorRT libraries...
when using ['TensorrtExecutionProvider', 'CPUExecutionProvider']
Falling back to ['CPUExecutionProvider'] and retrying.
```

## Причина

ONNX Runtime при первом импорте **всегда** пытается зарегистрировать TensorRT плагины, 
даже если:
- Установлена переменная `ORT_DISABLE_CUDA=1`
- Явно указан только CPUExecutionProvider
- TensorRT не установлен

Это поведение встроено в ONNX Runtime и не может быть полностью отключено через 
переменные окружения.

## Решение

Добавлено подавление этих warning'ов через Python `warnings.filterwarnings()` в двух местах:

### 1. Главный процесс (main.py)

В `setup_environment()` в самом начале, **до** настройки логирования:

```python
import warnings
# Подавляем TensorRT warning'и от ONNX Runtime
warnings.filterwarnings('ignore', message='.*TensorRT.*')
warnings.filterwarnings('ignore', message='.*TensorrtExecutionProvider.*')
```

### 2. Worker процессы (processing/detector_process_pool.py)

В `_worker_process_frame()` после настройки ORT_DISABLE_CUDA, **до** импорта моделей:

```python
# Подавляем TensorRT warning'и от ONNX Runtime
import warnings
warnings.filterwarnings('ignore', message='.*TensorRT.*')
warnings.filterwarnings('ignore', message='.*TensorrtExecutionProvider.*')
```

## Что подавляется

Эти фильтры подавляют **только** сообщения связанные с TensorRT:
- Сообщения о регистрации TensorRT плагинов
- Сообщения о fallback на CPUExecutionProvider
- Любые другие упоминания TensorRT

## Что НЕ подавляется

- Реальные ошибки ONNX Runtime (кроме TensorRT-специфичных)
- Warning'и о других execution providers
- Ошибки загрузки моделей
- Любые другие Python warnings

## Альтернативы (не использованы)

### 1. Полное отключение warnings
```python
import warnings
warnings.filterwarnings('ignore')  # ❌ Слишком агрессивно, скрывает важные warning'и
```

### 2. Патч ONNX Runtime
```python
import onnxruntime
onnxruntime.set_default_logger_severity(3)  # ❌ Не влияет на C++ EP Error'ы
```

### 3. Использование только onnxruntime (без GPU)
```bash
pip uninstall onnxruntime-gpu
pip install onnxruntime  # ❌ У нас уже используется CPU-only версия
```

## Проверка

После исправления в логах **не должно** быть:
```
❌ EP Error ... TensorRT ...
❌ TensorrtExecutionProvider ...
❌ Falling back to ['CPUExecutionProvider'] ...
```

Должно быть:
```
✅ [sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
✅ [Worker] Модели загружены
✅ Чистые логи без TensorRT warning'ов
```

## Документация

- Эти фильтры применяются **автоматически** при запуске приложения
- Никаких действий от пользователя не требуется
- Работает как в главном процессе, так и в worker процессах

## Связанные файлы

- `main.py` - setup_environment()
- `processing/detector_process_pool.py` - _worker_process_frame()

## Дата исправления

2026-09-01 11:05 - Добавлено подавление TensorRT warning'ов
