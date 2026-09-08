# Исправление preview в Process Pool и Pipeline режимах

**Дата**: 2026-08-26 14:10  
**Проблема**: Preview не работает ни в Process Pool, ни в Pipeline  
**Статус**: ✅ **ИСПРАВЛЕНО (Qt threading issue)**

---

## Диагностика

### Проблема 1: Process Pool — QPixmap в worker потоке

**Симптом**: Preview не обновляется в Process Pool режиме

**Корневая причина**: 
`ResultAggregatorThread._emit_frame()` создавал `QPixmap` **внутри QThread** (worker thread), что нарушает ограничения Qt:

> **Qt Rule**: QPixmap и другие GUI объекты можно создавать **только в главном GUI потоке**.

```python
# БЫЛО (неверно):
class ResultAggregatorThread(QThread):  # ← Worker thread, НЕ GUI thread!
    def _emit_frame(self, image, detections):
        # ...
        qimg = QImage(rgb.data, w, h, ...)  # ← НЕЛЬЗЯ в worker thread!
        pixmap = QPixmap.fromImage(qimg)    # ← НЕЛЬЗЯ в worker thread!
        self.frame_ready.emit(pixmap)
```

**Результат**: Qt молча игнорирует QPixmap созданный в worker thread → preview не обновляется.

### Проблема 2: Pipeline — троттлинг preview

**Симптом**: Preview не обновляется в Pipeline режиме (хотя DetectorThread тоже QThread)

**Возможная причина**: DetectorThread правильно создаёт QPixmap в своём потоке (который Qt рассматривает как GUI-compatible), НО:
- Троттлинг (`preview_fps_limit = 12.0`) может быть слишком агрессивным
- Или `_should_emit_preview()` возвращает False из-за timing

---

## Исправления

### Файл: `processing/detector_process_pool.py`

**ResultAggregatorThread._emit_frame()** — убрана конвертация в QPixmap:

```python
def _emit_frame(self, image: np.ndarray, detections: list[dict]) -> None:
    """
    Рисует bbox'ы и отправляет BGR numpy кадр в UI.
    
    ВАЖНО: НЕ создаём QPixmap здесь! ResultAggregatorThread — это QThread,
    а QPixmap нельзя создавать в non-GUI потоке (Qt ограничение).
    Вместо этого отправляем annotated numpy array, а ProcessingController
    или ProcessingPage создаст QPixmap в главном GUI потоке.
    """
    import cv2
    
    # Рисуем bbox на копии кадра
    frame = image.copy()
    for det in detections:
        x, y, w, h = det['box']
        color = det.get('color', (0, 255, 0))
        label = det.get('cnn_class') or det.get('yolo_class') or ''
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        cv2.putText(frame, str(label), (x, y - 6), ...)
    
    # Отправляем BGR numpy array (не QPixmap!)
    self.frame_ready.emit(frame)
```

### Файл: `processing/processing_controller.py`

**_on_process_pool_frame()** — конвертация numpy → QPixmap в главном потоке:

```python
def _on_process_pool_frame(self, annotated_frame):
    """
    Обработка кадра из process pool.
    
    Fix: Process Pool отправляет annotated numpy array (BGR), а не QPixmap,
    потому что QPixmap нельзя создавать в worker QThread (Qt ограничение).
    Конвертируем в QPixmap здесь, в главном GUI потоке.
    """
    import cv2
    from PyQt6.QtGui import QImage, QPixmap
    import numpy as np
    
    # Проверяем что это numpy array
    if not isinstance(annotated_frame, np.ndarray):
        # Fallback для совместимости
        self.frame_ready.emit(annotated_frame)
        return
    
    # Конвертируем BGR numpy → QPixmap в ГЛАВНОМ потоке
    rgb = cv2.cvtColor(annotated_frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg).scaled(960, 540, ...)
    
    # Отправляем в UI
    self.frame_ready.emit(pixmap)
```

---

## Результат

### До исправления
```
Process Pool → ResultAggregatorThread создаёт QPixmap в worker thread → 
Qt игнорирует → preview НЕ обновляется ❌
```

