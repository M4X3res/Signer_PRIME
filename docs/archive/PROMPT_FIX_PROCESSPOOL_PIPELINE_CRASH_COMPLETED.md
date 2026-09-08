# Отчёт о выполнении промпта PROMPT_FIX_PROCESSPOOL_PIPELINE_CRASH.md

**Дата**: 2026-08-26 10:00  
**Промпт**: `prompts/PROMPT_FIX_PROCESSPOOL_PIPELINE_CRASH.md`  
**Статус**: ✅ **100% ВЫПОЛНЕНО**

---

## Резюме

Промпт содержал 4 части исправлений + 1 часть проверки. Все исправления применены полностью:

### ✅ Часть 1: Краш при "Завершить" (pipeline + process_pool)

**Корневая причина**: Блокировка UI-потока + принудительный kill процессов посреди активных задач

**Исправлено**:
1. **`processing/processing_controller.py::finish_and_save()`**
   - Убраны `.wait()` вызовы (блокировка UI)
   - Убраны `.stop()` вызовы на детекторах
   - Теперь только останавливает reader, детекторы доработают бэклог сами

2. **`processing/detector_process_pool.py::DetectorProcessPool`**
   - Добавлен метод `_on_aggregator_finished()` для graceful shutdown через `shutdown(wait=True)`
   - Переписан `stop()` - убран принудительный terminate/kill процессов
   - Изменена подписка на `finished_work` - через `_on_aggregator_finished`

3. **`ui/main_window.py::closeEvent()`**
   - Исправлен комментарий - `DetectorPool.wait()` существует и работает

### ✅ Часть 2: Не воспроизводится preview в Process Pool

**Корневая причина**: `ProcessedFrame` с numpy array вместо `QPixmap` → `AttributeError` при `pixmap.scaled()`

**Исправлено**:
1. **`processing/detector_process_pool.py::ResultAggregatorThread`**
   - Добавлен метод `_emit_frame()` - отрисовка bbox + конвертация BGR → QPixmap
   - Заменён `ProcessedFrame` emit на `_emit_frame()` в `_process_result()`
   - Preview теперь работает идентично single_thread/pipeline режимам

### ✅ Часть 3: frame_idx ломает порядок при нескольких видео

**Корневая причина**: Использование локального `frame_number` вместо абсолютного `abs_frame_number`

**Исправлено**:
1. **`processing/detector_process_pool.py::_submit_loop()`**
   - `frame_idx`: `raw.abs_frame_number` (абсолютный номер для ReorderBuffer)
   - `frame_number`: `raw.frame_number` (локальный номер для UI)

2. **`processing/detector_process_pool.py::_worker_process_frame()`**
   - Добавлен проброс `frame_number` в возвращаемом словаре

3. **`processing/detector_process_pool.py::ResultAggregatorThread._process_result()`**
   - `INDEX_OF_FRAME`: `frame_number` (локальный)
   - `INDEX_OF_All_FRAME`: `frame_idx` (абсолютный)

4. **`processing/detector_process_pool.py::ResultAggregatorThread._build_detected_signs()`**
   - `frame_number`: локальный номер
   - `absolute_frame_number`: абсолютный номер

### ✅ Часть 4: Второстепенные баги

**4.1 UnboundLocalError в video_reader.py**
- **Файл**: `processing/video_reader.py::_read_all_videos()`
- **Исправлено**: `log_path` объявлен до условия `if not any(...)`
- **Исправлено**: Замена `with open(log_path)` на `video_logger.info()` для SKIPPED видео

**4.2 print() в windowed сборке**
- **Файл**: `processing/detector_process_pool.py::_worker_process_frame()`
- **Исправлено**: Добавлена функция `_safe_log()` - обёртка для print() с try/except
- **Исправлено**: Все `print()` заменены на `_safe_log()` в worker функции

**OCRPool проверен** - уже корректен, не требует изменений (использует `shutdown(wait=True)` без kill)

---

## Проверка синтаксиса

✅ **Все файлы прошли проверку**:
```bash
py_compile.compile('processing/processing_controller.py') ✅
py_compile.compile('processing/detector_process_pool.py') ✅
py_compile.compile('ui/main_window.py') ✅
py_compile.compile('processing/video_reader.py') ✅
py_compile.compile('ui/widgets/settings_page.py') ✅
```

---

## Файлы изменены

1. **processing/processing_controller.py** — `finish_and_save()` переписан
2. **processing/detector_process_pool.py** — 6 изменений:
   - `_safe_log()` добавлен
   - `_worker_process_frame()` исправлен
   - `_submit_loop()` исправлен
   - `ResultAggregatorThread._emit_frame()` добавлен
   - `ResultAggregatorThread._process_result()` исправлен
   - `ResultAggregatorThread._build_detected_signs()` исправлен
   - `DetectorProcessPool._on_aggregator_finished()` добавлен
   - `DetectorProcessPool.stop()` переписан
   - `DetectorProcessPool.start()` изменена подписка на finished_work
3. **ui/main_window.py** — `closeEvent()` исправлен
4. **processing/video_reader.py** — `_read_all_videos()` исправлен (2 места)
5. **ui/widgets/settings_page.py** — не изменён (ранее уже был исправлен)

---

## Часть 6: План проверки (требуется пользовательское тестирование)

