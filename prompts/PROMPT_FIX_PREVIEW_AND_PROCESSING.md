# Промпт для ИИ-агента: починка предпросмотра кадра и обработки во ВСЕХ режимах (single_thread / pipeline / process_pool) × (CPU / GPU) — RoadScanner (Signer PRIME)

> Скопируй этот файл целиком в контекст ИИ-агента (Claude Code / Cursor / аналог),
> имеющего прямой доступ к репозиторию. Документ написан на основе построчного
> чтения **актуального** кода (не исторических `.md`-отчётов в корне репозитория —
> они, как многократно подтверждено в этом же репозитории, систематически
> расходятся с реальным состоянием кода). Каждый баг ниже подтверждён цитатой
> реального кода и объяснением механизма поломки. Перед правками перечитай
> указанные файлы заново — они могли ещё раз измениться после написания
> этого промпта.

---

## 0. Как это устроено — экспресс-резюме для нетерпеливых

Предпросмотр кадра технически устроен одинаково для всех трёх режимов обработки
(`single_thread`, `pipeline`, `process_pool`): воркер (QThread или worker-процесс)
собирает сырой BGR-кадр через `processing/preview_utils.py::build_frame_dict()`
(без создания Qt-объектов — это обязательно, `QPixmap`/`QImage` нельзя создавать
вне GUI-потока), эмитит `dict` через сигнал `frame_ready`, а
`ProcessingController._on_worker_frame_ready()` в главном потоке конвертирует
`dict` → `QPixmap` через `build_pixmap_from_frame_dict()` и отдаёт в
`ProcessingPage.set_frame()`. **Эта часть архитектуры в текущем коде корректна
для всех трёх режимов** — Qt-threading здесь не нарушен, я проверил каждое
звено цепочки сигналов построчно.

Настоящая причина, по которой предпросмотр (и вообще вся обработка) **не
работает в режиме Process Pool** — не Qt-threading, а два самостоятельных бага
в `processing/detector_process_pool.py`:

1. **`ReorderBuffer` никогда не отдаёт ни одного кадра до самого конца видео**
   (Часть 1) — из-за этого в Process Pool нет ни живого превью, ни
   инкрементального накопления знаков: всё случается одним гигантским батчем
   в момент, когда `VideoReaderThread` уже дочитал файл до конца.
2. **Координаты знака не конвертируются из WGS84 в EPSG:32635** перед тем, как
   попасть в `SignHandler`/`TrackedSign` (Часть 2) — это в точности та же
   «Африка-баг», которая была найдена и исправлена в `DetectorThread`
   (см. исторический `BUGFIX_COORDINATES_AFRICA.md`), но фикс **не был
   продублирован** в `DetectorProcessPool`, из-за чего все знаки, найденные в
   режиме Process Pool, улетают на координаты около экватора.

Плюс — две настройки, которые есть в UI, но **не подключены ни к какому
реальному поведению** (Часть 3): количество воркеров Process Pool и режим
шага кадра (авто/вручную).

`single_thread` и `pipeline` режимы (оба реализованы в `DetectorThread`)
архитектурно корректны — в них я не нашёл багов предпросмотра при построчном
чтении. Для них в конце документа — чек-лист ручной проверки (Часть 6), а не
диффы, потому что чинить там нечего, только проверять.

---

## 1. КРИТИЧНО: `ReorderBuffer` в Process Pool никогда не отдаёт кадры до самого конца видео

### 1.1. Точная причина

Файл `processing/detector_process_pool.py`, класс `ReorderBuffer`:

```python
class ReorderBuffer:
    def __init__(self, max_gap: int = 32):
        self._buffer: dict[int, dict] = {}
        self._next_expected: int = 0          # <-- начинается с 0
        self._max_gap = max_gap

    def add(self, frame_data: dict) -> list[dict]:
        frame_idx = frame_data['frame_idx']    # <-- ключ = abs_frame_number
        self._buffer[frame_idx] = frame_data

        ready = []
        while self._next_expected in self._buffer:
            ready.append(self._buffer.pop(self._next_expected))
            self._next_expected += 1           # <-- шаг +1
        ...
```

Ключом для буфера и «ожидаемым следующим номером» служит `frame_data['frame_idx']`,
которому присваивается `raw.abs_frame_number` (см. `_submit_loop()` ниже). Но
`abs_frame_number` **никогда не равен 0 для первого обработанного кадра** и
**никогда не идёт последовательно +1** — он идёт с шагом `FRAME_STEP` (по
умолчанию 5). Смотри `processing/video_reader.py::_read_all_videos()`:

```python
local_frame = 0
...
frame_counter = 0

while True:
    ...
    with profiler.measure("video_grab_frame"):
        grabbed = cap.grab()
    ...
    local_frame += 1
    frame_counter += 1

    if frame_counter % step != 0:
        continue                       # пропускаем — НЕ ретривим и НЕ кладём в очередь

    with profiler.measure("video_retrieve_frame"):
        ret, image = cap.retrieve()
    ...
    frame_in_video = local_frame

    if video_idx == 0:
        abs_frame = local_frame
    else:
        abs_frame = (video_idx * config.FRAMES_PER_VIDEO) + local_frame
    ...
    raw = RawFrame(
        image            = image,
        frame_number     = frame_in_video,
        abs_frame_number = abs_frame,
        ...
    )
```

`local_frame` и `frame_counter` стартуют с 0 и увеличиваются на 1 **на каждом
grab()**, включая пропускаемые кадры. Первый кадр, для которого выполняется
`frame_counter % step == 0` (то есть первый реально обрабатываемый кадр),
наступает при `frame_counter == step`, и в этот момент `local_frame` тоже
равен `step` (оба счётчика всегда синхронно равны друг другу). Значит:

- при `FRAME_STEP=5` (дефолт) первый кадр в очереди имеет `abs_frame_number = 5`,
  второй — `10`, третий — `15`, и т.д.;
- **даже при `FRAME_STEP=1`** первый кадр имеет `abs_frame_number = 1`, а не `0`.

