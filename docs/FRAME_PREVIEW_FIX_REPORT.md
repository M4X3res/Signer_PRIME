# Отчёт: Исправление предпросмотра кадров (Frame Preview Fix)

**Дата:** 2026-08-27  
**Задача:** Унификация и исправление отображения предпросмотра кадров во всех режимах обработки

---

## Проблема

Предпросмотр кадра в UI работал нестабильно из-за **нарушения базового правила потокобезопасности Qt**: объекты `QPixmap` создавались вне главного GUI-потока.

### Симптомы до исправления:

1. **Single Thread / Pipeline режимы:** `DetectorThread._emit_frame()` создавал `QPixmap` внутри `QThread.run()` — **нарушение Qt threading rules**
2. **Process Pool режим:** официально считался сломанным — в UI была подсказка **«⚠️ Preview не отображается (технические ограничения)»**
3. Отсутствие троттлинга FPS в Process Pool режиме → возможное захлёбывание UI при большом потоке кадров
4. **Три разных, независимо написанных реализации** одной и той же функциональности «показать кадр в UI»

### Корневая причина:

Официальная документация Qt: `QPixmap` — GUI-класс, который можно создавать **только в главном (GUI) потоке**. Нарушение приводит к:
- Искажённым/не обновляющимся кадрам
- Непредсказуемым крашам (особенно на Windows с разными GPU/драйверами)
- Зависаниям UI

---

## Решение

Применена **единая, потокобезопасная архитектура** на основе уже существующего правильного паттерна из `detector_process_pool.py`:

```
Worker Thread/Process:
    image (np.ndarray) → build_frame_dict() → emit(dict)

Main GUI Thread (ProcessingController):
    receive(dict) → build_pixmap_from_frame_dict() → QPixmap → UI
```

---

## Изменения в коде

### 1. Создан `processing/preview_utils.py`

**Единая точка конвертации кадра в QPixmap** с двумя функциями:

- `build_frame_dict(image_bgr)` — сериализация BGR-кадра в dict (вызывается из любого потока)
- `build_pixmap_from_frame_dict(frame_dict)` — восстановление и создание QPixmap (только из GUI-потока)

**Ключевые особенности:**
- Сериализация через `np.ndarray.tobytes()` — thread-safe
- Явная проверка contiguous layout через `np.ascontiguousarray()`
- `.copy()` на `QImage` для отвязки от временного буфера
- Подробная документация с предупреждениями о threading

### 2. Исправлен `processing/detector_thread.py`

**До:**
```python
def _emit_frame(self, image: np.ndarray) -> None:
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    qimg = QImage(rgb.data, ...)
    pixmap = QPixmap.fromImage(qimg).scaled(...)  # ❌ QPixmap в QThread!
    self.frame_ready.emit(pixmap)
```

**После:**
```python
def _emit_frame(self, image: np.ndarray) -> None:
    from processing.preview_utils import build_frame_dict
    self.frame_ready.emit(build_frame_dict(image))  # ✓ только dict
```

**Результат:** `DetectorThread` больше не создаёт GUI-объекты вне главного потока.

### 3. Исправлен `processing/detector_process_pool.py`

**Добавлено:**
- Троттлинг FPS предпросмотра (аналогично `DetectorThread`)
- Метод `_should_emit_preview()` с использованием `AppSettings.preview_fps_limit`
- Понижен уровень логирования: `logger.info(...)` на каждый кадр → `logger.debug(...)`

**Изменён `_emit_frame()`:**
- Использует `build_frame_dict()` вместо ручной сборки словаря
- Соответствует единому паттерну

**Изменён `_process_result()`:**
- Эмит кадра обёрнут в `if self._should_emit_preview():`
- Лог только при реальном эмите (не на каждом обработанном кадре)

### 4. Унифицирован `processing/processing_controller.py`

**Создан единый обработчик `_on_worker_frame_ready()`:**
```python
def _on_worker_frame_ready(self, frame_data):
    """Единый обработчик кадров от ЛЮБОГО источника детекции."""
    if isinstance(frame_data, dict) and 'image_bytes' in frame_data:
        pixmap = build_pixmap_from_frame_dict(frame_data)
        self.frame_ready.emit(pixmap)
    # ... fallback'ы для обратной совместимости
```

**Переподключены оба источника:**
- `DetectorThread.frame_ready` → `_on_worker_frame_ready`
- `DetectorProcessPool.frame_ready` → `_on_worker_frame_ready`

**Результат:** Все три режима (single_thread, pipeline, process_pool) используют одну и ту же точку создания `QPixmap` в главном потоке.

### 5. Удалён мёртвый код

**Удалено:**
- Файл `processing/detector_pool.py` — содержал тот же баг, что и `detector_thread.py`, не использовался нигде в коде
- Метод `ProcessingController._start_detector_pool()` — никогда не вызывался
- Константа `USE_DETECTOR_POOL` — не читалась в логике запуска

**Подтверждение через grep:** единственные упоминания были внутри самого мёртвого кода.

### 6. Обновлён UI (`ui/widgets/settings_page.py`)

**Было:**
```
• Process Pool — ...
  ⚠️ Preview не отображается (технические ограничения).

⚠️ Process Pool: нет preview, но результаты сохраняются
```

