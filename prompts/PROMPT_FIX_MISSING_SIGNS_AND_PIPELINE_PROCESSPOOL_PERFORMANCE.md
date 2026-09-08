# PROMPT ДЛЯ ИИ-АГЕНТА: Пропадающие знаки + низкая производительность Pipeline/Process Pool

**Дата составления:** 2026-09-03
**Автор анализа:** Claude (аудит кода без возможности запуска)
**Статус:** Найдены конкретные, воспроизводимые баги с точными местами в коде. Ниже — предписанные исправления, а не догадки "попробуйте это".

---

## 0. TL;DR для нетерпеливых

Тестирование показало: "все режимы настроек вроде работают", но знаки не сохраняются, а Pipeline и Process Pool медленнее Single Thread. Это **не два случайных бага**, а **три бага в одной цепочке**, все связанные с обработкой OCR (распознавания текста на знаках):

| # | Баг | Файл | Эффект |
|---|-----|------|--------|
| **A** | `AttributeError: 'DetectedSign' object has no attribute 'bbox'` — падает весь `DetectorThread` при первом текстовом знаке | `processing/detector_thread.py`, метод `_submit_ocr_task()` | В **Pipeline**-режиме обработка обрывается почти сразу после старта → **знаки не сохраняются** (или сохраняется 2-3 знака) |
| **B** | Результат OCR никогда не записывается обратно в `TrackedSign.text_results` | `processing/detector_thread.py`, методы `_on_ocr_result()` / `_on_ocr_result_pool()` | Даже после фикса A текстовые знаки (ограничения скорости с подписью, названия городов) будут сохраняться с **пустым текстом** |
| **C** | `Detector.detect()` в **Process Pool**-воркере запускается с `skip_ocr=False` по умолчанию — OCR гоняется синхронно на КАЖДОМ кадре КАЖДОГО знака в КАЖДОМ процессе, без какого-либо троттлинга (в отличие от single_thread, где троттлинг уже реализован) | `processing/detector_process_pool.py`, функция `_worker_process_frame()` | Process Pool **всегда медленнее** single_thread, независимо от количества ядер — тратит в 5-8 раз больше времени на OCR, чем нужно |

Есть ещё 2 менее критичных, но реальных бага (`best_city_name()` всегда возвращает `""`, и знаки, ещё видимые в последних кадрах видео, никогда не финализируются) — см. Части 3 и 5.

**Порядок исправления:** A → B → C → (D, city name) → (E, finalize at end). A и B неразрывно связаны — фиксить нужно вместе, иначе после фикса A знаки будут сохраняться, но с пустым текстом (это будет выглядеть как "новый баг", хотя это тот же самый недоделанный код).

---

## 1. Контекст проекта (для агента, который видит код впервые)

Проект — desktop-приложение на PyQt6 (`RoadScanner` / `Signer PRIME`), которое обрабатывает видео с видеорегистратора + GPX-трек, находит дорожные знаки через YOLO+CNN, читает текст на знаках через EasyOCR, и сохраняет результат в GeoJSON.

Есть три режима обработки, переключаемые в Settings → "Режим обработки":

1. **`single_thread`** — всё в одном `DetectorThread` (QThread), OCR синхронный, но с троттлингом через `TrackedSign.should_run_ocr()`.
2. **`pipeline`** — тоже один `DetectorThread`, но OCR выносится в отдельный воркер (`OCRPool` — ProcessPoolExecutor, или `OCRWorkerThread` — QThread) и обрабатывается асинхронно, чтобы не блокировать основной цикл детекции.
3. **`process_pool`** — сама детекция (YOLO+CNN+OCR) размазывается по `ProcessPoolExecutor` с N воркер-процессами (`DetectorProcessPool` / `_worker_process_frame`), результаты собираются и упорядочиваются в `ResultAggregatorThread`.

Ключевые файлы, с которыми предстоит работать:

- `core/frame.py` — `DetectedSign` (иммутабельный dataclass, одно наблюдение знака в одном кадре)
- `core/sign.py` — `TrackedSign` (накопленная история знака по кадрам, включая `text_results: list[str]`)
- `core/sign_handler.py` — `SignHandler` (трекинг знаков между кадрами, финализация)
- `core/detector.py` — `Detector` (YOLO+CNN+OCR на одном кадре, включая CNN pHash-кэш)
- `core/final_handler.py` — `FinalHandler` (финальная сборка GeoJSON)
- `processing/detector_thread.py` — `DetectorThread` (single_thread / pipeline режимы)
- `processing/detector_process_pool.py` — `DetectorProcessPool`, `ResultAggregatorThread`, `_worker_process_frame` (process_pool режим)
- `processing/ocr_pool.py` — `OCRPool` (асинхронный OCR через отдельные процессы, используется в pipeline)
- `processing/ocr_worker.py` — `OCRWorkerThread` (асинхронный OCR через QThread, альтернатива OCRPool в pipeline)

---

## 2. БАГ A (P0, блокирующий): падение `DetectorThread` в Pipeline-режиме

### 2.1. Где именно

Файл `processing/detector_thread.py`, метод `_submit_ocr_task()`:

```python
def _submit_ocr_task(self, detected_sign: DetectedSign, frame: np.ndarray) -> None:
    if not self._ocr_worker:
        return

    sign_id = self._ocr_sign_counter
    self._ocr_sign_counter += 1

    # Извлекаем crop из кадра
    x, y, w, h = detected_sign.bbox        # <<< ВОТ ОНО. AttributeError.
    crop = frame[y:y+h, x:x+w]
    ...
```

`detected_sign` — это экземпляр `DetectedSign` из `core/frame.py`:

```python
@dataclass(slots=True)
class DetectedSign:
    x: int
    y: int
    w: int
    h: int
    name_sign:            str
    number_sign:          str
    frame_number:         int
    absolute_frame_number:int
    latitude:              float
    longitude:             float
    text_on_sign:         str = ""
    is_side:              bool = False
```

**У `DetectedSign` НЕТ атрибута `bbox`.** Поля называются `x, y, w, h` по отдельности. Класс объявлен с `@dataclass(slots=True)`, а значит у него нет `__dict__` и нельзя динамически "подставить" атрибут — обращение `detected_sign.bbox` **всегда** кидает `AttributeError: 'DetectedSign' object has no attribute 'bbox'`.

### 2.2. Как это вызывает потерю знаков

Цепочка вызовов, приводящая к краху:

1. `DetectorThread._process_loop()` крутится в цикле, для каждого кадра вызывает `SignHandler.check_the_data_to_add()`, который трекает знаки.
2. Дальше — только если `self._use_pipeline == True` (т.е. режим `pipeline`):
   ```python
   if self._use_pipeline and self._sign_handler.signs:
       for tracked_sign in self._sign_handler.signs:
           if self._detector.needs_ocr(tracked_sign.best_cnn, tracked_sign.best_yolo):
               if tracked_sign.should_run_ocr(raw.abs_frame_number):
                   ...
                   ocr_det_sign = DetectedSign(x=last_x, y=last_y, w=last_w, h=last_h, ...)
                   self._submit_ocr_task(ocr_det_sign, raw.image)   # <<< падает здесь
   ```
3. `tracked_sign.should_run_ocr()` возвращает `True` практически всегда при **первом** наблюдении текстового знака (`_last_ocr_abs_frame` инициализируется как `-10000`, так что условие интервала сразу выполняется).
4. `needs_ocr()` возвращает `True` для любого знака из `TYPE_SIGNS_WITH_TEXT` (ограничения скорости с подписью, таблички с расстоянием и т.д.) или `NAME_SIGNS_CITY` (указатели населённых пунктов) — это **очень частые** типы знаков на реальном видео.
5. Как только такой знак попадает в трекинг (обычно в первые секунды видео), `_submit_ocr_task()` кидает `AttributeError`.
6. Исключение **не перехватывается** внутри `_process_loop()` — оно улетает наверх, в `DetectorThread.run()`:
   ```python
   try:
       self._process_loop()
   except Exception as e:
       self.error.emit(str(e))
   finally:
       ...
       self.finished_work.emit()
   ```
7. `run()` перехватывает исключение, шлёт сигнал `error` (текст ошибки виден в логе обработки, но легко теряется среди других сообщений), и **сразу же** эмитит `finished_work` — то есть UI считает, что обработка **успешно завершена**.
8. `ProcessingController._on_detector_finished()` → `MainWindow._on_finish()` → `_save_results()` вызывается **немедленно**, сохраняя только те знаки, что успели финализироваться (`SignHandler._finalize_signs()`) за первые несколько секунд до краха. Часто это **ноль знаков** (знаку нужно минимум `MIN_OBSERVATIONS=4` наблюдения + `DIFF_FRAMES_MOVE=5` кадров "исчезновения", чтобы попасть в `result_signs`).

**Вывод: в Pipeline-режиме на реальном видео (где есть хотя бы один текстовый знак в первые секунды) `DetectorThread` фактически умирает почти сразу после старта.** Внешне это выглядит как "обработка завершилась мгновенно" + "GeoJSON почти пустой" — то есть именно то, что описывает пользователь.

Это же объясняет "низкую производительность Pipeline": дело не в том, что Pipeline медленнее по FPS — он **не работает вообще**, просто корректно завершается (без явного краша всего приложения), из-за чего проблему легко спутать с "тормозит".

### 2.3. Требуемое исправление

Заменить единственную проблемную строку:

```python
# БЫЛО:
x, y, w, h = detected_sign.bbox

# СТАЛО:
x, y, w, h = detected_sign.x, detected_sign.y, detected_sign.w, detected_sign.h
```

Дополнительно (не обязательно, но желательно для защиты от будущих регрессий): добавить в `core/frame.py` свойство `bbox`, чтобы аналогичные обращения в другом коде не падали неожиданно:

```python
@dataclass(slots=True)
class DetectedSign:
    x: int
    y: int
    w: int
    h: int
    ...

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.w, self.h)
```

(`@property` прекрасно работает с `slots=True`, так как это дескриптор класса, а не атрибут экземпляра — конфликта со `slots` нет.)

**Обязательно:** после фикса сделай `grep -rn "\.bbox" processing/ core/` по всему репозиторию и убедись, что нет других мест, где к `DetectedSign` (не путать с `SignRecord.bbox` в `ui/widgets/error_editor_page.py` — это другой, самодостаточный класс, трогать не нужно) обращаются через `.bbox` без объявленного свойства.

---

## 3. БАГ B (P0, обязателен вместе с A): результат OCR никогда не долетает до знака

### 3.1. Где именно

После того как задача на OCR отправлена в воркер (`OCRPool` или `OCRWorkerThread`), результат приходит через callback:

```python
def _on_ocr_result_pool(self, result) -> None:
    from processing.ocr_pool import OCRResult
    if result.sign_id in self._pending_ocr:
        detected_sign = self._pending_ocr.pop(result.sign_id)
        detected_sign.text_on_sign = result.text     # <<< тупик
        ...
```

и аналогично `_on_ocr_result()` для `OCRWorkerThread`-варианта.

`detected_sign` здесь — это тот самый **одноразовый, ни к чему не привязанный** объект `ocr_det_sign`, созданный в п. 2.2 шаг 2 исключительно чтобы донести crop-координаты до `_submit_ocr_task()`. Присвоение `detected_sign.text_on_sign = result.text` записывает текст **в переменную, которая тут же становится мусором** — этот объект нигде не хранится, не передаётся в `SignHandler`, не добавляется ни в один `TrackedSign`.