Итог: `ReorderBuffer._next_expected` стартует с `0`, но значение `0` **никогда
не появится** в `self._buffer` — ни для одного видео с любым `FRAME_STEP >= 1`.
Значит `while self._next_expected in self._buffer:` **никогда не выполнится ни
разу**, `ready` всегда пустой список, и `_process_result()` никогда не
вызывается из `add()`.

### 1.2. Почему «защита от разрыва» (`gap > max_gap`) не спасает

```python
        if self._buffer:
            min_buffered = min(self._buffer.keys())
            gap = min_buffered - self._next_expected
            if gap > self._max_gap:
                logger.warning(...)
                self._next_expected = min_buffered
                return self.add(frame_data)
        return ready
```

Раз `_next_expected` никогда не увеличивается (нет ни одного успешного
`pop`), а самый старый непопнутый ключ в буфере (`min_buffered`) остаётся тем
же самым первым кадром (5, например) **вечно**, пока хоть что-то не выбьет его
из буфера — а выбить его может только сам этот же `while`-цикл, которому
нечего сопоставлять. Значит `gap = min_buffered - self._next_expected` — это
**константа**, равная номеру самого первого пришедшего кадра (то есть
`FRAME_STEP`, обычно 5), и она **никогда не растёт**, потому что новые кадры
добавляются «сверху» (10, 15, 20…), а `min_buffered` как был 5, так и
остаётся 5. При `max_gap = 32` (дефолт, `config.REORDER_BUFFER_MAX_GAP`) эта
константа (5) никогда не превысит 32 — защитный механизм не срабатывает
вообще никогда.

### 1.3. К чему это приводит на практике

`_process_result()` (который и обновляет `SignHandler`, и эмитит превью,
и обновляет статистику `stats_updated`) вызывается **только внутри
`add()`** — а раз `add()` всегда возвращает пустой список, `_process_result()`
не вызывается **вообще ни разу за всё время обработки видео**, кроме одного
единственного момента — когда `ResultAggregatorThread.run()` доходит до конца
и вызывает `flush()`:

```python
def run(self):
    ...
    try:
        while not self._stop:
            ...
            if future is None:      # sentinel — reader дочитал видео до конца
                break
            ...
            ready_frames = self._reorder_buffer.add(result)  # <-- ВСЕГДА []
            for frame_data in ready_frames:
                self._process_result(frame_data)
        # Финальная очистка буфера
        remaining = self._reorder_buffer.flush()   # <-- ВСЁ видео разом, тут
        for frame_data in remaining:
            self._process_result(frame_data)        # <-- тут
        ...
```

То есть в режиме Process Pool: **предпросмотр не обновляется вообще (заглушка
на весь ход обработки), счётчики кадров/знаков/FPS в UI не двигаются, а в
момент, когда чтение видео заканчивается, ВСЕ кадры всего видео разом
прогоняются через `SignHandler.check_the_data_to_add()`** одним циклом (в
порядке `sorted(self._buffer.items())`, т.е. по `frame_idx` — тут порядок хотя
бы правильный, но всё внутри одного тяжёлого блокирующего цикла без единого
промежуточного `frame_ready`). Именно так и выглядит симптом «предпросмотр не
работает, а обработка либо зависает в конце, либо “что-то делает” без
видимого прогресса» — это не подвисание, это гигантский синхронный дамп в
конце.

### 1.4. Важное наблюдение, упрощающее фикс

Порядок поступления результатов в `ResultAggregatorThread.run()` **уже
гарантированно правильный** без всякого `ReorderBuffer`, потому что:

```python
future: Future = self._futures_q.get(timeout=0.2)   # FIFO — забираем в порядке submit()
...
result = future.result(timeout=10.0)                # БЛОКИРУЕМСЯ именно на этом future
```

`self._futures_q` — обычная `queue.Queue` (FIFO), в неё кладут `future` в
`_submit_loop()` строго в том порядке, в каком `VideoReaderThread` кладёт
кадры в `frame_queue` (монотонно возрастающий порядок). Аггрегатор
всегда забирает из `_futures_q` следующий по очереди future и **блокируется
на `.result()` именно на нём**, а не на «первом завершившемся» — то есть даже
если процессы-воркеры закончат обработку кадров в другом порядке, аггрегатор
всё равно дождётся именно нужного future и обработает результаты строго по
порядку отправки. **`ReorderBuffer` в этой архитектуре не устраняет
реальный беспорядок (его и так нет), а является избыточным защитным
слоем** — но раз уж он есть и настолько сломан, чинить его нужно, а не
удалять (удаление — более рискованный рефакторинг, минимальный фикс безопаснее).

### 1.5. Фикс — привязать буфер к строго последовательному `seq`, а не к `frame_idx`

Добавь отдельный, строго последовательный (0, 1, 2, 3…) счётчик отправки
кадров, никак не связанный с `abs_frame_number`/`FRAME_STEP`, и используй
именно его как ключ `ReorderBuffer`. Поле `frame_idx` (реальный
`abs_frame_number`) оставь как есть — оно по-прежнему нужно ниже по потоку
для `config.INDEX_OF_All_FRAME`, привязки к GPS и т.д.

**`processing/detector_process_pool.py`, класс `ReorderBuffer`:**

```python
class ReorderBuffer:
    """
    Буфер для восстановления правильного порядка кадров.

    ВАЖНО (BLOCK PREVIEW-FIX-1): ключ упорядочивания — 'seq', строго
    последовательный счётчик (0, 1, 2, ...), присваиваемый
    DetectorProcessPool._submit_loop() в момент отправки кадра воркеру.
    НЕЛЬЗЯ использовать 'frame_idx' (= raw.abs_frame_number) в этой роли:
    abs_frame_number растёт с шагом FRAME_STEP (обычно 5) и НИКОГДА не
    равен 0 для первого кадра, поэтому _next_expected=0 никогда не находил
    совпадения в self._buffer, add() всегда возвращал [] и все кадры
    накапливались до единственного flush() в самом конце обработки —
    отсюда «нет предпросмотра» и «всё случается одним махом в конце».
    См. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 1.
    """

    def __init__(self, max_gap: int = 32):
        self._buffer: dict[int, dict] = {}
        self._next_expected: int = 0
        self._max_gap = max_gap

    def add(self, frame_data: dict) -> list[dict]:
        seq = frame_data['seq']
        self._buffer[seq] = frame_data

        ready = []
        while self._next_expected in self._buffer:
            ready.append(self._buffer.pop(self._next_expected))
            self._next_expected += 1

        if self._buffer:
            min_buffered = min(self._buffer.keys())
            gap = min_buffered - self._next_expected
            if gap > self._max_gap:
                logger = logging.getLogger(__name__)
                logger.warning(f"[ReorderBuffer] gap={gap} > max_gap={self._max_gap}, "
                              f"skipping frames seq {self._next_expected}-{min_buffered}")
                self._next_expected = min_buffered
                return self.add(frame_data)

        return ready

    def flush(self) -> list[dict]:
        remaining = sorted(self._buffer.items())
        self._buffer.clear()
        return [frame_data for _, frame_data in remaining]

    def __len__(self) -> int:
        return len(self._buffer)
```

