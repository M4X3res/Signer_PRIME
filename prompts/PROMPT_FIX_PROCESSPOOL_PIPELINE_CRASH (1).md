# Промпт для ИИ-агента: краш при "Завершить" в pipeline/process_pool + отсутствие превью в Process Pool

> Скопируй весь этот файл в контекст ИИ-агента с реальным доступом к
> репозиторию RoadScanner (Signer PRIME). Ниже — точная диагностика (со
> ссылками на конкретный код) и точные диффы. Не переоткрывай диагностику
> заново «с нуля» — она уже сделана путём построчного анализа файлов
> `processing/processing_controller.py`, `processing/detector_process_pool.py`,
> `processing/detector_thread.py`, `processing/video_reader.py`,
> `ui/main_window.py`. Твоя задача — применить и проверить изменения, а не
> ещё раз диагностировать то же самое.

---

## КОНТЕКСТ: почему нельзя просто "обернуть в try/except"

В этом репозитории уже есть длинная история (`CRASH_FIX_*.md`,
`BUGFIX_*.md`, `docs/CRASH_FIX_0xC0000409.md`, `STATUS.md`) попыток лечить
краш `0xC0000409 (STATUS_STACK_BUFFER_OVERRUN)` через переменные окружения,
таймауты и обёртки `try/except: print(...)`. Ни одна из них не устраняет
корневую причину для режимов **pipeline** и **process_pool**, потому что
причина не в OpenMP/Qt конфликте, а в том, что код **насильно убивает
OS-процессы `ProcessPoolExecutor`, пока они ещё выполняют задачу**. Убийство
процесса, который в этот момент держит открытым pipe/очередь IPC с главным
процессом — это ровно то, что регулярно даёт `STATUS_STACK_BUFFER_OVERRUN`
на Windows. Правило для этой задачи: **никогда не вызывать `terminate()` /
`kill()` по живому `multiprocessing.Process`, пока для него есть
незавершённая задача**. Вместо этого — прекращать *приём новых* задач и
дожидаться завершения уже запущенных обычным `executor.shutdown(wait=True)`.

---

## ЧАСТЬ 1. Краш при "Завершить" (pipeline + process_pool) — ГЛАВНЫЙ БАГ

### 1.1. Диагностика

`ui/widgets/processing_page.py::_on_finish_clicked()` → эмитит
`finish_requested` → слот `ui/main_window.py::MainWindow._on_finish_requested()`
**выполняется в UI-потоке** и синхронно вызывает:

```python
if self._controller:
    self._controller.finish_and_save()
```

`processing/processing_controller.py::ProcessingController.finish_and_save()`
(текущий код):

```python
def finish_and_save(self) -> None:
    logger = logging.getLogger(__name__)

    if self._reader:
        self._reader.stop()
        if not self._reader.wait(5000):
            logger.warning("[ProcessingController] Reader не завершился за 5 сек")

    if self._detector:
        logger.info("[ProcessingController] Ожидание завершения DetectorThread...")
        if not self._detector.wait(10000):
            logger.warning("[ProcessingController] Detector не завершился за 10 сек")
            self._detector.stop()
            self._detector.wait(2000)
    elif self._detector_pool:
        logger.info("[ProcessingController] Остановка DetectorPool...")
        self._detector_pool.stop()

    logger.info("[ProcessingController] finish_and_save завершён")
```

Проблема в двух слоях:

1. **Блокировка UI-потока.** `.wait(5000)` / `.wait(10000)` — блокирующие
   вызовы, исполняемые прямо в обработчике клика. На CPU, при `FRAME_QUEUE_SIZE
   = 100` кадров в очереди (`ProcessingController.FRAME_QUEUE_SIZE`), доработка
   бэклога на CPU-инференсе легко занимает больше 10 секунд → таймаут почти
   гарантированно срабатывает.