**Стало:**
```
• Process Pool — ...
  ℹ️ Предпросмотр обновляется с учётом троттлинга FPS.

ℹ️ Process Pool: предпросмотр работает, результаты сохраняются
```

---

## Тестирование

### Автоматические тесты

Созданы:
- `tests/test_preview_utils.py` — полный набор unit-тестов для `preview_utils`
- `tests/conftest.py` — фикстура `qapp` для GUI-тестов в offscreen режиме
- `tests/manual_test_preview_utils.py` — ручной тест без pytest

**Покрытие тестами:**
- ✓ Roundtrip сериализация/десериализация
- ✓ Non-contiguous массивы
- ✓ Создание QPixmap с разными размерами
- ✓ Масштабирование с сохранением aspect ratio
- ✓ BGR → RGB конвертация
- ✓ Обработка некорректных входных данных

**Статус:** Тесты созданы и готовы к запуску (требуется окружение с pytest и PyQt6).

### Матрица приёмки (для ручной проверки)

| # | processing_mode | use_cuda | Статус | Примечание |
|---|------------------|----------|---------|------------|
| 1 | single_thread    | False (CPU) | ⏳ Требует проверки | Код исправлен, нужно запустить реальное видео |
| 2 | single_thread    | True (GPU) | ⏳ Требует проверки | Если GPU доступна |
| 3 | pipeline         | False (CPU) | ⏳ Требует проверки | Код исправлен |
| 4 | pipeline         | True (GPU) | ⏳ Требует проверки | Если GPU доступна |
| 5 | process_pool     | False (CPU) | ⏳ Требует проверки | Добавлен троттлинг |
| 6 | process_pool     | True (GPU) | ⏳ Требует проверки | Если GPU доступна |

**Инструкция для ручной проверки:**
1. Запустить приложение
2. Загрузить тестовое видео (1-3 минуты)
3. Выбрать режим из матрицы в Settings
4. Нажать «Начать обработку»
5. Проверить:
   - ✓ Кадр в `video_label` обновляется (не «заморожен»)
   - ✓ Картинка не искажена по цвету
   - ✓ Bbox знаков отрисованы поверх кадра
   - ✓ Нет Exception в логах
   - ✓ Штатное закрытие не крашится

---

## Соответствие критериям приёмки

- [✓] В проекте есть **ровно одно** место создания `QPixmap` из кадра детекции — `ProcessingController._on_worker_frame_ready()`, выполняется в главном потоке
- [✓] `DetectorThread` больше не импортирует/не использует `QPixmap` внутри `run()`
- [✓] `detector_pool.py` удалён (мёртвый код)
- [✓] `ResultAggregatorThread` троттлит частоту эмита через `AppSettings.preview_fps_limit`
- [✓] Убрано избыточное `logger.info(...)` на каждый кадр → заменено на `logger.debug(...)`
- [✓] Устаревшая формулировка «Preview не отображается» убрана из UI
- [✓] Добавлены тесты `tests/test_preview_utils.py`
- [⏳] Матрица из 6 конфигураций требует ручной проверки (нет доступа к окружению с установленными зависимостями)
- [✓] Нет новых `print()` — только `logging`
- [✓] `ProcessingPage.set_frame()` не изменялся — сигнатура осталась прежней

---

## Архитектурные преимущества после рефакторинга

1. **Потокобезопасность:** Все GUI-объекты создаются только в главном потоке
2. **Единообразие:** Один паттерн для всех трёх режимов обработки
3. **Троттлинг:** Process Pool режим больше не «захлёбывается» кадрами
4. **Поддерживаемость:** Новый код самодокументирован с явными предупреждениями
5. **Тестируемость:** Логика конвертации вынесена в отдельный модуль с unit-тестами

---

## Известные ограничения

1. **Ручные тесты не прогнаны** из-за отсутствия доступа к окружению с установленными зависимостями (numpy, PyQt6, cv2)
2. **GPU конфигурации не проверены** — требуется машина с CUDA-compatible GPU
3. **Троттлинг в Process Pool** может восприниматься как «медленный preview» — это нормально и настраивается через `preview_fps_limit`

---

## Рекомендации для финальной проверки

1. Прогнать `tests/manual_test_preview_utils.py` в окружении проекта
2. Протестировать все 6 конфигураций матрицы с реальным видео
3. Проверить логи на отсутствие Qt-related warnings/errors
4. При необходимости отрегулировать `preview_fps_limit` для Process Pool режима

---

## Антипаттерны, которых избежали

- ❌ Не добавлен `try/except: pass` вокруг QPixmap (скрывание симптомов)
- ❌ Не добавлен `time.sleep` (ложное решение проблемы троттлинга)
- ❌ Не оставлено дублирующих реализаций конвертации кадра
- ❌ Не удалён существующий троттлинг из `DetectorThread`
- ❌ Не декларирован фикс без фактической проверки (честно указан статус ⏳)

---

## Связь с другими исправлениями

Этот фикс **независим** от других промптов (`PROMPT_FOR_AI_AGENT.md`, `PROMPT_MULTITHREADING.md`), но использует тот же код обработки видео. Критические баги (`setDaemon`, Qt-импорты) проверены и уже исправлены в репозитории.

---

**Автор:** Kiro AI Agent  
**Промпт:** `prompts/PROMPT_FIX_FRAME_PREVIEW.md`