**`DetectorProcessPool.__init__`** — добавь счётчик отправки:

```python
def __init__(self, frame_queue: queue.Queue, parent=None):
    super().__init__(parent)
    self._frame_q = frame_queue
    self._num_workers = self._detect_optimal_workers()
    self._executor: Optional[ProcessPoolExecutor] = None
    self._reorder_buffer = ReorderBuffer(max_gap=config.REORDER_BUFFER_MAX_GAP)
    self._futures_q: queue.Queue = queue.Queue(maxsize=self._num_workers * 4)
    self._submit_seq = 0                      # NEW (BLOCK PREVIEW-FIX-1)
    self._sign_handler = None
    self._gpx = None
    self._aggregator: Optional[ResultAggregatorThread] = None
    self._submitter_thread: Optional[QThread] = None
    self._stop = False
    ...
```

**`DetectorProcessPool._submit_loop()`** — присваивай и передавай `seq`:

```python
def _submit_loop(self):
    logger = logging.getLogger(__name__)
    try:
        while not self._stop:
            try:
                raw: RawFrame = self._frame_q.get(timeout=0.2)
            except queue.Empty:
                continue

            if raw is _STOP:
                logger.debug("[DetectorProcessPool] Получен _STOP, завершаем submit loop")
                break

            frame_data = {
                'seq': self._submit_seq,               # NEW — строго 0,1,2,3,...
                'frame_idx': raw.abs_frame_number,      # без изменений
                'frame_number': raw.frame_number,
                'video_idx': raw.video_index,
                'video_name': raw.video_name,
                'image_bytes': raw.image.tobytes(),
                'image_shape': raw.image.shape,
                'gps_data': {'gps_index': raw.gps_index},
            }
            self._submit_seq += 1                       # NEW

            if self._executor is None:
                logger.warning("[DetectorProcessPool] Executor is None, прерываем submit loop")
                break

            try:
                future = self._executor.submit(_worker_process_frame, frame_data)
                self._futures_q.put(future)
            except Exception as e:
                logger.error(f"[DetectorProcessPool] Ошибка submit: {e}")
                break

        logger.debug("[DetectorProcessPool] Отправка sentinel в futures_q")
        self._futures_q.put(None)

    except Exception as e:
        self.error.emit(f"Submitter error: {e}")
```

**`_worker_process_frame()`** — прокинь `seq` через результат (worker-процесс
не должен ничего с ним делать, только вернуть обратно как есть):