### 3.2. Почему это важно

`TrackedSign.text_results` (используется в `FinalHandler._build_feature()` для генерации поля `SEM250`/`MVALUE` в GeoJSON) заполняется **только** внутри `SignHandler.check_the_data_to_add()` → `TrackedSign.append(det)`:

```python
def append(self, det: DetectedSign) -> None:
    ...
    if det.text_on_sign:
        self.text_results.append(det.text_on_sign)
```

Но `append()` вызывается **до** того, как OCR вообще завершился (в pipeline-режиме `Detector.detect(..., skip_ocr=True)` изначально возвращает `text=""` для всех знаков, именно поэтому OCR и вынесен в отдельный асинхронный шаг). Результат асинхронного OCR **никогда повторно не добавляется** в `text_results` этого знака.

**Следствие:** даже после исправления бага A, Pipeline-режим будет находить и сохранять знаки корректно (тип, геометрия, координаты), но у всех текстовых знаков (`3.24` с подписанной массой, `5.22.1`/`5.23.3` с названием города и т.п.) поле текста в GeoJSON всегда будет пустым. Это не крашит процесс, но искажает данные — важно исправить сразу вместе с A, а не отдельным заходом позже.

### 3.3. Требуемое исправление

Нужно, чтобы в момент отправки OCR-задачи сохранялась ссылка не на одноразовый `DetectedSign`, а на **сам `TrackedSign`**, чтобы после получения результата можно было напрямую дописать его в `text_results`.

`TrackedSign` — обычный `@dataclass` (без `slots`), мутировать поля можно свободно; хранение ссылки на него в `self._pending_ocr` держит объект живым в памяти (Python GC), даже если он к этому моменту уже перекочевал из `self._sign_handler.signs` в `result_signs`/`turns` — это нормально и безопасно, так как объект один и тот же.

Меняем сигнатуру и тело:

```python
def _submit_ocr_task(self, tracked_sign: "TrackedSign", frame: np.ndarray) -> None:
    """
    Отправляет знак на OCR обработку.
    ВАЖНО: храним ссылку на TrackedSign (а не на одноразовый DetectedSign),
    чтобы результат OCR можно было дописать обратно в tracked_sign.text_results.
    """
    if not self._ocr_worker:
        return
    if not tracked_sign.pixel_x or not tracked_sign.pixel_y:
        return

    sign_id = self._ocr_sign_counter
    self._ocr_sign_counter += 1

    x = tracked_sign.pixel_x[-1]
    y = tracked_sign.pixel_y[-1]
    w = tracked_sign.widths[-1]
    h = tracked_sign.heights[-1]
    crop = frame[y:y + h, x:x + w]

    if crop.size == 0:
        return

    self._pending_ocr[sign_id] = tracked_sign   # <<< ключевое изменение

    if self._using_ocr_pool:
        self._ocr_worker.submit(
            sign_id=sign_id,
            frame_number=tracked_sign.frame_numbers[-1],
            crop=crop.copy(),
            cnn_class=tracked_sign.best_cnn,
            yolo_class=tracked_sign.best_yolo,
            callback=self._on_ocr_result_pool
        )
    else:
        from processing.ocr_worker import OCRTask
        task = OCRTask(
            sign_id=sign_id,
            frame_number=tracked_sign.frame_numbers[-1],
            crop=crop.copy(),
            cnn_class=tracked_sign.best_cnn,
            yolo_class=tracked_sign.best_yolo
        )
        submitted = self._ocr_worker.submit_task(task)
        if not submitted:
            logger.warning(f"[Pipeline] Не удалось отправить OCR задачу для sign_id={sign_id}")
            self._pending_ocr.pop(sign_id, None)
```

И вызов в `_process_loop()` (там, где раньше строился `ocr_det_sign`) упрощается — больше не нужно вручную собирать промежуточный `DetectedSign`:

```python
if self._use_pipeline and self._sign_handler.signs:
    for tracked_sign in self._sign_handler.signs:
        if self._detector.needs_ocr(tracked_sign.best_cnn, tracked_sign.best_yolo):
            if tracked_sign.should_run_ocr(raw.abs_frame_number):
                self._submit_ocr_task(tracked_sign, raw.image)
                tracked_sign.mark_ocr_requested(raw.abs_frame_number)
                self._ocr_calls_total += 1
            else:
                self._ocr_calls_skipped += 1
```

(Импорт `DetectedSign` в этом файле по-прежнему нужен для `_build_detected()` — не удаляй.)

И callback-и:

```python
def _on_ocr_result(self, result) -> None:
    """Обработчик результата OCR из OCRWorkerThread (QThread)."""
    tracked_sign = self._pending_ocr.pop(result.sign_id, None)
    if tracked_sign is None:
        logger.warning(f"[Pipeline] Получен OCR результат для неизвестного sign_id={result.sign_id}")
        return
    if result.text:
        tracked_sign.text_results.append(result.text)
    logger.debug(f"[Pipeline] OCR завершён для sign_id={result.sign_id}, text='{result.text}'")

def _on_ocr_result_pool(self, result) -> None:
    """Callback для результата OCR из OCRPool (ProcessPool)."""
    tracked_sign = self._pending_ocr.pop(result.sign_id, None)
    if tracked_sign is None:
        logger.warning(f"[OCRPool] Получен OCR результат для неизвестного sign_id={result.sign_id}")
        return
    if result.error:
        logger.warning(f"[OCRPool] Ошибка для sign_id={result.sign_id}: {result.error}")
        return
    if result.text:
        tracked_sign.text_results.append(result.text)
    logger.debug(f"[OCRPool] OCR завершён для sign_id={result.sign_id}, text='{result.text}'")
```