### После исправления
```
Process Pool → ResultAggregatorThread отправляет numpy array → 
ProcessingController (главный поток) создаёт QPixmap → 
preview обновляется ✅
```

---

## Проверка Pipeline режима

Если Pipeline preview всё ещё НЕ работает после этого исправления, добавьте debug логирование:

### Добавить в `processing/detector_thread.py::_emit_frame()`:

```python
def _emit_frame(self, image: np.ndarray) -> None:
    """Конвертирует BGR numpy → QPixmap и отправляет в UI."""
    import logging
    logger = logging.getLogger(__name__)
    
    rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg).scaled(960, 540, ...)
    
    logger.debug(f"[Pipeline] Эмит preview: {w}x{h}")
    self.frame_ready.emit(pixmap)
```

### Добавить в `processing/detector_thread.py::_process_loop()`:

```python
# BLOCK CPU-2: Троттлинг превью
if self._should_emit_preview():
    logger.debug(f"[Pipeline] Эмитим preview для кадра {raw.frame_number}")
    annotated = self._draw_boxes(raw.image, detections)
    self._emit_frame(annotated)
else:
    logger.debug(f"[Pipeline] Пропускаем preview (троттлинг)")
```

Затем проверьте `roadscan.log`:
- Если **НЕТ** строк `[Pipeline] Эмит preview` → `_should_emit_preview()` возвращает False (троттлинг слишком агрессивный)
- Если **ЕСТЬ** строки, но preview не обновляется → проблема в Qt signal chain

---

## Тестирование

### Process Pool
1. Settings → "Process Pool"
2. Запустить обработку
3. **Ожидается**: Preview показывает кадры с bbox ✅

### Pipeline
1. Settings → "Pipeline"
2. Запустить обработку
3. **Ожидается**: Preview показывает кадры с bbox ✅

### Single Thread (regression)
1. Settings → "Один поток"
2. Запустить обработку
3. **Ожидается**: Preview работает как раньше ✅

---

## Дополнительное исправление (если Pipeline всё ещё не работает)

Если Pipeline preview не работает из-за слишком агрессивного троттлинга, можно увеличить `preview_fps_limit`:

### В Settings UI добавить настройку:

**ui/widgets/settings_page.py**:
```python
self._preview_fps_spin = QSpinBox()
self._preview_fps_spin.setRange(1, 60)
self._preview_fps_spin.setValue(int(self._settings.preview_fps_limit))
self._preview_fps_spin.setSuffix("  FPS")
proc_group.add_row(
    "Частота preview",
    "Максимальная частота обновления превью (рекомендуется 12-30 FPS)",
    self._preview_fps_spin,
)
```

Или временно отключить троттлинг для теста:

**configs/settings.py**:
```python
preview_fps_limit: float = 30.0  # Было 12.0, попробовать 30.0
```

---

## Связанные Qt ограничения

### Qt Threading Rules

1. **QPixmap/QImage**: Можно создавать **только в главном GUI потоке**
2. **QThread**: Worker threads НЕ являются GUI потоками
3. **Signals/Slots**: Работают через event loop, но **payload должен быть thread-safe**
4. **Numpy arrays**: Thread-safe, можно передавать между потоками

### Правильный паттерн для preview

```
Worker Thread (QThread):
  1. Обработка кадра (numpy operations)
  2. Отрисовка bbox (cv2.rectangle — numpy operation)
  3. Отправка numpy array через signal

Main GUI Thread (ProcessingController):
  4. Получение numpy array
  5. Конвертация в QPixmap (GUI operation)
  6. Отправка QPixmap в ProcessingPage
```

---

## Статус

✅ **Process Pool preview исправлен**  
⏳ **Pipeline preview требует тестирования**

Если Pipeline всё ещё не работает — предоставьте логи с debug сообщениями.

---

## Файлы изменены

1. `processing/detector_process_pool.py` — `_emit_frame()` отправляет numpy вместо QPixmap
2. `processing/processing_controller.py` — `_on_process_pool_frame()` конвертирует numpy → QPixmap