2. **Форсированный обрыв посреди активных задач `ProcessPoolExecutor`.**
   При таймауте вызывается `self._detector.stop()` (или сразу
   `self._detector_pool.stop()` для process_pool). Оба пути тянут за собой
   принудительное закрытие пула процессов, пока часть задач ещё выполняется:
   - **pipeline**: `DetectorThread.stop()` → в `finally` блоке `run()`
     вызывается `self._ocr_worker.stop(wait=True)` для `OCRPool`
     (по умолчанию `settings.ocr_use_process_pool = True`) — это тоже
     `ProcessPoolExecutor`.
   - **process_pool**: `DetectorProcessPool.stop()` явно убивает процессы:

```python
# processing/detector_process_pool.py, текущий DetectorProcessPool.stop()
if self._executor:
    try:
        self._executor.shutdown(wait=False, cancel_futures=True)
        if hasattr(self._executor, '_processes'):
            processes = list(self._executor._processes.values()) if self._executor._processes else []
            for proc in processes:
                if proc and proc.is_alive():
                    proc.terminate()
            time.sleep(0.3)
            for proc in processes:
                if proc and proc.is_alive():
                    proc.kill()          # ← убийство процесса, который может
                                          #   в этот момент делать forward pass
                                          #   через torch/YOLO
        self._executor = None
    except Exception as e:
        ...
```

   Это лезет в приватный атрибут `_processes` (не публичный API
   `concurrent.futures`, может отличаться между версиями Python) и убивает
   процесс, не зная, свободен он или занят. Дополнительно `DetectorProcessPool.
   stop()` сразу же выставляет `self._stop = True`, из-за чего
   `_submit_loop()` бросает **необработанный бэклог кадров** (данные теряются
   ещё до всякого краша).

Итог: сам механизм "мягкого завершения" на практике превращается в
"подождать недостаточно → форсированно убить процессы во время работы" —
и для pipeline (через OCRPool), и для process_pool (через основной пул).

### 1.2. Фикс — архитектурный принцип

`finish_and_save()` не должен ничего ждать и ничего принудительно
останавливать. Он должен только попросить `VideoReaderThread` перестать
читать новые кадры. `DetectorThread` / `DetectorProcessPool` **сами**
доработают весь бэклог (он ограничен `FRAME_QUEUE_SIZE=100`, то есть конечен)
и **естественно** испустят `finished_work`, когда реально закончат — этот
сигнал уже подключён к `_on_detector_finished()` → `self.finished` →
`MainWindow._on_finish()` → `_save_results()`. Никакого `.wait()` на UI-потоке
быть не должно.

### 1.3. Диффы

**`processing/processing_controller.py`** — заменить весь метод
`finish_and_save`:

```python
def finish_and_save(self) -> None:
    """
    Мягкая остановка — просим reader прекратить чтение НОВЫХ кадров.

    ВАЖНО: вызывается из UI-потока (слот на кнопку "Завершить") и НЕ
    ДОЛЖЕН блокировать его вызовами .wait()! DetectorThread /
    DetectorProcessPool сами доработают весь бэклог кадров, оставшийся
    в очереди (ограничен FRAME_QUEUE_SIZE), и когда реально закончат —
    испустят finished_work, уже подключённый к _on_detector_finished()
    → self.finished → MainWindow._on_finish() → _save_results().

    Никакого принудительного .stop()/.wait() здесь быть не должно —
    именно комбинация "короткий таймаут + forced stop посреди активных
    задач ProcessPoolExecutor" (OCRPool в pipeline или основной пул в
    process_pool) была причиной краша 0xC0000409 при нажатии "Завершить".
    """
    logger = logging.getLogger(__name__)
    logger.info("[ProcessingController] finish_and_save: сигнал остановки чтения видео")

    if self._reader:
        self._reader.stop()

    # НЕ вызывать .wait()/.stop() на self._detector или self._detector_pool
    # здесь — см. docstring выше.
```

**`processing/detector_process_pool.py`** — переписать `DetectorProcessPool.
stop()` и добавить `_on_aggregator_finished()`, переключить подписку на
`finished_work` в `start()`.

В `start()` заменить строку:

```python
self._aggregator.finished_work.connect(self.finished_work)
```

на:

```python
self._aggregator.finished_work.connect(self._on_aggregator_finished)
```

Добавить новый метод в класс `DetectorProcessPool`:

```python
def _on_aggregator_finished(self) -> None:
    """
    Вызывается когда ResultAggregatorThread САМ естественно завершился —
    то есть весь бэклог из очереди прочитан reader'ом, отправлен
    submitter'ом, обработан воркер-процессами и агрегирован. В этот
    момент executor можно закрыть штатно (executor.shutdown(wait=True)):
    все задачи уже выполнены, никто больше не вызывает executor.submit(),
    поэтому wait=True не зависнет и не потребует kill() процессов.
    """
    logger = logging.getLogger(__name__)
    logger.info("[DetectorProcessPool] Aggregator завершился естественно — закрываем executor...")

    if self._submitter_thread and not self._submitter_thread.wait(30000):
        logger.warning("[DetectorProcessPool] Submitter не завершился за 30 сек после aggregator")

    if self._executor is not None:
        try:
            self._executor.shutdown(wait=True)  # безопасно: новых задач больше не будет
        except Exception as e:
            logger.error(f"[DetectorProcessPool] Ошибка graceful shutdown executor: {e}")
        finally:
            self._executor = None

    logger.info("[DetectorProcessPool] Executor закрыт корректно")
    self.finished_work.emit()
```

Заменить весь метод `stop()`:

```python
def stop(self) -> None:
    """
    Немедленная остановка (используется кнопкой "Стоп"/закрытием
    приложения — БЕЗ ожидания полной обработки очереди, оставшийся
    бэклог кадров отбрасывается).

    ВАЖНО: НЕ убивает OS-процессы принудительно (proc.terminate()/kill()).
    Вместо этого прекращает приём НОВЫХ кадров в submit_loop (он выйдет
    на следующей итерации, максимум ~0.2с) и позволяет уже запущенным
    задачам (их не больше self._num_workers*4, см. futures_q maxsize)
    доработать штатно. Дальше _on_aggregator_finished() сам закроет
    executor через обычный graceful shutdown(wait=True). Именно
    принудительный kill() воркер-процессов посреди вычисления был
    вероятной причиной крашей 0xC0000409 — см. Часть 1 промпта
    PROMPT_FIX_PROCESSPOOL_PIPELINE_CRASH.md.
    """
    logger = logging.getLogger(__name__)
    logger.info("[DetectorProcessPool] Останавливаем (abort)...")
    self._stop = True
    # Дальнейшая остановка (submitter → aggregator → executor.shutdown)
    # произойдёт естественно и безопасно через _on_aggregator_finished().
```

**Важно:** ничего не убирай из `_submit_loop()` и не трогай `_process_loop`
в `ResultAggregatorThread` — они уже корректно проверяют `self._stop` и
`_STOP`/`None` сентинелы, всё нужное для «мягкого» финиша там уже есть.

**`processing/detector_thread.py`** — изменений в самом файле НЕ требуется,
раз `finish_and_save()` больше не дёргает `.stop()`/`.wait()` для этого
случая: `DetectorThread` теперь всегда доработает весь бэклог естественным
путём и штатно завершит OCR-воркер в `finally` блоке `run()` (уже
реализовано). Единственное, что нужно **проверить** (см. Часть 3) —
`processing/ocr_pool.py` (файла нет в контексте этого промпта, прочитай его
отдельно): убедись, что `OCRPool.stop(wait=True)` тоже не убивает процессы
принудительно, а делает `executor.shutdown(wait=True)` после того, как
submit-цикл OCRPool сам прекратил приём новых задач. Если там есть
`terminate()`/`kill()` по аналогии со старым `DetectorProcessPool.stop()` —
исправь по тому же принципу, который применён выше.

**`ui/main_window.py`** — `MainWindow.closeEvent()` (для полноты, при
закрытии приложения тоже вызывается `self._controller.stop()`, а там
устаревший неверный комментарий и упущенный `.wait()`):