**Важный нюанс:** `_on_ocr_result_pool` вызывается через `Future.add_done_callback()` из `ocr_pool.py`. В CPython callback `ProcessPoolExecutor.Future.add_done_callback` выполняется в потоке, который вызвал `future.result()` внутри пула, либо сразу же если future уже готов — практически всегда это **не** тот же поток, что крутит `_process_loop()`. Значит `tracked_sign.text_results.append(...)` потенциально мутируется из другого потока, пока основной поток тоже может читать/писать в `self._sign_handler.signs`. Это стоит явно защитить (см. п. 3.4).

### 3.4. Обязательная проверка потокобезопасности

`self._pending_ocr` — обычный `dict`, к которому обращаются из (а) основного потока `_process_loop()` при `submit()`, (б) callback-потока при завершении future. Операции `pop()`/`__setitem__` на `dict` в CPython атомарны на уровне отдельной операции благодаря GIL, так что грубого повреждения памяти не будет, но **гонка данных на уровне логики** возможна (например, `mark_ocr_requested()` в основном потоке и `text_results.append()` в callback-потоке почти одновременно — это безопасно, т.к. это разные поля разных списков, но стоит явно упомянуть в комментарии, что мутация `TrackedSign` происходит из двух потоков намеренно и осознанно).

Не нужно городить `threading.Lock()` для этого — риск дедлока/переусложнения выше пользы. Убедись только, что **`FinalHandler.save_result()` вызывается уже после того, как весь OCR-пул полностью остановлен** (`self._ocr_worker.stop(wait=True)` в `finally`-блоке `DetectorThread.run()` — это уже так реализовано, просто явно это провалидируй тестом, см. Часть 7).

---

## 4. БАГ C (P1, критично для производительности): OCR без троттлинга в Process Pool

### 4.1. Где именно

Файл `processing/detector_process_pool.py`, функция `_worker_process_frame()`:

```python
def _worker_process_frame(raw_frame_data: dict) -> dict:
    ...
    detector = _worker_process_frame._detector
    try:
        image = np.frombuffer(...).reshape(...)
        detections = detector.detect(image)          # <<< ВОТ ОНО
        ...
```

`Detector.detect(image)` вызывается **без** аргумента `skip_ocr` → используется значение по умолчанию `skip_ocr: bool = False`. Внутри `detect()`:

```python
text = ""
if not skip_ocr:
    with profiler.measure("ocr_read_text"):
        text = self._read_text(crop, cnn_class, yolo_class)
```

То есть **каждый worker-процесс на каждом вызове (= каждый обработанный кадр видео) синхронно гоняет EasyOCR на каждом обнаруженном текстовом знаке**, без какого-либо ограничения частоты.

### 4.2. Почему это в разы медленнее single_thread

В `single_thread`-режиме (`DetectorThread`, `self._use_pipeline == False`) вызывается `Detector.detect_with_tracking(raw.image, tracked_map, skip_ocr=False)`, и внутри этого метода OCR **уже троттлится** через `TrackedSign.should_run_ocr()`:

```python
if not tracked_sign.should_run_ocr(abs_frame):
    should_call_ocr = False
    ocr_skipped += 1
else:
    tracked_sign.mark_ocr_requested(abs_frame)
    ocr_called += 1
```

Это ограничивает число реальных вызовов EasyOCR до `OCR_MAX_CALLS_PER_SIGN = 6` успешных распознаваний на знак, не чаще чем раз в `OCR_MIN_INTERVAL_FRAMES = 8` обработанных кадров (см. `core/sign.py::TrackedSign.should_run_ocr()`). При типичной видимости знака 30-40 кадров это даёт экономию **~80-85% вызовов EasyOCR**, задокументированную в `CPU_OPT_BLOCK_4_OCR_THROTTLING.md`.

**У Process Pool такого механизма нет и в принципе не может быть в текущей архитектуре**, потому что:

- Каждый вызов `_worker_process_frame()` обрабатывает **один изолированный кадр**, без доступа к истории наблюдений конкретного знака за прошлые кадры.
- `TrackedSign`/`SignHandler` живут только в главном процессе, внутри `ResultAggregatorThread` — они физически недоступны воркер-процессам (у каждого своя память, `ProcessPoolExecutor` с `spawn`).
- CNN pHash-кэш (`Detector._cnn_cache`) в каждом воркере свой (per-process singleton `_worker_process_frame._detector`), поэтому CNN хоть как-то кэшируется, но **аналогичного кэша для OCR-результатов сейчас нет вообще** (см. `core/detector.py` — есть `CNNCache`/`compute_image_hash`, но их использование ограничено CNN-классификацией, для OCR такого нет).

**Итог:** EasyOCR (100-500мс на вызов, задокументировано в `docs/PROFILING_RESULTS.md`, `BLOCK_C_ASYNC_OCR_IMPLEMENTATION.md`) вызывается в Process Pool **в 5-8 раз чаще**, чем должен бы — независимо от количества воркеров/ядер, это делает Process Pool медленнее single_thread на любом видео с текстовыми знаками (то есть практически на любом реальном видео с ограничениями скорости/указателями). Параллелизм по кадрам не компенсирует этот перерасход, потому что перерасход **умножается на каждый воркер отдельно**.

### 4.3. Обязательное исправление: OCR-кэш по perceptual hash (минимальный риск, максимальная польза)

Самое безопасное и универсальное решение — **добавить OCR-кэш по тому же принципу, что уже работает для CNN** (`compute_image_hash()` уже существует и используется в `core/detector.py`, ничего изобретать не нужно). Соседние кадры трекинга дают почти идентичный crop одного и того же знака → pHash почти всегда совпадает → кэш даст высокий hit-rate **без необходимости какого-либо межпроцессного/межкадрового состояния**. Это работает одинаково хорошо во всех трёх режимах (single_thread, pipeline, process_pool), потому что кэш живёт внутри одного `Detector`-инстанса на процесс, а не зависит от `TrackedSign`.