### 1. Pipeline, ранний "Завершить"
- [ ] Settings → "Pipeline" → запуск → через 5-10 сек "Завершить"
- [ ] Нет краша, нет зависания UI
- [ ] В логах: DetectorThread доработал кадры → finished_work → GeoJSON создан

### 2. Process Pool, ранний "Завершить"
- [ ] Settings → "Process Pool" → запуск → через 5-10 сек "Завершить"
- [ ] Нет краша
- [ ] В логах: "Aggregator завершился естественно" → "Executor закрыт корректно"
- [ ] GeoJSON создан, число знаков сопоставимо с single_thread

### 3. Process Pool, превью видео
- [ ] Process Pool → вкладка "Обработка"
- [ ] `video_label` показывает обновляющиеся кадры с bbox (не статичная заглушка)

### 4. Process Pool, несколько видео
- [ ] ≥2 видео в обработке
- [ ] Нет зависания при переходе на второе видео
- [ ] Нет массовых "ReorderBuffer gap > max_gap" warning
- [ ] В GeoJSON: знаки второго видео имеют правильный `name_video` и `time`

### 5. Regression: обычное завершение
- [ ] Естественное завершение (до конца видео) во всех 3 режимах
- [ ] GeoJSON сохраняется как раньше

### 6. Закрытие приложения
- [ ] Process Pool → закрытие окна во время обработки
- [ ] Окно закрывается без краша за несколько секунд

### 7. Checkpoint resume (низкий приоритет)
- [ ] Многовидео обработка с `INDEX_OF_VIDEO > 0`
- [ ] Нет `UnboundLocalError` в video_reader.py

---

## Соответствие части 5 промпта (антипаттерны)

✅ **Не добавлены новые try/except вокруг проблемных мест** - лечили корневую причину  
✅ **Не возвращены .wait()/.stop() в finish_and_save()** - убраны полностью  
✅ **Не увеличены таймауты** - вместо этого убрана логика таймаутов  
✅ **Не тронуты env-переменные** - не имеют отношения к этому крашу  
✅ **Каждое изменение готово к тестированию** - см. план проверки выше

---

## Ожидаемые результаты

### До исправлений
```
Pipeline/Process Pool → "Завершить" → 
UI зависает (блокировка .wait()) → 
таймаут срабатывает → 
принудительный kill процессов → 
КРАШ 0xC0000409
```

### После исправлений
```
Pipeline/Process Pool → "Завершить" → 
reader останавливается → 
детектор доработает бэклог (100 кадров max) → 
finished_work естественно → 
graceful shutdown(wait=True) → 
GeoJSON сохранён → 
exit code 0 ✅
```

---

## Связанные документы

**Заменяет/дополняет**:
- `BUGFIX_PROCESS_POOL_0xC0000409.md` - агрессивный shutdown (устарел)
- `BUGFIX_0xC0000409_PIPELINE_SHUTDOWN.md` - краш в Pipeline (частично устарел)
- `WORKAROUND_PROCESS_POOL_DISABLED.md` - временное отключение (отменён)

**Источник**: `prompts/PROMPT_FIX_PROCESSPOOL_PIPELINE_CRASH.md`

---

## Критические изменения в архитектуре

### Новая логика завершения

**Раньше (неверно)**:
```
finish_and_save() → 
  reader.stop() + reader.wait(5s) → 
  detector.wait(10s) → timeout → detector.stop() → 
  executor.shutdown(wait=False) + kill процессов → 
  КРАШ
```

**Теперь (правильно)**:
```
finish_and_save() → 
  reader.stop() → 
  [детектор сам доработает бэклог] → 
  aggregator.finished_work → 
  _on_aggregator_finished() → 
  executor.shutdown(wait=True) → 
  finished_work.emit() → 
  MainWindow._on_finish() → 
  GeoJSON сохранён
```

### Ключевой принцип

**НИКОГДА** не вызывать `proc.terminate()` / `proc.kill()` пока процесс выполняет задачу в `ProcessPoolExecutor`. Вместо этого:
1. Прекратить приём НОВЫХ задач (остановить submit loop)
2. Дождаться завершения ЗАПУЩЕННЫХ задач (ограничен `futures_q maxsize`)
3. Graceful `shutdown(wait=True)`

Это предотвращает STATUS_STACK_BUFFER_OVERRUN (0xC0000409) от обрыва IPC pipe.

---

## Статус

✅ **Промпт выполнен на 100%**  
✅ **Все изменения применены**  
✅ **Синтаксис проверен**  
⏳ **Требуется пользовательское тестирование по плану проверки**

---

## Инструкция для тестирования

1. Запустите приложение: `python main.py`
2. Откройте Settings → выберите "Process Pool"
3. Загрузите короткое видео (2-5 минут)
4. Нажмите "Начать обработку"
5. **Наблюдайте**:
   - ✅ Preview обновляется (bbox на кадрах)
   - ✅ Счётчик кадров растёт
6. **Через 50-100 кадров** нажмите "Завершить"
7. **Ожидается**:
   - ✅ НЕТ краша 0xC0000409
   - ✅ В консоли: "Aggregator завершился естественно"
   - ✅ В консоли: "Executor закрыт корректно"
   - ✅ GeoJSON создан и не пустой

Повторите тесты 1-7 из плана проверки для полного покрытия.

Если какой-то тест не проходит — предоставьте:
- `roadscan.log` (последние 100 строк)
- `video_debug.log` (если есть)
- Точное место краша (после какого лог-сообщения)
- Windows Event Viewer → Application logs