```python
elif self._controller._detector_pool:
    print("[MainWindow] Ожидание завершения DetectorPool...")
    # DetectorPool не имеет wait(), только stop()
    pass
```

заменить на:

```python
elif self._controller._detector_pool:
    print("[MainWindow] Ожидание завершения DetectorPool...")
    if not self._controller._detector_pool.wait(5000):
        print("[MainWindow] WARNING: DetectorPool не завершился за 5 сек")
```

(`DetectorProcessPool.wait()` уже существует и делегирует в
`self._aggregator.wait(timeout_ms)` — комментарий в коде был просто неверный.)

---

## ЧАСТЬ 2. Не воспроизводится (не обновляется) превью кадра в Process Pool

### 2.1. Диагностика

`ui/widgets/processing_page.py::ProcessingPage.set_frame()`:

```python
def set_frame(self, pixmap: QPixmap):
    self.video_label.setPixmap(
        pixmap.scaled(...)
    )
```

Ожидает `QPixmap`. Но в process_pool режиме сигнал `frame_ready` доходит
из `processing/detector_process_pool.py::ResultAggregatorThread._process_result()`:

```python
processed = ProcessedFrame(
    frame_idx=frame_data['frame_idx'],
    video_idx=frame_data['video_idx'],
    video_name=frame_data['video_name'],
    image=image,                    # сырой numpy BGR-массив
    detections=frame_data['detections'],
    gps_data=frame_data.get('gps_data'),
    timestamp=frame_data['timestamp'],
)
self.frame_ready.emit(processed)    # ← НЕ QPixmap!
```

Через `ProcessingController._on_process_pool_frame()` этот `ProcessedFrame`
пробрасывается как есть в `page_processing.set_frame(pixmap)`, где падает
на `pixmap.scaled(...)` (`AttributeError`). В отличие от `DetectorThread.
_emit_frame()` и старого `DetectorPool._emit_frame()`, здесь шаг конвертации
в `QPixmap` с отрисованными боксами просто отсутствует — поэтому превью в
режиме Process Pool никогда не обновляется.

### 2.2. Фикс

**`processing/detector_process_pool.py`** — в `ResultAggregatorThread.
_process_result()` заменить блок формирования и отправки `ProcessedFrame`:

```python
        # Создаем ProcessedFrame для UI
        processed = ProcessedFrame(
            frame_idx=frame_data['frame_idx'],
            video_idx=frame_data['video_idx'],
            video_name=frame_data['video_name'],
            image=image,
            detections=frame_data['detections'],
            gps_data=frame_data.get('gps_data'),
            timestamp=frame_data['timestamp'],
        )

        # Отправляем в UI
        self.frame_ready.emit(processed)
```

на:

```python
        # ── Превью для UI ────────────────────────────────────────
        # page_processing.set_frame() (ui/widgets/processing_page.py)
        # ожидает QPixmap, а не сырой ProcessedFrame/numpy-массив — раньше
        # сюда отправлялся ProcessedFrame, из-за чего set_frame() падал на
        # pixmap.scaled() и превью в Process Pool режиме никогда не
        # показывалось.
        self._emit_frame(image, frame_data['detections'])
```

и добавить новый метод в `ResultAggregatorThread`:

```python
    def _emit_frame(self, image: np.ndarray, detections: list[dict]) -> None:
        """
        Рисует bbox'ы и конвертирует BGR numpy кадр в QPixmap для
        ProcessingPage.set_frame(). Аналог DetectorThread._draw_boxes +
        DetectorThread._emit_frame из processing/detector_thread.py —
        сохраняй тот же стиль отрисовки (толщина линии, шрифт), чтобы
        превью выглядело одинаково независимо от режима обработки.
        """
        import cv2
        from PyQt6.QtGui import QImage, QPixmap
        from PyQt6.QtCore import Qt

        frame = image.copy()
        for det in detections:
            x, y, w, h = det['box']
            color = det.get('color', (0, 255, 0))
            label = det.get('cnn_class') or det.get('yolo_class') or ''
            cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
            cv2.putText(
                frame, str(label), (x, y - 6),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1,
            )

        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        h_, w_, ch = rgb.shape
        qimg = QImage(rgb.data, w_, h_, ch * w_, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(
            960, 540,
            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
        )
        self.frame_ready.emit(pixmap)
```