В `core/detector.py`:

1. В `Detector.__init__` добавить второй кэш рядом с существующим `self._cnn_cache`:
   ```python
   self._ocr_cache = CNNCache(maxsize=500)  # общий LRU-класс, ключ->текст; можно переиспользовать as-is
   ```
   (`CNNCache` по устройству — обычный generic LRU `str -> Any`, типовая аннотация `tuple[str, float]` нигде жёстко не форсируется рантаймом — переиспользование безопасно. Если хочешь чище — заведи отдельный класс `OCRCache(CNNCache)` без изменения логики, просто для читаемости кода.)

2. Переписать `_read_text()`:
   ```python
   def _read_text(
       self,
       crop_orig: np.ndarray,
       cnn_class: str,
       yolo_class: str,
   ) -> str:
       """Читает текст на знаке (с OCR-кэшем по perceptual hash)."""
       needs_basic = cnn_class in TYPE_SIGNS_WITH_TEXT
       needs_city  = yolo_class in NAME_SIGNS_CITY
       if not needs_basic and not needs_city:
           return ""

       img_hash = compute_image_hash(crop_orig)
       cache_key = f"{'ocr_city' if needs_city else 'ocr_basic'}:{img_hash}"

       cached = self._ocr_cache.get(cache_key)
       if cached is not None:
           return cached

       text = self._ocr(crop_orig) if needs_basic else self._ocr_city(crop_orig)
       self._ocr_cache.put(cache_key, text)
       return text
   ```
   (`compute_image_hash()` уже принимает изображение произвольного размера — внутри сам делает resize до 8x8, дополнительный ресайз перед вызовом не нужен, передавай `crop_orig` как есть, в оригинальном разрешении, так же как сейчас.)

3. Убедиться, что метод `_run_cnn_batch`/`_classify_fine_batch` — не трогать, это отдельный кэш, не путать местами.

4. Опционально, но рекомендуется: добавить `get_ocr_cache_stats()` / периодический лог по аналогии с `_print_cache_stats()` для CNN, чтобы в проде было видно фактический hit-rate.

**Важно:** это исправление снижает нагрузку OCR **во всех режимах**, но особенно критично для `process_pool`, так как это единственный доступный механизм троттлинга, не требующий архитектурных изменений и не пересекающийся с прошлыми задокументированными крашами `0xC0000409` (см. Часть 8, "Чего не делать").

### 4.4. Опционально / P3 (делать только если хватает времени и после того, как A/B/C/D полностью протестированы): полноценный троттлинг OCR в Process Pool

Если после фикса 4.3 производительность Process Pool всё ещё неудовлетворительна, следующий шаг — перенести OCR из воркеров в главный процесс, аналогично исправленному (после багов A/B) pipeline-механизму:

1. В `_worker_process_frame()` жёстко зафиксировать `detector.detect(image, skip_ocr=True)` — воркеры больше никогда не делают OCR.
2. В `ResultAggregatorThread` (у которой уже есть доступ к `self._sign_handler` и, следовательно, к `TrackedSign` с историей по кадрам) добавить `OCRPool`-инстанс (тот же класс, что использует Pipeline) и логику отправки задач по образцу исправленного `_submit_ocr_task()` из Части 3.3: после каждого `self._sign_handler.check_the_data_to_add(...)` — пройтись по `self._sign_handler.signs`, вызвать `needs_ocr()` + `should_run_ocr()`, и если нужно — отправить crop на OCR, привязав результат к `TrackedSign` тем же паттерном хранения ссылки, что в Части 3.3.
3. Это даст Process Pool тот же уровень троттлинга (~80% экономии), что и single_thread/pipeline, поверх уже полученной экономии от кэша (п. 4.3) — то есть двойной эффект.

**Это отдельная, более рискованная задача.** Делать её отдельным коммитом от P0/P1 фиксов, с отдельным тестированием. Не смешивать с обязательной частью промпта.

---

## 5. БАГ D (P1, искажение данных): `best_city_name()` всегда возвращает `""`

### 5.1. Где именно

`core/sign.py`:

```python
def best_city_name(self) -> str:
    scores: dict[str, dict] = {}
    for item in self.text_results:
        if not isinstance(item, list):
            continue
        for accuracy, name in item:
            ...
    if not scores:
        return ""
    return max(scores, key=lambda n: scores[n]["accuracy"])
```

Метод ожидает, что элементы `self.text_results` — это **списки кортежей** `[(accuracy, name), ...]`. Но реальные реализации `_ocr_city()`:

- `core/detector.py::Detector._ocr_city()` — возвращает **обычную строку** (лучшее совпадение из `difflib.get_close_matches(..., n=1, ...)`).
- `processing/ocr_pool.py::_ocr_city()` — возвращает **строку**, местами `json.dumps([(0.9, match), ...])` (сериализованный JSON-текст, тоже `str`, а не `list`).

`TrackedSign.append()` кладёт эти строки в `text_results` как есть:
```python
if det.text_on_sign:
    self.text_results.append(det.text_on_sign)
```

В `best_city_name()` проверка `isinstance(item, list)` для **любой строки всегда False** → `continue` на каждой итерации → `scores` остаётся пустым `{}` → метод **всегда** возвращает `""`.

### 5.2. Кого это касается

`FinalHandler._build_feature()`:
```python
if sign.best_yolo in NAME_SIGNS_CITY:
    text = sign.best_city_name()      # <<< всегда ""
elif len(sign.text_results) > 4:
    text = sign.most_common(sign.text_results)[0]
else:
    text = ""
```

