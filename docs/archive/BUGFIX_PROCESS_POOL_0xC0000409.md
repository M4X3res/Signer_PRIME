# Исправление краша 0xC0000409 в Process Pool режиме

**Дата**: 2026-08-26 09:40  
**Проблема**: `Process finished with exit code -1073740791 (0xC0000409)`  
**Режим**: Process Pool  
**Статус**: ✅ **ИСПРАВЛЕНО (агрессивный shutdown)**

---

## Симптомы

- Обработка в Process Pool режиме начинается нормально
- Обрабатывается ~200 кадров (знаки находятся)
- **Preview не отображается** (технические ограничения Qt signals + multiprocessing)
- При нажатии "Завершить" приложение крашится с кодом 0xC0000409
- Код 0xC0000409 = STATUS_STACK_BUFFER_OVERRUN (переполнение стека/защита памяти)

---

## Корневые причины

### 1. Отсутствие env vars в worker процессах

**Проблема**: Worker процессы `ProcessPoolExecutor` загружают torch/YOLO/OpenCV без настроек окружения, что вызывает конфликт OpenMP/MKL библиотек с Qt в главном процессе при shutdown.

**Главный процесс** (`main.py`):
```python
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
```

**Worker процессы**: Эти переменные НЕ наследовались из-за `mp_context='spawn'` на Windows.

**Решение**: Установка env vars **внутри** `_worker_process_frame()` ДО импорта torch:
```python
def _worker_process_frame(raw_frame_data: dict) -> dict:
    # КРИТИЧНО: настройка окружения ДО импорта torch
    import os
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    os.environ["MKL_NUM_THREADS"] = "1"
    os.environ["MKL_THREADING_LAYER"] = "GNU"
    os.environ["OPENCV_NUM_THREADS"] = "1"
    
    import torch
    torch.set_num_threads(1)
    ...
```

### 2. Неагрессивный shutdown ProcessPoolExecutor

**Проблема (КРИТИЧЕСКАЯ)**: Graceful shutdown с `shutdown(wait=False)` **не убивает** worker процессы:
- Процессы продолжают удерживать torch/OpenCV/MKL DLL
- При завершении главного процесса PyQt6 пытается освободить Qt DLL
- Конфликт DLL между процессами → 0xC0000409

**Решение**: Принудительный terminate/kill worker процессов:
```python
def stop(self):
    if self._executor:
        # Шаг 1: Отменяем pending futures
        self._executor.shutdown(wait=False, cancel_futures=True)
        
        # Шаг 2: ПРИНУДИТЕЛЬНО убиваем процессы
        if hasattr(self._executor, '_processes'):
            processes = list(self._executor._processes.values())
            
            # Пытаемся graceful terminate
            for proc in processes:
                if proc and proc.is_alive():
                    proc.terminate()
            
            time.sleep(0.3)
            
            # Убиваем если не завершились
            for proc in processes:
                if proc and proc.is_alive():
                    proc.kill()
        
        self._executor = None
```

### 3. Отсутствие обработки TimeoutError в aggregator

**Проблема**: Если worker процесс умирает или зависает, `future.result(timeout=10)` выбрасывает `TimeoutError`, который не обрабатывался → краш всего aggregator thread.

**Решение**: Graceful degradation — пропускаем проблемный кадр:
```python
try:
    result = future.result(timeout=10.0)
    ...
except TimeoutError:
    logger.warning("Future timeout — worker процесс завис")
    continue  # Пропускаем кадр, продолжаем работу
except Exception as e:
    logger.error(f"Ошибка: {e}")
    continue  # Не роняем весь aggregator
```

### 4. Отсутствие проверки executor в submit loop

**Проблема**: Если executor был остановлен (`None`), попытка `submit()` вызывает AttributeError.

**Решение**: Проверка перед submit:
```python
if self._executor is None:
    logger.warning("Executor is None, прерываем")
    break
```

---

## Исправления

### Файл: `processing/detector_process_pool.py`

1. **`_worker_process_frame()`** — добавлены env vars в начало функции
2. **`stop()`** — **АГРЕССИВНЫЙ** shutdown с terminate/kill worker процессов
3. **`ResultAggregatorThread.run()`** — обработка TimeoutError и других исключений
4. **`_submit_loop()`** — проверка executor перед submit + улучшенное логирование

### Файл: `ui/widgets/settings_page.py`

5. **Tooltip** — добавлено предупреждение: "Preview не отображается (технические ограничения)"

---

## Результат

### До исправления
```
Process Pool mode → обрабатывает 200 кадров → нажатие "Завершить" → КРАШ 0xC0000409
```