`ProcessedFrame` датакласс можно оставить в файле (не используется для UI
после фикса, но не мешает) либо удалить вместе с неиспользуемым импортом —
на усмотрение агента, это не влияет на корректность.

`ProcessingController._on_process_pool_frame()` менять не нужно — он просто
форвардит `object` дальше, а сигнал `frame_ready = pyqtSignal(object)`
одинаково пропускает что `ProcessedFrame`, что `QPixmap`.

---

## ЧАСТЬ 3. Побочный баг, найденный при анализе: `frame_idx` ломает порядок кадров и время знаков при нескольких видео

### 3.1. Диагностика

`processing/detector_process_pool.py::DetectorProcessPool._submit_loop()`:

```python
frame_data = {
    'frame_idx': raw.frame_number,   # ← номер кадра ВНУТРИ текущего видео!
    'video_idx': raw.video_index,
    'video_name': raw.video_name,
    'image_bytes': raw.image.tobytes(),
    'image_shape': raw.image.shape,
    'gps_data': {'gps_index': raw.gps_index},
}
```

`raw.frame_number` (см. `processing/video_reader.py::RawFrame`) — это
локальный номер кадра внутри текущего видеофайла, обнуляющийся на каждом
новом файле из `config.VIDEOS`. Этот же `frame_idx` используется:

1. Как ключ упорядочивания в `ReorderBuffer` (`self._next_expected`,
   стартует с 0 и растёт монотонно). При переходе на второе видео кадры
   снова начинают идти с малых номеров 1, 2, 3... — они уже меньше
   `_next_expected`, накопленного от первого видео, никогда не совпадают с
   ожидаемым значением → буфер копится → срабатывает защита
   `gap > max_gap` → кадры второго и последующих видео массово
   пропускаются/теряются (см. `ReorderBuffer.add()`).
2. Как `config.INDEX_OF_All_FRAME` в `ResultAggregatorThread._process_result()`
   — это поле используется в `core/final_handler.py::_build_feature()` для
   вычисления `video_idx`/времени знака (`avg_frame // config.FRAMES_PER_VIDEO`).
   С локальным номером вместо абсолютного эти вычисления неверны для
   любого видео, кроме первого.

### 3.2. Фикс

**`processing/detector_process_pool.py`**, в `_submit_loop()`:

```python
frame_data = {
    'frame_idx': raw.abs_frame_number,
    'frame_number': raw.frame_number,  # локальный номер — для UI/переходов к кадру
    'video_idx': raw.video_index,
    'video_name': raw.video_name,
    'image_bytes': raw.image.tobytes(),
    'image_shape': raw.image.shape,
    'gps_data': {'gps_index': raw.gps_index},
}
```

В `_worker_process_frame()`, в возвращаемом словаре добавить проброс
`frame_number`:

```python
return {
    'frame_idx': raw_frame_data['frame_idx'],
    'frame_number': raw_frame_data.get('frame_number', raw_frame_data['frame_idx']),
    'video_idx': raw_frame_data['video_idx'],
    'video_name': raw_frame_data['video_name'],
    'image_bytes': raw_frame_data['image_bytes'],
    'image_shape': raw_frame_data['image_shape'],
    'detections': detections_serialized,
    'gps_data': raw_frame_data.get('gps_data'),
    'timestamp': time.time(),
}
```

В `ResultAggregatorThread._process_result()`:

```python
config.INDEX_OF_FRAME = frame_data['frame_idx']
config.INDEX_OF_All_FRAME = frame_data['frame_idx']  # Используем frame_idx как abs_frame
```

заменить на:

```python
config.INDEX_OF_FRAME = frame_data.get('frame_number', frame_data['frame_idx'])
config.INDEX_OF_All_FRAME = frame_data['frame_idx']  # теперь действительно абсолютный номер
```

В `_build_detected_signs()`:

```python
frame_number=frame_data['frame_idx'],
absolute_frame_number=frame_data['frame_idx'],
```

заменить на:

```python
frame_number=frame_data.get('frame_number', frame_data['frame_idx']),
absolute_frame_number=frame_data['frame_idx'],
```

---

## ЧАСТЬ 4. Второстепенные баги, найденные попутно

### 4.1. `UnboundLocalError` в `processing/video_reader.py` при повторном запуске обработки

`_read_all_videos()`:

```python
video_logger = logging.getLogger(f"{__name__}.video_debug")
video_logger.setLevel(logging.DEBUG)

if not any(isinstance(h, logging.FileHandler) for h in video_logger.handlers):
    log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "video_debug.log")
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    video_logger.addHandler(file_handler)
```

`video_logger` — логгер уровня модуля, его `handlers` переживают повторные
вызовы `_read_all_videos()` в рамках одного процесса приложения (второй
запуск обработки, восстановление из checkpoint и т.п.). При повторном
запуске условие `if not any(...)` — `False`, `log_path` не создаётся, а
дальше в коде:

```python
if video_idx < config.INDEX_OF_VIDEO:
    with open(log_path, "a", encoding="utf-8") as log:   # ← UnboundLocalError
        log.write(f"[VIDEO {video_idx}] SKIPPED: {video_name}\n")
```

Эта ветка срабатывает при восстановлении с `INDEX_OF_VIDEO > 0` (checkpoint
resume на многовидео обработке) — то есть при штатном сценарии "продолжить
после краша/паузы", что прямо противоречит смыслу feature checkpoint.

**Фикс:**

```python
video_logger = logging.getLogger(f"{__name__}.video_debug")
video_logger.setLevel(logging.DEBUG)

# log_path нужен ниже (ветка "SKIPPED") независимо от того, создаём ли мы
# FileHandler в этом вызове, или он уже был создан предыдущим запуском.
log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "video_debug.log")
if not any(isinstance(h, logging.FileHandler) for h in video_logger.handlers):
    file_handler = logging.FileHandler(log_path, mode='w', encoding='utf-8')
    file_handler.setFormatter(logging.Formatter('%(message)s'))
    video_logger.addHandler(file_handler)
```

и заменить ручной `open()` на использование того же логгера (заодно
устраняет открытие одного файла двумя дескрипторами одновременно):

```python
if video_idx < config.INDEX_OF_VIDEO:
    video_logger.info(f"[VIDEO {video_idx}] SKIPPED: {video_name}")
    self.video_switched.emit(video_idx, video_name)
    continue
```

### 4.2. `print()` внутри воркер-процесса (`_worker_process_frame`)

В `processing/detector_process_pool.py::_worker_process_frame()` используется
`print()` для диагностики внутри дочернего процесса. В GUI-приложении,
собранном PyInstaller с флагом `--windowed` (см. `sys._MEIPASS` в `utils.py`,
`main.py`), у процесса без консоли `sys.stdout is None`, и `print()` кидает
`AttributeError`. Это не критично прямо сейчас (при обычном запуске через
`python main.py` есть консоль), но является латентным крашем при поставке
собранного `.exe`. Низкий приоритет, почини заодно:

```python
def _safe_log(msg: str) -> None:
    """print() может упасть в windowed/frozen сборке, где sys.stdout is None."""
    try:
        print(msg)
    except Exception:
        pass
```

и заменить все `print(...)` внутри `_worker_process_frame` на `_safe_log(...)`.

---

## ЧАСТЬ 5. Что НЕ трогать / антипаттерны (важно)

Следуй тем же правилам, что уже сформулированы в `prompts/PROMPT_FOR_AI_AGENT.md`
этого репозитория (Часть 5 «Антипаттерны»):