Все знаки указателей населённых пунктов (`5.22.1`, `5.22.2`, `5.23.1`, `5.23.2`, `5.23.3`, `5.25.3` — см. `NAME_SIGNS_CITY`/`TYPE_SIGNS_CITY` в `configs/sign_data.py`) сохраняются в GeoJSON с **пустым** полем `SEM250`/`MVALUE`, даже если OCR отработал корректно.

### 5.3. Требуемое исправление

Логика голосования по большинству (`most_common`) уже реализована и используется для обычных текстовых знаков — переиспользуй её вместо сломанного `scores`-механизма:

```python
def best_city_name(self) -> str:
    """Наиболее вероятное название населённого пункта по голосованию OCR-наблюдений."""
    if not self.text_results:
        return ""
    return self.most_common(self.text_results)[0]
```

Заодно унифицируй обе реализации `_ocr_city()`, чтобы они всегда возвращали **простую строку** (без JSON-сериализации):

`processing/ocr_pool.py`, функция `_ocr_city()`:
```python
def _ocr_city(crop: np.ndarray) -> str:
    """OCR для городских знаков — возвращает лучшее совпадение с справочником городов."""
    global _worker_ocr_reader
    import difflib

    try:
        result = _worker_ocr_reader.readtext(crop)
        if not result:
            return ""
        best_text = max(result, key=lambda x: x[2])[1]

        try:
            from utils import resource_path
            cities_path = resource_path("static/cities_be.txt")
            with open(cities_path, encoding="utf-8") as f:
                cities = [line.strip().lower() for line in f if line.strip()]
        except Exception:
            cities = []

        if not cities:
            return best_text

        matches = difflib.get_close_matches(best_text.lower(), cities, n=1, cutoff=0.6)
        return matches[0] if matches else best_text
    except Exception as e:
        logger.warning(f"[OCRPool] OCR city failed: {e}")
        return ""
```

(Убрали `json.dumps`/`n=3` — теперь единообразно с `core/detector.py::_ocr_city()`, всегда одна строка, как ожидает и `best_city_name()`, и `most_common()`.)

**Важно:** это исправление затрагивает формат данных, уже сохранённых в старых GeoJSON. Не пытайся "мигрировать" старые файлы — просто убедись, что новые прогоны обработки дают корректный результат.

---

## 6. БАГ E (P2, второстепенный): знаки, ещё видимые в последних кадрах видео, теряются

### 6.1. Суть проблемы

`SignHandler._finalize_signs()` переносит знак из активного трекинга (`self.signs`) в `result_signs` **только** если он не наблюдался `DIFF_FRAMES_MOVE = 5` и более кадров подряд (то есть "исчез" из поля зрения):

```python
def _finalize_signs(self, current_frame: int) -> None:
    to_finalize = []
    for sign in self.signs:
        gone_long_enough = (current_frame - sign.frame_numbers[-1] >= self.DIFF_FRAMES_MOVE)
        has_enough_obs = sign.observation_count >= self.MIN_OBSERVATIONS
        if gone_long_enough and has_enough_obs:
            ...
```

Если видео заканчивается, пока знак **ещё виден** (или ещё не "истекли" 5 кадров с момента последнего наблюдения), он навсегда остаётся в `self.signs` и никогда не попадает ни в `result_signs`, ни в `turns`. `get_result_signs()`/`get_turn_data()` в `ProcessingController` эти "зависшие" знаки не видят и не возвращают — они просто теряются молча, без ошибок в логе.

Для длинных видео это единичные знаки (в последних 1-2 секундах), но для коротких тестовых клипов (типичный сценарий при отладке — 30-60 секунд) это может быть заметная доля всех знаков в кадре, что усиливает впечатление "знаки не сохраняются".

### 6.2. Требуемое исправление

Добавить в `SignHandler` метод принудительной финализации всех ещё активных знаков, соответствующих порогу `MIN_OBSERVATIONS`, не дожидаясь "исчезновения":

```python
def finalize_remaining(self) -> None:
    """
    Принудительно финализирует все ещё активные знаки, которые
    успели набрать минимум MIN_OBSERVATIONS наблюдений.
    Вызывается один раз в самом конце обработки видео (когда больше
    не будет новых кадров), чтобы не терять знаки, всё ещё видимые
    в последних кадрах.
    """
    to_finalize = [s for s in self.signs if s.observation_count >= self.MIN_OBSERVATIONS]
    for sign in to_finalize:
        self._set_side(sign)
        if not self._is_duplicate(sign):
            self.result_signs.append(sign)
        self.signs.remove(sign)
```

Вызвать этот метод:

- В `DetectorThread._process_loop()` — сразу после выхода из основного `while not self._stop:` цикла (перед `finally`-блоком в `run()`, либо в самом конце `_process_loop()`), один раз.
- В `ResultAggregatorThread.run()` (`processing/detector_process_pool.py`) — аналогично, один раз после того, как обработан последний `frame_data` (после цикла по `remaining = self._reorder_buffer.flush()`, перед `self.finished_work.emit()`).

**Не вызывай этот метод по таймеру/несколько раз** — только один раз, когда точно больше не будет новых кадров, иначе можно преждевременно финализировать знак, который на самом деле продолжит наблюдаться (что ухудшит точность геометрии знака).

---

## 7. Обязательные регресс-тесты

Добавь (или расширь, если что-то похожее уже существует, например `tests/test_tracked_sign_regression.py`) следующие тесты. Все — без запуска реального видео/GUI, чистые unit-тесты на изолированных объектах.

### 7.1. `tests/test_ocr_pipeline_regression.py` (новый файл)

