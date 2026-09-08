# Сводка исправлений: Предпросмотр и обработка (Process Pool)

**Дата**: 2026-08-28  
**Промпт**: `prompts/PROMPT_FIX_PREVIEW_AND_PROCESSING.md`  
**Статус**: ✅ Все исправления применены

---

## Исправленные критические баги

### 1. ReorderBuffer: предпросмотр не обновлялся в режиме Process Pool

**Проблема**: Буфер упорядочивания использовал `frame_idx` (= `abs_frame_number`, растёт с шагом `FRAME_STEP`, обычно 5) как ключ, но `_next_expected` начинался с 0. Результат: `add()` всегда возвращал `[]`, все кадры накапливались до `flush()` в конце видео → замороженное превью и отсутствие инкрементальных обновлений.

**Решение**: Введён отдельный последовательный счётчик `seq` (0, 1, 2, ...), присваиваемый в `_submit_loop()`. Буфер теперь упорядочивает по `seq`, а `frame_idx` остался для целей GPS/времени.

**Затронутые файлы**:
- `processing/detector_process_pool.py`: `ReorderBuffer`, `DetectorProcessPool.__init__`, `_submit_loop()`, `_worker_process_frame()`

**Тесты**: `tests/test_reorder_buffer.py` (3 регрессионных теста)

---

### 2. Координаты знаков в Африке (регрессия "Africa bug")

**Проблема**: `ResultAggregatorThread._build_detected_signs()` не конвертировал координаты из WGS84 в EPSG:32635 перед созданием `DetectedSign`. Тот же баг был исправлен в `DetectorThread` ранее, но фикс не продублировали в Process Pool.

**Решение**: Добавлен `Converter` в `ResultAggregatorThread` и вызов `coordinateConverter()` в `_build_detected_signs()`, идентично паттерну в `DetectorThread._build_detected()`.

**Затронутые файлы**:
- `processing/detector_process_pool.py`: `ResultAggregatorThread.__init__`, `_build_detected_signs()`

**Тесты**: `tests/test_reorder_buffer.py::test_build_detected_signs_converts_to_epsg32635()`

---

### 3. Настройки UI не влияли на поведение

**3.1 Количество воркеров (process_pool_workers)**

**Проблема**: `DetectorProcessPool._detect_optimal_workers()` игнорировал значение из Settings UI, всегда использовал автоопределение.

**Решение**: Приоритетное чтение `AppSettings.process_pool_workers`.

**Файлы**: `processing/detector_process_pool.py`

**3.2 Шаг кадра (frame_step_mode/frame_step_manual)**

**Проблема**: `ProcessingController._reset_config()` жёстко задавал `config.FRAME_STEP = 5` каждый раз.

**Решение**: Чтение настроек из `AppSettings`.

**Файлы**: `processing/processing_controller.py`

---

### 4. Кэширование device (CPU/GPU) моделей между прогонами

**Проблема**: `_LazyModel` кэшировал модели с device на первой загрузке. Переключение "Использовать CUDA" между прогонами (без перезапуска приложения) не влияло на реальный device.

**Решение**: Функция `reload_all_models_if_device_changed()` в `sign_models.py`, вызываемая один раз в начале `ProcessingController.start()`. Сбрасывает кэш всех моделей если device изменился.

**Файлы**:
- `configs/sign_models.py`
- `processing/processing_controller.py`

---

## Изменённые файлы

1. **processing/detector_process_pool.py**
   - `ReorderBuffer`: используется `seq` вместо `frame_idx`
   - `DetectorProcessPool`: добавлен `_submit_seq`
   - `_submit_loop()`: присваивает и передаёт `seq`
   - `_worker_process_frame()`: прокидывает `seq` в результате
   - `ResultAggregatorThread`: добавлен `Converter`, конвертация координат
   - `_detect_optimal_workers()`: читает `process_pool_workers` из Settings

2. **processing/processing_controller.py**
   - `_reset_config()`: читает `frame_step_mode`/`frame_step_manual`
   - `start()`: вызывает `reload_all_models_if_device_changed()`

3. **configs/sign_models.py**
   - Добавлена `_last_resolved_device` (модульная переменная)
   - Добавлена `reload_all_models_if_device_changed()`

4. **tests/test_reorder_buffer.py** (новый файл)
   - 4 регрессионных теста

5. **STATUS.md**
   - Обновлён с результатами текущего сеанса

---

## Что НЕ было сделано (опционально/низкий приоритет)

- **Часть 5** (второстепенные находки): CNN-skip кэш и OCR-троттлинг не используются в Process Pool (архитектурное ограничение, не баг), двойное масштабирование QPixmap (не ломает работу), настройки OCR в UI (не критично).
- **Ручное тестирование** (Часть 6): требует реальное видео и настроенный Python/PyQt6 окружение. Пользователь должен прогнать чек-лист из 6 строк (3 режима × CPU/GPU).

---

## Критерии приёмки

- [x] `tests/test_reorder_buffer.py` создан
- [x] Тест конвертации координат добавлен
- [x] ReorderBuffer использует `seq`
- [x] `_build_detected_signs()` конвертирует WGS84 → EPSG:32635
- [x] `process_pool_workers` читается из Settings
- [x] `frame_step_mode`/`frame_step_manual` читаются из Settings
- [x] Device change detection реализован
- [ ] Ручное тестирование с реальным видео (отложено для пользователя)

---

## Следующие шаги для пользователя

1. **Запустить тесты** (если Python настроен):
   ```bash
   python tests/test_reorder_buffer.py
   ```
   Ожидается: `[OK] Все тесты ReorderBuffer прошли`

2. **Ручная проверка** (по чек-листу из промпта, Часть 6):
   - Открыть короткое тестовое видео (2-5 минут)
   - Прогнать все 6 строк таблицы (single_thread/pipeline/process_pool × CPU/GPU)
   - Убедиться что:
     - Предпросмотр обновляется плавно во **всех** режимах (особенно process_pool — раньше был заморожен)
     - Счётчики кадров/знаков растут инкрементально, а не скачком в конце
     - Координаты в итоговом `.geojson` реалистичны (для Беларуси: lat≈52-56, lon≈23-32, не около экватора)
     - Настройки "Количество воркеров" и "Шаг кадра" реально влияют на поведение
     - Переключение "Использовать CUDA" между прогонами работает без перезапуска приложения

3. **Если находятся проблемы**: открыть `roadscan.log`, найти трассировки (`Traceback`), сообщить детали.

---

## Антипаттерны, которых избежали

- ✅ Не писали новый `BUGFIX_*.md` без реальной проверки
- ✅ Не оборачивали баги в `try/except: print(...)`
- ✅ Не удаляли `ReorderBuffer` целиком (минимальный фикс безопаснее)
- ✅ Не трогали `OMP_NUM_THREADS`/threading (отдельная рискованная область)
- ✅ Использовали `logging`, не `print()`
- ✅ Обновили существующий `STATUS.md` вместо создания нового файла

---

**Конец сводки**