1. **Не добавляй новые `try/except: print(...)` вокруг проблемных мест** —
   корневая причина найдена (принудительный kill процессов), лечи её, а не
   маскируй симптом ещё одним обработчиком исключений.
2. **Не возвращай обратно `.wait()`/`.stop()` в `finish_and_save()`** "на
   всякий случай" — это заново воспроизведёт краш. Если кажется, что нужно
   дождаться чего-то синхронно — сигнальная цепочка `finished_work →
   _on_detector_finished → self.finished → MainWindow._on_finish` уже это
   делает асинхронно, не блокируя UI.
3. **Не увеличивай таймауты `.wait(5000)/.wait(10000)`** вместо удаления
   логики — большой бэклог на медленном CPU всё равно рано или поздно
   вылезет за любой фиксированный таймаут.
4. **Не трогай `configs/config.py` env-переменные** (`OMP_NUM_THREADS=1` и
   т.д.) в рамках этой задачи — они не имеют отношения к этому классу
   краша (см. диагностику выше — причина в `multiprocessing`, не в OpenMP).
5. Каждое изменение сопровождай тестовым сценарием из Части 6 — не
   помечай пункт как исправленный, пока сам не прогнал сценарий.

---

## ЧАСТЬ 6. План проверки / критерии приёмки

Обязательно прогнать вручную (короткое тестовое видео, 1-3 минуты, ≥2
видеофайла в `config.VIDEOS`, если возможно — для проверки Части 3):

1. **Pipeline, ранний "Завершить"**: Settings → режим "Pipeline" → запустить
   обработку → через 5-10 секунд нажать "■ Завершить".
   - [ ] Приложение НЕ крашится, UI не "зависает" (Not Responding).
   - [ ] В логах видно, что DetectorThread доработал оставшиеся кадры
     (продолжают идти `[SmartSkip] ...` строки некоторое время после клика),
     затем `finished_work` → сохранение → `GeoJSON` создан.
2. **Process Pool, ранний "Завершить"**: то же самое с режимом
   "Process Pool".
   - [ ] Нет краша.
   - [ ] В логах видно `[DetectorProcessPool] Aggregator завершился
     естественно — закрываем executor...` и затем `Executor закрыт корректно`.
   - [ ] `GeoJSON` создан, число знаков сопоставимо с single_thread на том
     же ролике (не пустой, не в разы меньше).
3. **Process Pool, превью видео**: запустить обработку в режиме Process
   Pool, перейти на вкладку "Обработка".
   - [ ] `video_label` показывает обновляющиеся кадры с отрисованными
     bbox'ами знаков (как в single_thread/pipeline режимах), а не
     статичную заглушку "Видео не запущено".
4. **Process Pool, несколько видео** (если тестовых видео ≥2):
   - [ ] Обработка не "зависает"/не теряет массово кадры при переходе со
     первого видео на второе (смотри лог `[DetectorProcessPool]`,
     отсутствие `ReorderBuffer gap > max_gap` warning на регулярной основе).
   - [ ] В сохранённом `GeoJSON` у знаков из второго видео `name_video`
     соответствует реальному второму файлу, а `time` — правдоподобное
     (не "0:00" у всех знаков второго видео).
5. **Regression обычного (не раннего) завершения**: дать обработке дойти
   до конца видео естественно (reader сам исчерпает файлы) — во всех трёх
   режимах убедиться, что `GeoJSON` сохраняется как раньше, поведение не
   изменилось.
6. **Закрытие приложения во время обработки** (`MainWindow.closeEvent`) в
   process_pool режиме — окно закрывается без краша и без зависания дольше
   нескольких секунд.
7. Дополнительно (низкий приоритет, Часть 4.1): восстановление из
   checkpoint на многовидео обработке (`INDEX_OF_VIDEO > 0`) не падает с
   `UnboundLocalError`.

Если какой-то пункт не проходит — не отправляй следующий шаг, диагностируй
именно этот сценарий (логи `roadscan.log` + `video_debug.log`) прежде чем
считать блок исправленным.