```python
"""
Регресс-тесты для багов A/B: крах DetectorThread из-за .bbox
и потеря результата OCR при возврате в TrackedSign.
"""
import numpy as np


def test_detected_sign_has_no_bbox_attribute_by_design():
    """Документирует契 факт: DetectedSign НЕ имеет .bbox, только x/y/w/h.
    Если кто-то добавит property .bbox — тест не должен падать (ОК),
    но если кто-то уберёт x/y/w/h — тест должен упасть."""
    from core.frame import DetectedSign
    det = DetectedSign(
        x=10, y=20, w=30, h=40,
        name_sign="krug", number_sign="3.24",
        frame_number=1, absolute_frame_number=1,
        latitude=0.0, longitude=0.0,
    )
    assert (det.x, det.y, det.w, det.h) == (10, 20, 30, 40)


def test_submit_ocr_task_does_not_raise_attributeerror():
    """БАГ A: _submit_ocr_task не должен падать с AttributeError на bbox."""
    from processing.detector_thread import DetectorThread
    from core.sign import TrackedSign
    from core.frame import DetectedSign

    thread = DetectorThread.__new__(DetectorThread)  # без QThread.__init__
    thread._ocr_worker = None  # ранний return — метод не должен упасть
    thread._pending_ocr = {}
    thread._ocr_sign_counter = 0
    thread._using_ocr_pool = True

    tracked = TrackedSign()
    det = DetectedSign(
        x=5, y=5, w=10, h=10, name_sign="krug", number_sign="3.24",
        frame_number=1, absolute_frame_number=1, latitude=0.0, longitude=0.0,
    )
    tracked.append(det)

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Не должно бросать AttributeError, даже с ocr_worker=None (ранний return)
    thread._submit_ocr_task(tracked, frame)


def test_ocr_result_is_written_back_to_tracked_sign():
    """БАГ B: результат OCR должен попадать в TrackedSign.text_results."""
    from processing.detector_thread import DetectorThread
    from core.sign import TrackedSign

    thread = DetectorThread.__new__(DetectorThread)
    thread._pending_ocr = {}

    tracked = TrackedSign()
    thread._pending_ocr[0] = tracked

    class FakeResult:
        sign_id = 0
        text = "60"
        error = None

    thread._on_ocr_result_pool(FakeResult())

    assert "60" in tracked.text_results
    assert 0 not in thread._pending_ocr  # должен быть удалён из pending после обработки
```

### 7.2. `tests/test_ocr_cache_and_city_name.py` (новый файл)

```python
"""Регресс-тесты для багов C/D: OCR-кэш и best_city_name()."""


def test_best_city_name_uses_plain_strings():
    """БАГ D: best_city_name должен работать с обычными строками в text_results,
    а не требовать список кортежей (старый сломанный формат)."""
    from core.sign import TrackedSign

    sign = TrackedSign()
    sign.text_results = ["минск", "минск", "мiнск", "минск"]

    result = sign.best_city_name()
    assert result == "минск"


def test_best_city_name_empty_when_no_observations():
    from core.sign import TrackedSign
    sign = TrackedSign()
    assert sign.best_city_name() == ""


def test_detector_has_ocr_cache():
    """БАГ C: Detector должен иметь отдельный OCR-кэш (не совпадающий с CNN-кэшем)."""
    from core.detector import Detector
    detector = Detector()
    assert hasattr(detector, "_ocr_cache")
    assert detector._ocr_cache is not detector._cnn_cache
```

### 7.3. `tests/test_sign_handler_finalize_remaining.py` (новый файл)

```python
"""Регресс-тест для бага E: знаки, активные на момент конца видео."""
from core.frame import DetectedSign
from core.sign_handler import SignHandler


def test_finalize_remaining_saves_still_active_signs():
    handler = SignHandler()
    det = DetectedSign(
        x=100, y=100, w=50, h=50, name_sign="krug", number_sign="3.24",
        frame_number=1, absolute_frame_number=1, latitude=0.0, longitude=0.0,
    )
    # Имитируем 5 наблюдений одного знака (>= MIN_OBSERVATIONS=4)
    for i in range(5):
        det2 = DetectedSign(
            x=100 + i, y=100, w=50, h=50, name_sign="krug", number_sign="3.24",
            frame_number=1 + i, absolute_frame_number=1 + i,
            latitude=0.0, longitude=0.0,
        )
        handler._add_sign(det2) if i == 0 else handler.signs[-1].append(det2)

    assert len(handler.result_signs) == 0  # знак всё ещё "активен", видео не закончилось

    handler.finalize_remaining()

    assert len(handler.result_signs) == 1
    assert len(handler.signs) == 0
```

Скорректируй тест под реальный API `SignHandler`, если конструкция `handler._add_sign(det2)` / `handler.signs[-1].append(det2)` не совпадает 1-в-1 с текущей реализацией — главное, чтобы тест проверял именно поведение "знак с достаточным числом наблюдений, который никогда не 'исчезал', должен попасть в `result_signs` после вызова `finalize_remaining()`".

### 7.4. Прогон существующих тестов

Убедись, что после всех правок по-прежнему проходят:
- `tests/test_confidence.py`
- `tests/test_tracked_sign_regression.py`
- `tests/test_performance_optimizations.py`
- `scripts/test_detector_regression.py --compare` (если есть сохранённый baseline; если нет — создай новый через `--save-baseline` на любом коротком тестовом видео **до** внесения правок, если возможность запустить видео есть в окружении агента; если видео нет — пропусти этот пункт и явно укажи это в отчёте)

---

## 8. Чего категорически НЕ делать

Судя по истории документации в этом репозитории (`BUGFIX_PROCESS_POOL_0xC0000409.md`, `BUGFIX_0xC0000409_PIPELINE_SHUTDOWN.md`, `BUGFIX_VIDEO_FOLDER_CRASH_0xC0000409.md`, `CPU_OPT_SUMMARY.md` раздел про `OMP_NUM_THREADS`), в этом проекте уже случались тяжёлые, трудновоспроизводимые краши `STATUS_STACK_BUFFER_OVERRUN (0xC0000409)`, связанные с конфликтом OpenMP/MKL/Qt при неаккуратной работе с многопоточностью/многопроцессностью. Поэтому:

1. **Не трогай `OMP_NUM_THREADS`, `MKL_NUM_THREADS`, `torch.set_num_threads()` и другие переменные окружения** в `main.py`/`processing/detector_process_pool.py` в рамках этой задачи. Ни один из найденных багов (A-E) не требует этого.
2. **Не добавляй `try/except: pass` вокруг проблемных мест "чтобы не падало"** — это маскирует симптом, а не чинит причину. Баг A нужно исправить именно заменой `.bbox` на `.x/.y/.w/.h`, а не оборачиванием в try/except.
3. **Не переписывай архитектуру Process Pool целиком** в рамках обязательной части (Части 2-6) — только минимальный, безопасный OCR-кэш (Часть 4.3). Полный перенос OCR-троттлинга в аггрегатор (Часть 4.4) — опционально, отдельным коммитом, только если хватит времени/уверенности, и **обязательно** с отдельным тестированием на реальном видео перед тем, как считать его завершённым.
4. **Не удаляй `ReorderBuffer`, `seq`-логику, конвертацию координат WGS84→EPSG:32635** в `detector_process_pool.py` — это уже исправленные в прошлых сессиях баги (см. `STATUS.md`, `FIXES_PREVIEW_PROCESSING_SUMMARY.md`), не откатывай их случайно при рефакторинге соседнего кода.
5. **Не пиши в отчёте "исправлено и протестировано", если у тебя нет возможности реально прогнать код** (нет видео/GPX-файла/PyQt6-окружения в песочнице). Честно указывай: "код исправлен и логически проверен, юнит-тесты добавлены и проходят, но не проверено на реальном видео — требуется ручное тестирование пользователем" — как это принято в этом репозитории (см. `STATUS.md`, `FIXES_PREVIEW_PROCESSING_SUMMARY.md` — там чётко разделены "исправлено в коде" и "проверено вручную").
6. **Не создавай очередной "победный" markdown-отчёт с невалидированными утверждениями.** Если создаёшь отчёт о проделанной работе — обнови статус в существующем файле (например, дополни `STATUS.md`) вместо создания десятого нового файла `COMPLETION_REPORT_*.md` (в репозитории уже больше 15 таких файлов, это затрудняет навигацию).

---

## 9. План работ по приоритету

1. **P0.** Исправить баг A (`.bbox` → `.x/.y/.w/.h`) в `processing/detector_thread.py::_submit_ocr_task()`. Без этого Pipeline не работает вообще.
2. **P0.** Исправить баг B (сохранение ссылки на `TrackedSign`, а не одноразовый `DetectedSign`, дозапись `text_results`) — там же, плюс `_on_ocr_result()`/`_on_ocr_result_pool()`. Делать вместе с A, это одна логическая правка.
3. **P1.** Добавить OCR pHash-кэш (`core/detector.py::_read_text()`, новое поле `self._ocr_cache`) — баг C. Это главный фикс производительности Process Pool.
4. **P1.** Исправить `best_city_name()` в `core/sign.py` + унифицировать `_ocr_city()` в `processing/ocr_pool.py` — баг D.
5. **P2.** Добавить `SignHandler.finalize_remaining()` и вызвать его в конце `_process_loop()` (`DetectorThread`) и в конце `run()` (`ResultAggregatorThread`) — баг E.
6. **P0-P2 (обязательно).** Написать и прогнать регресс-тесты из Части 7.
7. **P3 (опционально, отдельным коммитом, только после успешной проверки P0-P2).** Полный перенос OCR-троттлинга в `ResultAggregatorThread` для Process Pool — Часть 4.4.
8. Обновить `STATUS.md` — что реально исправлено, что проверено юнит-тестами, что требует ручной проверки на реальном видео.

---

## 10. Ручной чек-лист проверки (для пользователя, после того как агент закончит)

Раздел для передачи пользователю — агент должен явно перечислить эти шаги в финальном отчёте как "требуется ручная проверка":

1. **Pipeline-режим:** Settings → "Pipeline" → обработать видео, содержащее хотя бы один знак с текстом/подписью в первые 30 секунд (например, ограничение скорости с уточняющей табличкой, или указатель населённого пункта). Проверить:
   - В логе обработки **нет** строк вида `AttributeError` / `has no attribute 'bbox'`.
   - Обработка идёт до конца видео (счётчик кадров растёт равномерно, а не "останавливается" через несколько секунд).
   - Итоговый GeoJSON содержит знаки на всём протяжении видео, а не только в первые секунды.
   - У текстовых знаков поле `SEM250`/`MVALUE` **не пустое** и соответствует тому, что видно на кадре.
   - У знаков-указателей населённых пунктов (`5.22.x`/`5.23.x`) название города **не пустое**.
2. **Process Pool режим:** обработать то же видео. Сравнить время обработки/FPS до и после фикса (лог `[SmartSkip] ... FPS: X.X`). Ожидается заметное ускорение (в разы) на видео с текстовыми знаками за счёт OCR-кэша (баг C).
3. **Single Thread режим:** прогнать как regression-контроль — поведение и результат не должны измениться относительно того, что было до этой правки (single_thread не затрагивался багами A/B/C, но C затрагивает и его — OCR-кэш добавляет пользу и здесь; итоговое число/состав знаков должно быть тем же или лучше, не хуже).
4. Сравнить количество найденных знаков между всеми тремя режимами на одном и том же видео — после фиксов они должны быть **сопоставимы** (не идентичны из-за случайности порядка обработки в Process Pool, но одного порядка величины), а не "Pipeline находит в 10 раз меньше, чем single_thread", как сейчас.