```python
    return {
        'seq': raw_frame_data['seq'],                                     # NEW
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

**Проверь**, что нигде больше `frame_data['frame_idx']` не используется как
ключ упорядочивания (только `ReorderBuffer.add()` — остальные места типа
`config.INDEX_OF_All_FRAME = frame_data['frame_idx']` в `_process_result()`
использовать `frame_idx` **правильно и нужно оставить как есть** — это не
про упорядочивание, это про реальный номер кадра для GPS/времени/итогового
GeoJSON).

### 1.6. Тест-регрессия (обязательно добавить)

Создай `tests/test_reorder_buffer.py`:

```python
"""
tests/test_reorder_buffer.py
Регрессионный тест на баг с ReorderBuffer в Process Pool режиме —
см. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 1.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processing.detector_process_pool import ReorderBuffer


def test_reorder_buffer_releases_first_frame_immediately():
    """
    Регрессия: раньше буфер ждал frame_idx == 0, которого никогда не было
    (реальный abs_frame_number первого кадра == FRAME_STEP, например 5).
    После фикса буфер ключуется по 'seq' (0,1,2,...), присваиваемому
    submitter'ом, и должен отдать первый кадр сразу же, без ожидания
    остальных 31 (max_gap) кадров.
    """
    buf = ReorderBuffer(max_gap=32)
    frame = {"seq": 0, "frame_idx": 5, "payload": "first"}
    ready = buf.add(frame)
    assert ready == [frame], (
        "ReorderBuffer должен немедленно отдать самый первый кадр (seq=0), "
        "а не ждать flush() в конце видео"
    )


def test_reorder_buffer_handles_frame_step_stride_and_reordering():
    """
    Имитация реального FRAME_STEP=5: frame_idx растёт как 5,10,15,...,
    но seq присваивается строго последовательно submitter'ом. Воркеры
    могут завершиться не в том порядке, в котором были отправлены —
    буфер должен восстановить порядок по seq.
    """
    buf = ReorderBuffer(max_gap=32)
    frames = [
        {"seq": 2, "frame_idx": 15},
        {"seq": 0, "frame_idx": 5},
        {"seq": 1, "frame_idx": 10},
        {"seq": 4, "frame_idx": 25},
        {"seq": 3, "frame_idx": 20},
    ]
    released = []
    for f in frames:
        released.extend(buf.add(f))

    assert [r["frame_idx"] for r in released] == [5, 10, 15, 20, 25], (
        "Кадры должны выходить из буфера строго по возрастанию frame_idx "
        "(что эквивалентно возрастанию seq), независимо от порядка поступления"
    )


def test_reorder_buffer_gap_safety_valve_still_works():
    """
    Если какой-то seq потерян навсегда (например, воркер упал и future
    никогда не вернул результат для него — в реальном коде такие future
    просто не попадают в буфер вообще, но проверим что buffer не виснет
    вечно, если появляется настоящий разрыв seq > max_gap).
    """
    buf = ReorderBuffer(max_gap=5)
    # seq=0 никогда не придёт (потерян/пропущен)
    for seq in range(1, 10):
        released = buf.add({"seq": seq, "frame_idx": seq * 5})
    # После накопления достаточного разрыва буфер должен самовосстановиться
    # и начать отдавать кадры, не дожидаясь пропавшего seq=0 вечно.
    assert len(buf) < 9, "Буфер должен был сработать через gap-защиту и что-то отдать"


if __name__ == "__main__":
    test_reorder_buffer_releases_first_frame_immediately()
    test_reorder_buffer_handles_frame_step_stride_and_reordering()
    test_reorder_buffer_gap_safety_valve_still_works()
    print("[OK] Все тесты ReorderBuffer прошли")
```

Прогони: `python tests/test_reorder_buffer.py` — все три должны пройти
**после** фикса из 1.5, и первый/второй должны **падать до фикса** (это и
подтверждает, что баг реален — проверь на исходном коде перед правкой, если
хочешь дополнительно убедиться).

---

## 2. КРИТИЧНО: координаты знаков в Process Pool не конвертируются WGS84 → EPSG:32635 («Африка-баг», регрессия)

### 2.1. Точная причина

Это та же самая проблема, что уже была найдена и исправлена **только в
`DetectorThread`** (историческая справка в `BUGFIX_COORDINATES_AFRICA.md`),
но фикс не был продублирован в `DetectorProcessPool`.

`core/gpx_handler.py::GPXHandler.get_current_coordinate()` возвращает
координаты в **WGS84** (градусы, `lat≈53.9, lon≈27.5` для Беларуси):

```python
def get_current_coordinate(self, index: int) -> tuple[float, float]:
    pt = self.get_point(index)
    if pt is None:
        return (0.0, 0.0)
    return (pt.latitude, pt.longitude)
```

А `core/frame.py::DetectedSign.latitude/longitude` по контракту должны
содержать координаты автомобиля **уже в EPSG:32635** (метры, UTM):

```python
@dataclass(slots=True)
class DetectedSign:
    ...
    latitude:              float # координата автомобиля X (EPSG:32635, метры)
    longitude:             float # координата автомобиля Y (EPSG:32635, метры)
```

**В `DetectorThread._build_detected()` (правильно, конвертация ЕСТЬ):**

```python
def _build_detected(self, detections, raw):
    result = []
    lat, lon = config.INDEX_OF_GPS, 0.0
    try:
        lat, lon = self._gpx.get_current_coordinate(raw.gps_index)
        if lat != 0.0 and lon != 0.0:
            lat, lon = self._converter.coordinateConverter(
                lat, lon, "epsg:4326", "epsg:32635"
            )
    except Exception:
        pass
    for item in detections:
        ...
        result.append(DetectedSign(..., latitude=lat, longitude=lon, ...))
    return result
```

**В `processing/detector_process_pool.py::ResultAggregatorThread._build_detected_signs()`
(баг, конвертации НЕТ):**

```python
def _build_detected_signs(self, frame_data: dict):
    from core.frame import DetectedSign
    result = []
    lat, lon = 0.0, 0.0
    try:
        gps_index = frame_data.get('gps_data', {}).get('gps_index', 0)
        lat, lon = self._gpx.get_current_coordinate(gps_index)   # <-- WGS84, БЕЗ конвертации!
    except Exception:
        pass
    for det in frame_data['detections']:
        result.append(DetectedSign(
            ...
            latitude=lat,     # <-- сюда попадает 53.9 вместо ~549933
            longitude=lon,    # <-- сюда попадает 27.5 вместо ~5979471
            ...
        ))
    return result
```

### 2.2. К чему это приводит

`TrackedSign._append_car_coord()` (`core/sign.py`) кладёт эти «сырые» WGS84
значения в `car_x`/`car_y`, которые везде ниже по потоку (`CoordinateCalculation`,
`OSMSnapper`, `FinalHandler`) трактуются как метры EPSG:32635. Итог — знаки,
найденные в режиме Process Pool, оказываются на координатах в районе экватора
(0°–1° широты), т.е. буквально «в Африке», как это уже было описано и
исправлено для `DetectorThread` в предыдущем цикле фиксов, только для
Process Pool этот же баг остался нетронутым.

### 2.3. Фикс

**`processing/detector_process_pool.py`, `ResultAggregatorThread.__init__`** —
добавь `Converter`:

```python
    def __init__(
        self,
        futures_queue: queue.Queue,
        reorder_buffer: ReorderBuffer,
        sign_handler,
        gpx_handler,
        parent=None,
    ):
        super().__init__(parent)
        self._futures_q = futures_queue
        self._reorder_buffer = reorder_buffer
        self._sign_handler = sign_handler
        self._gpx = gpx_handler

        # NEW (BLOCK PREVIEW-FIX-2): нужен для конвертации WGS84 -> EPSG:32635,
        # см. _build_detected_signs() ниже и PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 2.
        from core.converter import Converter
        self._converter = Converter()

        self._stop = False
        ...
```

**`ResultAggregatorThread._build_detected_signs()`** — добавь конвертацию,
один в один как в `DetectorThread._build_detected()`:

```python
    def _build_detected_signs(self, frame_data: dict):
        """
        Fix 1.2 (историческая правка): конвертирует serialized detections
        в DetectedSign objects. Портировано из DetectorPool._build_detected_signs().

        BLOCK PREVIEW-FIX-2: добавлена конвертация координат WGS84 -> EPSG:32635,
        без которой все знаки, найденные в режиме Process Pool, оказывались
        на координатах около экватора («Африка-баг»). Тот же фикс уже был
        применён в DetectorThread._build_detected() ранее — здесь он был
        пропущен. См. Часть 2 промпта.
        """
        from core.frame import DetectedSign

        result = []
        lat, lon = 0.0, 0.0

        try:
            gps_index = frame_data.get('gps_data', {}).get('gps_index', 0)
            lat, lon = self._gpx.get_current_coordinate(gps_index)
            if lat != 0.0 and lon != 0.0:
                lat, lon = self._converter.coordinateConverter(
                    lat, lon, "epsg:4326", "epsg:32635"
                )
        except Exception:
            pass

        for det in frame_data['detections']:
            result.append(DetectedSign(
                x=det['box'][0],
                y=det['box'][1],
                w=det['box'][2],
                h=det['box'][3],
                name_sign=det['yolo_class'],
                number_sign=det['cnn_class'],
                frame_number=frame_data.get('frame_number', frame_data['frame_idx']),
                absolute_frame_number=frame_data['frame_idx'],
                latitude=lat,
                longitude=lon,
                text_on_sign=det.get('text', ''),
                is_side=det.get('is_side', False),
            ))

        return result
```

### 2.4. Тест-регрессия

Добавь в `tests/test_reorder_buffer.py` (или отдельный файл
`tests/test_process_pool_coordinates.py`) простой тест на конвертацию:

```python
def test_build_detected_signs_converts_to_epsg32635(monkeypatch):
    """
    Регрессия «Африка-баг»: latitude/longitude в DetectedSign должны быть
    в EPSG:32635 (метры, обычно сотни тысяч), а не в WGS84 (градусы, < 180).
    """
    from processing.detector_process_pool import ResultAggregatorThread

    class FakeGPX:
        def get_current_coordinate(self, idx):
            return (53.9021, 27.5612)  # Минск, WGS84

    agg = ResultAggregatorThread.__new__(ResultAggregatorThread)  # обходим __init__ QThread
    from core.converter import Converter
    agg._gpx = FakeGPX()
    agg._converter = Converter()

    frame_data = {
        "frame_idx": 100,
        "frame_number": 100,
        "gps_data": {"gps_index": 5},
        "detections": [
            {"box": [10, 10, 20, 20], "yolo_class": "krug", "cnn_class": "3.24",
             "text": "", "is_side": False}
        ],
    }

    signs = agg._build_detected_signs(frame_data)
    assert len(signs) == 1
    lat, lon = signs[0].latitude, signs[0].longitude

    # WGS84 координаты всегда в диапазоне [-180, 180]; EPSG:32635 (UTM, зона 35N)
    # для Беларуси — это величины порядка 300000-700000 (X) и 5900000-6200000 (Y).
    assert abs(lat) > 1000 or abs(lon) > 1000, (
        f"Координаты ({lat}, {lon}) похожи на WGS84 градусы — конвертация "
        f"в EPSG:32635 не сработала (снова 'Африка-баг')"
    )
```

---

## 3. Настройки, которые есть в UI, но ни на что не влияют

### 3.1. «Количество воркеров» (`process_pool_workers`) игнорируется

`configs/settings.py`:
```python
process_pool_workers: int = 0  # 0 = auto (cpu_count - 1)
```
UI-контрол `_workers_spin` в `settings_page.py` сохраняет значение в
`AppSettings.process_pool_workers` исправно. Но
`DetectorProcessPool._detect_optimal_workers()` **никогда его не читает**:

```python
def _detect_optimal_workers(self) -> int:
    if config.N_WORKERS is not None:
        return max(1, config.N_WORKERS)
    cpu_count = os.cpu_count() or 4
    optimal = max(2, min(8, cpu_count - 1))
    return optimal
```

`config.N_WORKERS` нигде не присваивается (проверено по всему коду) — значит
всегда `None`, и метод всегда идёт по ветке автоопределения. Пользователь
может выставить в Settings хоть «16 воркеров», хоть «1 воркер» — реально
будет использовано `max(2, min(8, cpu_count - 1))` в любом случае.

**Фикс** — читать настройку в первую очередь:

```python
def _detect_optimal_workers(self) -> int:
    """
    Порядок приоритета:
    1) AppSettings.process_pool_workers, если пользователь явно задал > 0
       (Settings UI -> "Количество воркеров")
    2) config.N_WORKERS, если когда-либо будет установлен программно
    3) автоопределение по cpu_count
    """
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if settings.process_pool_workers and settings.process_pool_workers > 0:
            return max(1, settings.process_pool_workers)
    except Exception:
        pass

    if config.N_WORKERS is not None:
        return max(1, config.N_WORKERS)

    cpu_count = os.cpu_count() or 4
    return max(2, min(8, cpu_count - 1))
```

### 3.2. «Шаг кадра» (`frame_step_mode` / `frame_step_manual`) игнорируется

`configs/settings.py`:
```python
frame_step_mode: Literal["auto", "manual"] = "auto"
frame_step_manual: int = 5
```
UI-контролы `_frame_mode_combo`/`_frame_step_spin` в `settings_page.py`
исправно сохраняют значения. Но `processing/processing_controller.py::
ProcessingController._reset_config()` (вызывается в начале **каждого**
`start()`) жёстко перезаписывает шаг:

```python
def _reset_config(self) -> None:
    config.FRAME_STEP           = 5     # <-- всегда 5, настройка не читается
    config.COUNT_PROCESSED_FRAMES = 0
    config.INDEX_OF_FRAME       = 0
    config.INDEX_OF_VIDEO       = 0
    config.INDEX_OF_All_FRAME   = 0
    config.INDEX_OF_GPS         = 0
    config.INDEX_OF_SING        = 0
```

**Фикс:**

```python
def _reset_config(self) -> None:
    """Сброс всех индексов перед началом обработки."""
    from configs.settings import get_app_settings
    settings = get_app_settings()

    if settings.frame_step_mode == "manual" and settings.frame_step_manual > 0:
        config.FRAME_STEP = max(1, int(settings.frame_step_manual))
    else:
        # "auto": базовый шаг чтения видео остаётся стандартным; дополнительная
        # адаптивная подстройка по скорости уже делается отдельно внутри
        # DetectorThread._calc_skip_interval() поверх этого базового шага —
        # это НЕ то же самое поле и трогать его тут не нужно.
        config.FRAME_STEP = 5

    config.COUNT_PROCESSED_FRAMES = 0
    config.INDEX_OF_FRAME       = 0
    config.INDEX_OF_VIDEO       = 0
    config.INDEX_OF_All_FRAME   = 0
    config.INDEX_OF_GPS         = 0
    config.INDEX_OF_SING        = 0
```

**Важно:** не путай `config.FRAME_STEP` (грубый шаг чтения кадров из файла,
применяется в `VideoReaderThread`) с внутренним адаптивным
`DetectorThread._current_skip`/`_calc_skip_interval()` (дополнительный,
основанный на скорости движения, слой пропуска поверх уже прочитанных
кадров). Это два независимых механизма, оба должны остаться рабочими —
фикс касается только первого.

---

## 4. Кэширование device (CPU/GPU) моделей между запусками в рамках одной сессии приложения

### 4.1. Симптом

Пользователь переключает «Использовать CUDA» в Settings **между** запусками
обработки (не перезапуская приложение) — переключатель визуально сохраняется,
но реальное поведение (какой device реально используется моделями) **не
меняется** до перезапуска всего приложения.

### 4.2. Причина

`configs/sign_models.py::_LazyModel` — модели являются **модульными
синглтонами** (`model_side_detect`, `rube_modal`, `model_dict{...}`,
`sub_models{...}`, `model_lane_detect`, `model_lane_segment` — все создаются
один раз на уровне модуля при импорте `configs.sign_models` и живут всё время
работы процесса приложения):

```python
class _LazyModel:
    def __init__(self, path_fn):
        self._path_fn = path_fn
        self._model   = None
        self._device  = None

    def _load(self):
        if self._model is None:            # <-- грузится и кэшируется НАВСЕГДА
            from ultralytics import YOLO
            self._device = _resolve_device()
            self._model = YOLO(self._path_fn())
            self._model.to(self._device)
        return self._model
```

`self._model is None` — единственное условие перезагрузки. Как только модель
загружена (на CPU или на GPU — в зависимости от того, что было в настройках
**в момент первой загрузки**), она остаётся с этим device до конца жизни
процесса приложения, даже если пользователь потом поменяет `use_cuda` в
Settings и запустит новую обработку.

### 4.3. Рекомендуемый фикс (низкий риск: проверка device делается один раз
на старте прогона, а не на каждый вызов `.predict()`)

Не делай проверку внутри `_load()` (она дёргается на **каждый** вызов
`.predict()`/`.__call__()`, то есть на каждый кадр — добавление туда чтения
`QSettings` на каждый инференс — это measurable overhead на десятках тысяч
кадров). Вместо этого сделай явный сброс кэша один раз в начале
`ProcessingController.start()`, если `use_cuda` реально изменился с прошлого
запуска:

**`configs/sign_models.py`** — добавь функцию сброса и запоминание последнего
резолвнутого device:

```python
_last_resolved_device: str | None = None


def _resolve_device() -> str:
    """
    Определяет device для YOLO-моделей на основе настроек и доступности CUDA.
    Возвращает "cuda:0" если use_cuda=True и CUDA доступна, иначе "cpu".
    """
    try:
        from configs.settings import get_app_settings
        import torch
        settings = get_app_settings()
        if settings.use_cuda and torch.cuda.is_available():
            return "cuda:0"
    except Exception:
        pass
    return "cpu"


def reload_all_models_if_device_changed() -> bool:
    """
    Вызывать ОДИН РАЗ в начале ProcessingController.start() (не на каждый
    кадр!). Если пользователь поменял 'Использовать CUDA' в Settings между
    прогонами в рамках одной сессии приложения, сбрасывает кэш всех
    _LazyModel, чтобы они перезагрузились на новом device при следующем
    обращении. См. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 4.

    Returns:
        True если модели были сброшены (device реально изменился).
    """
    global _last_resolved_device
    current = _resolve_device()
    if _last_resolved_device is not None and _last_resolved_device != current:
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[sign_models] Device изменился {_last_resolved_device} -> {current}, "
                    f"сбрасываем кэш моделей")
        for m in (model_side_detect, rube_modal, model_lane_detect, model_lane_segment):
            m._model = None
            m._device = None
        for m in model_dict.values():
            m._model = None
            m._device = None
        for m in sub_models.values():
            m._model = None
            m._device = None
        _last_resolved_device = current
        return True
    _last_resolved_device = current
    return False
```

**`processing/processing_controller.py::ProcessingController.start()`** —
вызови это один раз перед стартом:

```python
def start(self) -> None:
    if self._running:
        return

    self._reset_config()

    from configs.settings import get_app_settings
    settings = get_app_settings()
    config.PROCESSING_MODE = settings.processing_mode

    # NEW (BLOCK PREVIEW-FIX-4): подхватить изменение "Использовать CUDA"
    # без перезапуска приложения, если пользователь переключил его со
    # времени последнего прогона.
    try:
        from configs.sign_models import reload_all_models_if_device_changed
        reload_all_models_if_device_changed()
    except Exception:
        pass

    ...
```

Также применимо для EasyOCR (`core/detector.py::_get_ocr()`) — тот же паттерн
модульного синглтона (`_ocr_reader`), тот же класс проблемы. Если решишь
чинить и его — добавь туда аналогичный сброс `global _ocr_reader; _ocr_reader
= None` внутри той же функции `reload_all_models_if_device_changed()` (или
рядом), не обязательно, но по-хорошему нужно для полной консистентности
между "Use CUDA" и OCR-инференсом.

Если считаешь это избыточным усложнением для редкого сценария — минимальная
альтернатива: просто не чини это в коде, а явно предупреди пользователя в
tooltip рядом с переключателем `_cuda_toggle` в `settings_page.py`:
*"Изменения вступят в силу после перезапуска приложения"*. Выбери один из
двух вариантов и реализуй его — не оставляй как сейчас (тихо не работает
без объяснения).

---

## 5. Второстепенные находки (не блокирующие, но стоит знать/поправить)

Эти пункты — **не обязательны** для починки предпросмотра/базовой
обработки, но относятся к «также почини обработку» и напрямую связаны с
разницей CPU/GPU режимов. Делай их после Частей 1–4, с отдельными коммитами.

### 5.1. Process Pool не использует CNN-skip кэш и OCR-троттлинг по TrackedSign

`_worker_process_frame()` вызывает `detector.detect(image)` (обычный путь),
а не `detector.detect_with_tracking(image, tracked_map, ...)`, который
используют `single_thread`/`pipeline` через `DetectorThread`. Причина
архитектурная: каждый воркер-процесс обрабатывает кадры **без сохранения
состояния** между вызовами (никакого доступа к `TrackedSign` из другого
процесса быть не может по определению multiprocessing), поэтому:
- CNN-классификация вызывается на каждый кадр каждого знака, без пропуска
  для «стабильных» знаков (в отличие от `detect_with_tracking`);
- OCR вызывается синхронно на каждом кадре с текстовым знаком, без
  троттлинга через `TrackedSign.should_run_ocr()`.

Это не «баг», а архитектурное ограничение — Process Pool в текущем виде
всегда будет делать больше вычислений на знак, чем `pipeline`/`single_thread`.
Если хочешь исправить — нужно либо (а) отправлять воркеру не просто сырой
кадр, а также «слепок» уже накопленной по этому знаку статистики (сложно,
требует сериализации состояния трекинга через границу процессов на каждый
кадр — вероятно того не стоит), либо (б) честно задокументировать в
tooltip'е `_processing_mode_combo` (`settings_page.py`), что Process Pool не
получает этих оптимизаций и будет медленнее на CPU для видео с
повторяющимися знаками, только явно и с текущими деталями, а не общей фразой
"⚠️ Медленнее на CPU из-за overhead!" как сейчас.

### 5.2. GPU + Process Pool: N воркер-процессов на одну видеокарту

Каждый worker-процесс через `_worker_process_frame()` независимо резолвит
`_resolve_device()` и создаёт свой собственный CUDA-контекст, если
`use_cuda=True` и CUDA доступна. Несколько процессов, конкурирующих за одну
GPU, обычно не крашатся, но заметно теряют в производительности из-за
конкуренции за контекст/память по сравнению с одним процессом, использующим
батчинг. Это **не проверялось на реальном железе** ни в одном из
исторических отчётов этого репозитория (все тесты Process Pool были
CPU-only). Перед тем как объявлять Process Pool рабочим для GPU-пользователей —
явно протестируй этот сценарий (см. чек-лист Часть 6, строка "process_pool + GPU").

### 5.3. Двойное масштабирование QPixmap

`processing/preview_utils.py::build_pixmap_from_frame_dict()` масштабирует
кадр до `target_size=(960, 540)` по умолчанию, а затем
`ui/widgets/processing_page.py::ProcessingPage.set_frame()` масштабирует
**ещё раз** до `self.video_label.size()`:

```python
def set_frame(self, pixmap: QPixmap):
    self.video_label.setPixmap(
        pixmap.scaled(
            self.video_label.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
    )
```

Не баг (картинка не ломается), но лишняя работа на каждый кадр. Опционально:
либо не масштабировать в `build_pixmap_from_frame_dict()` вовсе (оставить
масштабирование только на стороне `set_frame`), либо передавать туда реальный
размер `video_label` вместо жёстко забитого `(960, 540)`. Низкий приоритет.

### 5.4. `preview_fps_limit`, `ocr_throttle_interval_frames`, `ocr_max_calls_per_sign` не выведены в UI

Поля есть в `AppSettings`, используются в коде (`DetectorThread`,
`ResultAggregatorThread`, `TrackedSign`), но в `settings_page.py` нет для них
контролов — их можно поменять только через ручную правку `QSettings` или
экспорт/импорт JSON. Не баг, но раз уж правишь `settings_page.py` в рамках
Части 3 — добавь заодно `QDoubleSpinBox` для `preview_fps_limit` (диапазон
1–60, дефолт 12) в группу «Многопоточность» рядом с остальными
многопоточность-настройками. Низкий приоритет, опционально.

---

## 6. Чек-лист ручной проверки — все 6 комбинаций (3 режима × CPU/GPU)

`single_thread` и `pipeline` архитектурно не содержат найденных багов
предпросмотра (обе используют один и тот же корректный
`DetectorThread._emit_frame() → build_frame_dict() → ProcessingController.
_on_worker_frame_ready() → build_pixmap_from_frame_dict()` путь) — но их
всё равно нужно фактически прогнать, чтобы подтвердить это на практике, а не
только по чтению кода. Прогони короткое тестовое видео (2–5 минут) на каждой
из строк таблицы **после** применения фиксов из Частей 1–4:

| # | processing_mode | use_cuda | Ожидаемый результат |
|---|------------------|----------|----------------------|
| 1 | single_thread    | False (CPU) | Превью обновляется плавно с частотой ~`preview_fps_limit` (12 FPS по умолчанию), счётчики кадров/знаков растут, никаких исключений в `roadscan.log` |
| 2 | single_thread    | True (GPU, если физически доступна) | То же самое; FPS обработки выше, превью по-прежнему троттлится на `preview_fps_limit`, не быстрее |
| 3 | pipeline         | False (CPU) | То же, что и (1); дополнительно в логах видно `[OCR-Throttling]`/`OCR: N calls, M skipped` |
| 4 | pipeline         | True (GPU) | То же, что и (2) |
| 5 | process_pool     | False (CPU) | **До фикса Части 1**: превью не обновляется весь прогон, счётчики стоят на месте, всё «случается» разом в конце. **После фикса**: превью обновляется инкрементально почти как в (1)/(3), счётчики растут по ходу видео, а не разом в конце. Знаки в итоговом GeoJSON — на реальных координатах (не в Африке, см. Часть 2) |
| 6 | process_pool     | True (GPU) | То же, что и (5); дополнительно проверь потребление GPU-памяти при `N > 1` воркеров (см. 5.2) — не должно расти неограниченно/крашиться |

Для каждой строки зафиксируй в отчёте:
1. Реально ли обновляется `video_label` на странице "Обработка" в течение
   всего прогона (не только в начале/конце).
2. Растут ли счётчики "кадров обр." / "знаков найд." / FPS в мини-статистике
   плавно, а не скачком.
3. Нет ли `Traceback`/`Exception` в `roadscan.log`, связанных с `QPixmap`,
   `frame_ready`, `_build_detected_signs`, `ReorderBuffer`.
4. Координаты знаков в итоговом `.geojson` (открой в текстовом редакторе или
   на карте) — должны быть в разумном диапазоне (для Беларуси: `lat≈52-56,
   lon≈23-32`, а не `lat≈0-1`).
5. Штатное закрытие приложения (крестик) во время активной обработки не
   виснет и не крашится ни в одном из режимов.

---

## 7. План работы (по шагам)

1. Прочитай заново `processing/detector_process_pool.py`,
   `processing/processing_controller.py`, `configs/sign_models.py`,
   `configs/settings.py`, `ui/widgets/settings_page.py` целиком — сверь с
   цитатами кода в этом промпте, убедись, что код с момента его написания не
   изменился (если изменился — актуализируй диагностику Частей 1–4).
2. Примени фикс Части 1 (`ReorderBuffer` + `seq`), добавь и прогони
   `tests/test_reorder_buffer.py` — оба «регрессионных до фикса» теста
   должны падать на исходном коде и проходить после правки (проверь это
   явно, не поверхностно).
3. Примени фикс Части 2 (конвертация координат в `_build_detected_signs`),
   добавь и прогони тест на конвертацию координат.
4. Примени фиксы Части 3 (`process_pool_workers`, `frame_step_mode`).
5. Реши и примени один из двух вариантов Части 4 (реальный reload моделей
   при смене device, либо честный tooltip про необходимость перезапуска).
6. Прогони `python -m py_compile` на всех изменённых файлах.
7. Прогони чек-лист Части 6 на реальном коротком тестовом видео (минимум
   строки 1, 3, 5 — CPU-конфигурации; строки 2, 4, 6 — если физически
   доступна GPU на машине, где выполняется задача; если недоступна — явно
   пометь в отчёте «не проверено, нет GPU на машине агента», не выдумывай
   результат).
8. По желанию — реализуй пункты Части 5 (второстепенные, не блокирующие).
9. Обнови/создай `STATUS.md` (не пиши очередной отдельный «мы всё
   исправили»-файл — в репозитории их уже больше сотни, они не должны больше
   плодиться, см. Часть 8 ниже) с фактическими результатами по каждой строке
   таблицы Части 6, включая то, что осталось не проверенным.

---

## 8. Антипаттерны, которых нужно избегать (это уже происходило в этом
репозитории десятки раз — см. историю `.md`-файлов в корне)

1. **Не пиши новый `BUGFIX_*.md`/`HOTFIX_*.md` со статусом «✅ исправлено»,
   не прогнав тест/сценарий из Части 6 и не увидев его прохождение своими
   глазами.** В репозитории уже есть минимум 5 файлов, декларирующих
   «предпросмотр исправлен», написанных ДО реальной проверки на практике —
   не продолжай эту традицию. Обновляй `STATUS.md` **в существующем файле**,
   а не создавай новый.
2. **Не оборачивай `ReorderBuffer.add()`/`_build_detected_signs()` в
   `try/except: print(...)` вместо настоящего фикса.** Причина найдена
   точно (Части 1.1–1.4, 2.1) — почини причину, а не глуши симптом.
3. **Не удаляй `ReorderBuffer` целиком «раз он избыточен»** (см. 1.4) — да,
   реальный беспорядок уже устранён блокирующим `future.result()` в
   правильном FIFO-порядке, но буфер служит защитой на случай будущих
   изменений архитектуры (например, если кто-то однажды заменит блокирующий
   `.result()` на `concurrent.futures.as_completed()` ради скорости — тогда
   буфер снова станет обязательным). Минимальный фикс (переключить ключ на
   `seq`) безопаснее полного удаления.
4. **Не трогай `os.environ["OMP_NUM_THREADS"]`/`torch.set_num_threads(1)`**
   в рамках этой задачи — это отдельная, куда более рискованная область
   (исторический краш `0xC0000409`), не имеющая отношения к найденным здесь
   багам. Если считаешь, что она тоже требует внимания — это отдельная
   задача с собственным ≥20-минутным стресс-тестом, не смешивай её с этим
   промптом.
5. **Не меняй формат `.geojson`** (набор полей `properties`) в рамках фикса
   Части 2 — единственное, что меняется, это *значения* `latitude`/`longitude`
   внутри `DetectedSign` (внутренняя структура, не GeoJSON-выход напрямую),
   сама схема выходного файла не затрагивается.
6. **Используй `logging`, не `print()`**, для любых новых диагностических
   сообщений, которые добавишь при отладке (см. уже принятый в проекте
   паттерн `logger = logging.getLogger(__name__)` в `detector_process_pool.py`).

---

## 9. Критерии приёмки

- [ ] `tests/test_reorder_buffer.py` создан, все тесты проходят.
- [ ] Тест на конвертацию координат в `_build_detected_signs()` создан и
      проходит.
- [ ] В режиме `process_pool` + CPU: предпросмотр обновляется в течение
      всего прогона видео (не только в начале и в конце), проверено вручную
      на реальном тестовом видео.
- [ ] В режиме `process_pool`: координаты знаков в итоговом `.geojson`
      находятся в разумном географическом диапазоне, а не около экватора.
- [ ] Настройка «Количество воркеров» (`process_pool_workers`) реально
      влияет на число запускаемых процессов (проверить логом
      `[DetectorProcessPool] Создан пул из N процессов` — N должно совпадать
      с настройкой, если она > 0).
- [ ] Настройка «Шаг кадра» (`frame_step_mode`/`frame_step_manual`) реально
      влияет на `config.FRAME_STEP` при старте обработки (проверить
      логом/отладочным выводом).
- [ ] Переключение «Использовать CUDA» между прогонами в одной сессии
      приложения либо реально меняет device моделей (если выбран фикс из
      4.3), либо явно предупреждает пользователя о необходимости перезапуска
      (если выбран простой вариант) — не остаётся молча нерабочим, как
      сейчас.
- [ ] Все 6 строк чек-листа Части 6 прогнаны хотя бы для CPU-конфигураций
      (1, 3, 5); GPU-конфигурации (2, 4, 6) — прогнаны, если физически
      доступна GPU, иначе явно помечены как непроверенные.
- [ ] `single_thread` и `pipeline` режимы не регрессировали — предпросмотр и
      обработка в них работают так же, как до этой сессии правок.
- [ ] Нет новых `print()` в изменённых файлах — только `logging`.
- [ ] `STATUS.md` обновлён в репозитории с фактическими (не декларативными)
      результатами проверки, включая явный список того, что осталось
      непроверенным (например, GPU-сценарии, если GPU физически недоступна
      агенту).