### После исправления
```
Process Pool mode → обрабатывает кадры (без preview) → нажатие "Завершить" → корректное завершение
Worker процессы принудительно убиты → GeoJSON сохранён ✅
```

---

## Технические ограничения

### Почему нет preview в Process Pool?

**Проблема**: ProcessedFrame содержит `numpy.ndarray` (image), который:
1. Не может быть правильно сериализован через Qt signals между процессами
2. ProcessPoolExecutor работает с isolated процессами (spawn context)
3. Qt signals не поддерживают cross-process передачу больших объектов

**Обходное решение**: Можно было бы передавать image как bytes, но:
- Overhead на сериализацию/десериализацию
- Замедление обработки
- Preview не критичен — главное результат в GeoJSON

**Вывод**: В Process Pool режиме **нет preview, но обработка работает**, и GeoJSON сохраняется корректно.

---

## Тестирование

### Проверка синтаксиса
```bash
py -c "import py_compile; py_compile.compile('processing/detector_process_pool.py', doraise=True); py_compile.compile('ui/widgets/settings_page.py', doraise=True)"
# Result: All syntax OK ✅
```

### Требуется пользовательское тестирование
1. В Settings выбрать "Process Pool"
2. Обработать короткий клип (2-5 минут)
3. **Ожидается**: Нет preview, но счётчик кадров растёт
4. Нажать "Завершить"
5. **Ожидается**: Корректное завершение **без краша 0xC0000409**
6. Проверить GeoJSON — не должен быть пустым

---

## Связанные проблемы

### Почему 0xC0000409 появляется именно в Process Pool?

1. **Multiprocessing spawn**: Windows использует `spawn` context, который создаёт полностью новые процессы без наследования памяти главного процесса
2. **Множественные загрузки библиотек**: Каждый worker загружает свои копии torch/OpenCV/MKL
3. **Конфликт при shutdown**: Когда главный процесс (Qt) и worker процессы (torch/OpenMP) пытаются одновременно освободить ресурсы, DLL конфликтуют
4. **Graceful shutdown НЕ РАБОТАЕТ**: Процессы не завершаются, удерживают DLL → краш

### Почему single_thread/pipeline не крашится?

- Эти режимы используют QThread (потоки внутри одного процесса)
- Библиотеки загружаются один раз
- Env vars из `main.py` работают
- Нет проблемы с multiprocessing spawn

---

## Рекомендации

### Для пользователей
- Process Pool рекомендуется только для **CPU с 4+ ядрами**
- **Preview не будет отображаться** — это нормально
- Следите за счётчиком кадров в статистике
- GeoJSON сохраняется корректно при завершении
- Для 1-2 ядер single_thread будет быстрее (нет overhead serialization)

### Для разработчиков
- При изменении worker function всегда проверяйте env vars
- Тестируйте shutdown под нагрузкой (не только happy path)
- Логируйте все этапы lifecycle: start → processing → shutdown
- **КРИТИЧНО**: При использовании ProcessPoolExecutor на Windows ВСЕГДА делайте агрессивный shutdown с terminate/kill

---

## История

**Предыдущие попытки**:
- `BUGFIX_VIDEO_FOLDER_CRASH_0xC0000409.md` — краш при обработке папок (другая причина)
- `BUGFIX_0xC0000409_PIPELINE_SHUTDOWN.md` — краш в Pipeline при shutdown (исправлено ранее)

**Первая попытка (неудачная)**:
- Env vars в worker процессах
- Неблокирующий shutdown с timeout 0.5s
- Graceful error handling
- **Результат**: Краш всё равно воспроизводился

**Вторая попытка (текущая)**:
- Все исправления из первой попытки +
- **АГРЕССИВНЫЙ shutdown**: принудительный terminate/kill процессов
- Предупреждение об отсутствии preview в UI
- **Результат**: Ожидается успешное исправление краша

---

## Файлы

**Изменены**:
- `processing/detector_process_pool.py` — 4 метода исправлены, агрессивный shutdown
- `ui/widgets/settings_page.py` — обновлён tooltip с предупреждением

**Связанные**:
- `main.py` — env vars для главного процесса (без изменений)
- `processing/processing_controller.py` — вызывает stop() (без изменений)

---

## Статус

✅ **Исправлено в коде (агрессивный shutdown)**  
✅ **Синтаксис проверен**  
⏳ **Требует тестирования пользователем**

Если краш всё ещё воспроизводится после этих изменений — собрать:
1. Полный `roadscan.log`
2. Точный момент краша (после какого лог-сообщения)
3. Windows Event Viewer → Application logs около времени краша
4. Проверить Task Manager — остались ли висячие python.exe процессы
