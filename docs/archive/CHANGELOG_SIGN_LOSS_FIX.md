# CHANGELOG — Исправление потери знаков (2026-09-04)

## [CRITICAL FIX] Устранение потери данных при обработке видео

### 🔴 БАГ №1: Потеря знаков при переполнении result_queue

**Проблема:**  
При переполнении очереди результатов (`result_queue`) знаки терялись навсегда из-за безусловного `clear()` после прерывания цикла через `break`.

**Исправление:**
- `processing/detector_thread.py`: знаки, не поместившиеся в очередь, откладываются и отправляются повторно
- Финальная отправка использует блокирующий `put(timeout=2.0)` для каждого знака
- Явное логирование потерь с полным списком типов знаков

**Тест:** `tests/test_result_queue_no_loss.py` ✅

---

### 🔴 БАГ №2: Восстановление из checkpoint не работало

**Проблема:**  
`ProcessingController.start()` безусловно сбрасывал индексы через `_reset_config()`, уничтожая данные, только что загруженные через `load_checkpoint()`. Знаки из checkpoint не передавались в `DetectorThread`.

**Исправление:**
- `ProcessingController`: добавлен флаг `_resume_from_checkpoint`
- `_reset_config()`: проверяет флаг и НЕ сбрасывает индексы при восстановлении
- `DetectorThread`: принимает `checkpoint_signs` и восстанавливает их в `SignHandler`
- Одноразовый сброс флага после использования

**Тест:** `tests/test_checkpoint_resume.py` ✅

---

### 🟡 БАГ №3: Один битый знак уничтожал весь пакет

**Проблема:**  
В `FinalHandler._batch_snap_signs()` выражение `sign.car_x[-1]` бросало `IndexError` для знаков с пустыми координатами. Исключение перехватывалось верхним `try/except`, что приводило к `features = []` — все прямые знаки терялись.

**Исправление:**
- `FinalHandler`: новый метод `_validate_signs_for_processing()` фильтрует знаки без координат
- Валидация вызывается перед `_batch_snap_signs()`
- `logger.exception()` вместо ручного `traceback.print_exc()`
- Итоговая сводка с предупреждением если потеряно > 50% знаков

**Тест:** `tests/test_final_handler_resilience.py` ✅

---

### 🟡 БАГ №4: UI показывал неверное число сохранённых знаков

**Проблема:**  
`SaveThread` эмитировал `len(self.signs)` (входное количество), а не реальное количество features, записанных в GeoJSON после дедупликации.

**Исправление:**
- `FinalHandler.save_result()`: возвращает `int` — реальное количество записанных features
- `SaveThread`: использует возвращённое значение
- `MainWindow._on_save_finished()`: сравнивает входное и сохранённое, выдаёт предупреждение при больших расхождениях

**Тест:** `tests/test_final_handler_return_value.py` ✅

---

## Дополнительные улучшения

### Сквозное логирование
Добавлено логирование на каждой границе передачи данных:
- `DetectorThread`: количество знаков перед отправкой в очередь
- `DetectorThread.finally`: список потерянных типов при критичном переполнении
- `FinalHandler`: входное vs записанное количество с предупреждением

### Настройки
- `AppSettings`: добавлено поле `settings_ui_mode` для будущей реализации простого/расширенного режима

---

## Backward Compatibility

✅ Все существующие тесты прошли без изменений  
✅ Checkpoint-файлы старого формата совместимы  
✅ Никакие публичные API не сломаны  
✅ Дефолтное поведение осталось прежним

---

## Тестирование

**Все тесты:**
```bash
python tests/test_result_queue_no_loss.py          # PASS
python tests/test_checkpoint_resume.py             # PASS  
python tests/test_final_handler_resilience.py      # PASS
python tests/test_final_handler_return_value.py    # PASS
python tests/test_reorder_buffer.py                # PASS (регрессия)
```

**Ручная проверка (рекомендуется перед деплоем):**
1. Обработать короткое видео с GPX до конца
2. Обработать видео, нажать "Завершить" в середине
3. Убить процесс, запустить снова, восстановить из checkpoint
4. Временно уменьшить `RESULT_QUEUE_SIZE` до 5, проверить логи

---

## Файлы

**Изменено:**
- `processing/detector_thread.py`
- `processing/processing_controller.py`
- `core/final_handler.py`
- `ui/main_window.py`
- `configs/settings.py`

**Создано:**
- `tests/test_result_queue_no_loss.py`
- `tests/test_checkpoint_resume.py`
- `tests/test_final_handler_resilience.py`
- `tests/test_final_handler_return_value.py`
- `docs/BUGFIX_SIGN_LOSS_PART_A.md`
- `docs/EXECUTION_REPORT_SIGN_LOSS_FIX.md`

---

**Автор:** AI Agent (Kiro CLI)  
**Дата:** 2026-09-04  
**Промпт:** `prompts/PROMPT_FIX_SIGN_LOSS_AND_SETTINGS_MODES.md` (Часть A)
