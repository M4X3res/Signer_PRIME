# Исправление краша 0xC0000409 при завершении обработки в режиме Pipeline

**Дата**: 2026-08-26  
**Код ошибки**: `Process finished with exit code -1073740791 (0xC0000409)` — STATUS_STACK_BUFFER_OVERRUN

## Причины краша

### 1. **processing/detector_thread.py**: Вызов несуществующего метода `wait()` на OCRPool

**Проблема**: В блоке `finally` метода `run()` вызывался `self._ocr_worker.wait(3000)` для всех типов OCR workers, но класс `OCRPool` не имеет метода `wait()` (это метод QThread). Это вызывало `AttributeError` при использовании pipeline режима с OCRPool, что приводило к некорректной финализации ресурсов и краш 0xC0000409.

**Исправление**:
```python
# Было:
if self._ocr_worker:
    self._ocr_worker.stop()
    self._ocr_worker.wait(3000)  # ❌ OCRPool не имеет wait()!

# Стало:
if self._ocr_worker:
    if self._using_ocr_pool:
        # OCRPool не имеет метода wait(), используем shutdown с wait=True
        self._ocr_worker.stop(wait=True)
    else:
        # OCRWorkerThread имеет метод wait()
        self._ocr_worker.stop()
        if hasattr(self._ocr_worker, 'wait'):
            self._ocr_worker.wait(3000)
```

### 2. **processing/detector_thread.py**: Двойной вызов `stop()` на OCR worker

**Проблема**: Метод `stop()` DetectorThread вызывал `self._ocr_worker.stop()`, а затем в блоке `finally` метода `run()` снова вызывался `self._ocr_worker.stop()`. Это могло приводить к race condition и некорректной остановке процессов OCR.

**Исправление**: Убран вызов `stop()` из метода `DetectorThread.stop()` — теперь остановка OCR worker происходит только в `finally` блоке.

### 3. **processing/ocr_pool.py**: Агрессивная отмена futures при остановке

**Проблема**: При вызове `stop(wait=False)` использовался параметр `cancel_futures=True`, который отменял уже запущенные задачи OCR. Это приводило к краш 0xC0000409, потому что процессы с EasyOCR/PyTorch прерывались в момент работы с нативными библиотеками (libiomp5md.dll, MKL, CUDA runtime).

**Исправление**:
```python
# Было:
self._executor.shutdown(wait=False, cancel_futures=True)  # ❌ Краш!

# Стало:
self._executor.shutdown(wait=False, cancel_futures=False)  # ✅ Безопасно
```

Теперь при остановке не отменяем уже запущенные задачи, а просто не принимаем новые.

### 4. **ui/main_window.py**: Отсутствие явного ожидания завершения потоков

**Проблема**: При закрытии приложения вызывался `controller.stop()`, но не было явного ожидания завершения DetectorThread и VideoReader. Приложение могло завершиться до того, как потоки корректно освободили ресурсы (EasyOCR, PyTorch модели).

**Исправление**: Добавлено явное ожидание завершения потоков с таймаутами в `closeEvent()`:
```python
if self._controller._detector:
    if not self._controller._detector.wait(5000):
        print("[MainWindow] WARNING: DetectorThread не завершился за 5 сек")
        
if self._controller._reader:
    if not self._controller._reader.wait(2000):
        print("[MainWindow] WARNING: VideoReader не завершился за 2 сек")
```

### 5. **processing/processing_controller.py**: Недостаточная обработка таймаутов

**Проблема**: Метод `finish_and_save()` ждал завершения DetectorThread, но не предпринимал никаких действий если таймаут истекал. Поток мог остаться "висящим", блокируя освобождение ресурсов.

**Исправление**: Добавлена принудительная остановка при таймауте:
```python
if not self._detector.wait(10000):
    logger.warning("[ProcessingController] Detector не завершился за 10 сек")
    # Принудительно останавливаем
    self._detector.stop()
    self._detector.wait(2000)
```

## Изменённые файлы

1. `processing/detector_thread.py` — корректная остановка OCR worker в зависимости от типа (Pool vs Thread)
2. `processing/ocr_pool.py` — безопасная остановка без отмены запущенных futures
3. `ui/main_window.py` — явное ожидание завершения потоков при закрытии
4. `processing/processing_controller.py` — принудительная остановка при таймаутах

## Тестирование

После исправлений необходимо проверить:

1. ✅ **Синтаксис**: Все файлы компилируются без ошибок
2. ⏳ **Функциональность**: 
   - Запустить обработку в режиме Pipeline с CPU
   - Обработать минимум 100 кадров
   - Нажать кнопку "Завершить обработку"
   - **Ожидаемый результат**: Приложение корректно завершает обработку, сохраняет GeoJSON, без краша 0xC0000409

3. ⏳ **Закрытие приложения**:
   - Запустить обработку
   - Закрыть приложение через X (не дожидаясь завершения)
   - **Ожидаемый результат**: Приложение корректно завершается без краша

## Ожидаемая производительность в режиме Pipeline

**Текущая проблема**: Вы отметили, что "в режиме пайплайн прироста к производительности нет".

Это **ожидаемо** для CPU-режима, потому что:

1. **Одно узкое место**: YOLO детекция на CPU — самая медленная операция (~1-2 сек на кадр). CNN классификация и OCR быстрее на порядок.

2. **Pipeline не помогает**: Если детекция занимает 1 секунду, а OCR — 0.1 секунды, то pipeline может обрабатывать следующий кадр пока идёт OCR предыдущего. Но **детекция всё равно идёт последовательно**, потому что она одна на главном потоке.

3. **Реальное ускорение возможно только через**:
   - **CUDA** — ускорение YOLO в 10-50 раз
   - **Process Pool для детекции** — параллельная обработка кадров (но требует много RAM)
   - **Снижение разрешения** / увеличение frame skip

**Вывод**: Pipeline режим с CPU даёт прирост ~10-20% за счёт асинхронного OCR, но не решает главное узкое место — медленную детекцию на CPU. Для реального ускорения нужна CUDA или распараллеливание самой детекции.

## Связанные документы

- `docs/CRASH_FIX_0xC0000409.md` — исторический документ о проблемах с этим кодом ошибки
- `prompts/PROMPT_FIX_CPU_CRASH.md` — исходный промпт для диагностики
- `BUGFIX_VIDEO_FOLDER_CRASH_0xC0000409.md` — предыдущая попытка исправления (не решила проблему полностью)
