# Исправление краша 0xC0000409 (STATUS_STACK_BUFFER_OVERRUN)

## Проблема

**Ошибка:** `Process finished with exit code -1073740791 (0xC0000409)`  
**Описание:** STATUS_STACK_BUFFER_OVERRUN — критический краш при завершении обработки

## Причины

### 1. Конфликт библиотек OpenMP/MKL
- PyTorch использует Intel MKL с OpenMP (libiomp5md.dll)
- Qt/PyQt6 тоже может использовать OpenMP
- При одновременной работе → конфликт → краш

### 2. Отсутствие ожидания завершения потоков
- `finish_and_save()` останавливал reader
- Но НЕ ждал завершения detector
- При попытке сохранить результаты → обращение к незавершённым потокам → краш

### 3. Двойной вызов `_on_finish()`
- Сигнал `finished` мог вызвать `_on_finish()` дважды
- Попытка повторного обращения к уже удалённым объектам → краш

## Исправления

### 1. Усиленная защита от конфликта OpenMP (`main.py`)

```python
# БЫЛО:
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

# СТАЛО:
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["MKL_THREADING_LAYER"] = "GNU"  # Новое
os.environ["TBB_NUM_THREADS"] = "1"        # Новое
os.environ["OPENCV_NUM_THREADS"] = "1"     # Новое
```

### 2. Ожидание завершения потоков (`processing/processing_controller.py`)

```python
def finish_and_save(self) -> None:
    # Останавливаем reader
    if self._reader:
        self._reader.stop()
        # НОВОЕ: Ждём завершения (5 сек)
        if not self._reader.wait(5000):
            print("[WARNING] Reader не завершился")
    
    # НОВОЕ: Ждём завершения detector (10 сек)
    if self._detector:
        if not self._detector.wait(10000):
            print("[WARNING] Detector не завершился")
    elif self._detector_pool:
        self._detector_pool.stop()
```

### 3. Защита от двойного вызова (`ui/main_window.py`)

```python
def _on_finish(self):
    # НОВОЕ: Проверка что не вызывался уже
    if hasattr(self, '_finish_called') and self._finish_called:
        print("_on_finish уже был вызван, пропускаем")
        return
    
    self._finish_called = True
    
    # Обработка с try-except
    try:
        self._save_results()
    except Exception as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}")
        traceback.print_exc()
    
    # Сброс флага для следующего запуска
    self._finish_called = False
```

## Дополнительные меры безопасности

### 1. Логирование для диагностики

Добавлено логирование в критических точках:
```python
print("[MainWindow] _save_results вызван")
print(f"[MainWindow] Получено: {len(signs)} знаков")
print("[ProcessingController] finish_and_save завершён")
```

### 2. Обработка исключений

Все критические операции обёрнуты в `try-except`:
```python
try:
    self._save_results()
except Exception as e:
    traceback.print_exc()  # Полный traceback
    self.page_processing.log(f"Ошибка: {e}", "error")
```

### 3. Таймауты ожидания

Потоки ждут завершения с таймаутом:
- Reader: 5 секунд
- Detector: 10 секунд

Если не завершился → warning в лог, но программа продолжает работу.

## Тестирование

### Чек-лист

- [ ] Запустить обработку короткого видео (1-2 мин)
- [ ] Нажать "Завершить" в середине обработки
- [ ] Проверить что программа НЕ крашится
- [ ] Проверить что знаки сохранены в GeoJSON
- [ ] Проверить логи на warnings
- [ ] Повторить 3-5 раз для стабильности

### Ожидаемое поведение

✅ Программа завершает обработку корректно  
✅ GeoJSON сохраняется с найденными знаками  
✅ Нет краша 0xC0000409  
✅ В логах: "finish_and_save завершён"  

### Если краш всё равно происходит

1. **Проверить логи** — где именно крашится
2. **Проверить версии библиотек:**
   ```bash
   pip list | grep -E "torch|PyQt6|opencv"
   ```
3. **Попробовать отключить все оптимизации:**
   - Smart skipping → выключить
   - CNN cache → выключить
   - Checkpoint → CHECKPOINT_INTERVAL = 0
4. **Проверить память:**
   - Запустить Task Manager
   - Следить за потреблением RAM
   - Если > 90% → уменьшить FRAME_QUEUE_SIZE

## Известные ограничения

### Windows-специфичные проблемы

- Конфликт OpenMP критичен только на Windows
- На Linux/Mac подобных проблем обычно нет
- Intel MKL более проблематичен чем OpenBLAS

### Рекомендации

**Для максимальной стабильности:**

1. **Используйте последовательную обработку:**
   - Параллельные детекторы → отключено ✓
   - Это уже сделано по умолчанию

2. **Не прерывайте обработку слишком рано:**
   - Дайте детектору обработать минимум 10-20 кадров
   - Иначе SignHandler может быть не инициализирован

3. **Проверяйте свободную память:**
   - Минимум 4 ГБ свободной RAM
   - Иначе может быть краш от OOM, а не от OpenMP

4. **Обновите драйверы:**
   - Видеокарта
   - Chipset
   - Особенно Intel Management Engine

## Альтернативные решения

### Если краш продолжается

#### Вариант 1: Переустановить PyTorch с другим backend

```bash
# Вместо MKL использовать OpenBLAS
pip uninstall torch
pip install torch --index-url https://download.pytorch.org/whl/cpu
```

#### Вариант 2: Использовать виртуальное окружение

```bash
# Создать чистое окружение
python -m venv venv_clean
venv_clean\Scripts\activate
pip install -r requirements.txt
```

#### Вариант 3: Обработка без GUI

Создать CLI версию для обработки без Qt:
```bash
python process_video_cli.py --video video.mp4 --gpx track.gpx
```

Исключит конфликт Qt + OpenMP.

## Мониторинг

### Логи для диагностики

Следите за этими сообщениями:

```
[MainWindow] _save_results вызван
[MainWindow] Получено из контроллера: N знаков
[ProcessingController] finish_and_save завершён
[Checkpoint] Сохранено: N знаков
```

Если последнее сообщение не появилось → определите где краш.

### Task Manager

Во время обработки следите:
- CPU: 50-70% (норма)
- RAM: стабильная, не растёт
- Threads: 4-6 потоков

## Статус

| Исправление | Статус | Эффект |
|-------------|--------|--------|
| Защита OpenMP | ✅ Усилена | Должно помочь |
| Ожидание потоков | ✅ Добавлено | Критично |
| Защита от двойного вызова | ✅ Добавлена | Важно |
| Логирование | ✅ Добавлено | Диагностика |
| Обработка ошибок | ✅ Улучшена | Стабильность |

**Рекомендация:** Протестируйте на коротком видео (1-2 мин) перед длинной обработкой.

---

**Автор:** Kiro AI Agent  
**Дата:** 2026-07-09  
**Версия:** 1.3.2 (hotfix)
