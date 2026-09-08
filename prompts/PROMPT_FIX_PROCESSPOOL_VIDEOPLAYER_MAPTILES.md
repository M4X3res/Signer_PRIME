# PROMPT: Process Pool bottleneck, видеоплеер на карте, настройка подложки карты

**Проект:** RoadScanner / Signer PRIME
**Дата составления:** 2026-09-04
**Статус:** Готово к исполнению агентом

---

## 0. Контекст и правила работы

Это промпт для AI-агента (Kiro/Claude Code и т.п.), который должен внести три независимых
исправления/фичи в проект. Работай по частям **строго последовательно** (Часть 1 → Часть 2 →
Часть 3), после каждой части — коммить отдельно и обновляй соответствующий раздел этого файла
пометкой `[x]` у выполненных пунктов чеклиста.

**Общие правила проекта (соблюдай неукоснительно):**
- Никаких `print()` в новом коде — только `logging.getLogger(__name__)`, см.
  `docs/LOGGING_MIGRATION_GUIDE.md`.
- Перед оптимизацией — измерение (профилирование), после — измерение ещё раз. Не декларируй
  успех без чисел. Смотри культуру проекта: `docs/PROFILING_RESULTS.md`,
  `docs/BATCHING_FAILURE_ANALYSIS.md`, `WHY_SINGLE_THREAD_FASTER.md` — там ровно такой подход:
  гипотеза → эксперимент → цифры → вывод.
  По итогам Части 1 создай новый файл `docs/PROCESS_POOL_SLOWDOWN_ANALYSIS.md` с результатами
  твоих замеров (по аналогии с уже существующими `docs/PROFILING_*.md`).
- Модели (`configs/sign_models.py`) грузятся ЛЕНИВО и только внутри QThread/воркер-процесса —
  не трогай эту архитектуру и не добавляй eager-loading в главном потоке (см.
  `tests/test_no_eager_model_loading.py` — эта регрессия жёстко протестирована).
- Windows — целевая платформа №1. Учитывай краш 0xC0000409 (`docs/CRASH_FIX_0xC0000409.md`) при
  любых изменениях, трогающих многопоточность/OpenMP/CUDA-контексты.
- Не удаляй существующие regression-тесты, по возможности добавляй новые в `tests/`.

---

## 1. Часть 1 — Process Pool медленнее Single Thread / Pipeline на ВСЕХ backend'ах

### 1.1 Симптом

Пользователь подтверждает: `process_pool` медленнее чем `single_thread`/`pipeline` не только на
CPU (это уже задокументировано и объяснено в `WHY_SINGLE_THREAD_FASTER.md` для CPU-only кейса),
но **и на GPU (CUDA)**, и на всех CPU-бэкендах инференса (PyTorch/ONNX/OpenVINO) одинаково. Это
значит, что проблема **не в скорости самого инференса**, а в архитектуре передачи данных между
процессами — то есть в оверхеде, который одинаков независимо от того, что быстро или медленно
считает модель.

### 1.2 Подтверждённые находки (прочитаны в коде, не гипотезы)

**Файл:** `processing/detector_process_pool.py`

**Находка A — двойная сериализация кадра через IPC (главная гипотеза, приоритет №1).**

Функция `_worker_process_frame()` (top-level функция для pickling, исполняется в воркер-процессе)
получает на вход `raw_frame_data` со полем `image_bytes` — сериализованный кадр (`.tobytes()`,
для 1920×1080×3 это ≈ 6 МБ). Это единственный раз, когда кадр *обязан* пересечь границу процессов
(нужен воркеру для инференса). Но в конце функции:

```python
return {
    'seq': raw_frame_data['seq'],
    'frame_idx': raw_frame_data['frame_idx'],
    'frame_number': raw_frame_data.get('frame_number', raw_frame_data['frame_idx']),
    'video_idx': raw_frame_data['video_idx'],
    'video_name': raw_frame_data['video_name'],
    'image_bytes': raw_frame_data['image_bytes'],   # ← ВОЗВРАЩАЕТ ТОТ ЖЕ КАДР ОБРАТНО!
    'image_shape': raw_frame_data['image_shape'],
    'detections': detections_serialized,
    'gps_data': raw_frame_data.get('gps_data'),
    'timestamp': time.time(),
}
```

Воркер возвращает те же самые `image_bytes` в главный процесс НЕИЗМЕНЁННЫМИ. Это означает, что
на каждый обработанный кадр IPC-канал (`ProcessPoolExecutor` + `mp.get_context('spawn')`)
сериализует/десериализует ~6 МБ **дважды**: один раз на пути `submit()` (главный → воркер), и
второй раз на пути `future.result()` (воркер → главный), итого ~12 МБ round-trip вместо
логичных ~6 МБ one-way. Каждый такой проход — это `pickle.dumps`/`pickle.loads` плюс копирование
через ОС-канал (pipe/socket в зависимости от платформы), что является чисто CPU-bound и
однопоточной операцией **в главном процессе** (десериализация `future.result()` происходит в
`ResultAggregatorThread.run()`, который у нас один на весь пул).

Единственная причина, по которой кадр вообще нужен обратно в главном процессе — отрисовка bbox
для UI-превью в `ResultAggregatorThread._emit_frame()` (`processing/detector_process_pool.py`,
метод `_process_result` → `_emit_frame`). Но исходный кадр УЖЕ есть в главном процессе — он был
прочитан `VideoReaderThread` и находится в `DetectorProcessPool._submit_loop()` (переменная
`raw: RawFrame`) непосредственно перед тем, как превратиться в `image_bytes` и уйти в
`executor.submit()`. После `.tobytes()` он просто выбрасывается — вместо того чтобы быть
сохранённым и переиспользованным.

**Это единственная находка, которая одинаково объясняет замедление на GPU и на CPU (любой
backend)** — потому что overhead чисто в объёме данных, гоняемых через IPC, а не в скорости
модели.

**Находка B — единственный последовательный `ResultAggregatorThread` как бутылочное горлышко.**

`SignHandler.check_the_data_to_add()` (см. `core/sign_handler.py`) обязан обрабатывать кадры
СТРОГО по порядку (трекинг знаков между кадрами, `ReorderBuffer` в
`processing/detector_process_pool.py` специально восстанавливает порядок по `seq` перед тем как
отдать кадры в `ResultAggregatorThread`). Значит, сколько бы воркеров детекции ни было запущено,
итоговый throughput пула ограничен скоростью ОДНОГО потока — аггрегатора, который вдобавок
(из-за находки A) тратит время на распаковку лишних 6 МБ на каждый кадр, рисование bbox
(`cv2.rectangle`/`cv2.putText`) и сборку структуры для UI.

**Находка C — `futures_q` создаёт backpressure, маскирующий выигрыш от параллелизма.**

```python
self._futures_q: queue.Queue = queue.Queue(maxsize=self._num_workers * 4)
```

Если аггрегатор не успевает разбирать `future.result()` (что вероятно из-за A и B), воркеры
блокируются на `self._futures_q.put(future)` внутри `_submit_loop()`. Пул полностью деградирует
до скорости аггрегатора вне зависимости от `num_workers` и вне зависимости от backend'а
инференса.

**Находка D — на GPU: N процессов = N независимых CUDA-контекстов на одной видеокарте
(гипотеза, требует профилирования на реальной GPU-машине).**

В проекте нигде не настроен NVIDIA MPS (Multi-Process Service). Без MPS параллельные CUDA-
контексты от РАЗНЫХ ОС-процессов на одной GPU по умолчанию сериализуются драйвером
(time-slicing) — то есть реального параллелизма вычислений на GPU не получается, а сама
многопроцессность добавляет постоянный context-switch overhead. Плюс каждый воркер-процесс
независимо грузит ПОЛНУЮ копию всех моделей (`Detector()` → `configs/sign_models.py`:
`model_side_detect`, `rube_modal`, ~11 моделей `model_dict`, `sub_models`, lane-модели) в свой
собственный VRAM — то есть VRAM расходуется кратно `num_workers`, при том что реального
параллелизма вычислений может не быть вообще.

**Находка E — `spawn`-старт процессов на Windows.**

Каждый воркер — отдельный интерпретатор Python (`mp.get_context('spawn')`, обязательно для
Windows/PyQt), который заново импортирует `torch`/`ultralytics`/`onnxruntime`/`openvino` и грузит
ВСЕ модели с нуля. Согласно `WHY_SINGLE_THREAD_FASTER.md`, это 40–60 секунд на воркер. Это не
влияет на устойчивый FPS в середине обработки, но объясняет долгий "разгон" и должно быть
задокументировано отдельно от находок A–D (не путать причины холодного старта с причинами
низкого установившегося FPS).

### 1.3 Что нужно сделать

**Шаг 1 — подтвердить находку A измерением (обязательно ПЕРЕД правкой кода).**

Добавь временную инструментацию через существующий `core/profiler.py` (`profiler.measure(...)`)
в трёх точках:
1. `_worker_process_frame()` — вокруг `pickle`-неявной сериализации входа/выхода нельзя измерить
   напрямую изнутри функции, поэтому измерь **размер** `raw_frame_data['image_bytes']` и время
   выполнения `detector.detect(image)` отдельно от времени всей функции — разница покажет
   оверхед на сборку/копирование.
2. В `ResultAggregatorThread.run()` — обверни `future.result(timeout=10.0)` в
   `profiler.measure("future_result_unpickle")` — это покажет реальное время, потраченное на
   десериализацию (включая злополучные `image_bytes`).
3. В `ResultAggregatorThread._process_result()` — обверни `np.frombuffer(...).reshape(...)` и
   `_emit_frame()` отдельно.

Прогони `scripts/benchmark_end_to_end_cpu.py --mode process_pool` (расширь его при необходимости
поддержкой GPU-прогона — сейчас скрипт называется `..._cpu.py` и принудительно ставит
`settings.use_cuda = False`; сделай флаг `--mode-suffix` или отдельный
`scripts/benchmark_end_to_end_gpu.py`, который НЕ трогает `use_cuda`).

Запиши результаты в `docs/PROCESS_POOL_SLOWDOWN_ANALYSIS.md`: сколько % времени кадра уходит на
`future_result_unpickle` против `detector.detect()`. Если `future_result_unpickle` доминирует —
находка A подтверждена, переходи к шагу 2. Если нет — не трогай архитектуру IPC, ищи причину
в другом месте (обнови этот файл новыми находками).

**Шаг 2 — устранить двойную сериализацию кадра (реализация находки A).**

Идея: воркер должен возвращать ТОЛЬКО детекции (маленький JSON-сериализуемый список), а не
исходный кадр. Главный процесс должен помнить кадр сам, по ключу `seq`.

Изменения в `DetectorProcessPool` (`processing/detector_process_pool.py`):

```python
class DetectorProcessPool(QObject):
    def __init__(self, frame_queue, parent=None):
        ...
        self._pending_frames: dict[int, RawFrame] = {}   # NEW: seq -> RawFrame (с image)
        self._pending_frames_lock = threading.Lock()      # NEW
```

В `_submit_loop()`, непосредственно перед `executor.submit(...)`, сохраняй кадр:

```python
seq = self._submit_seq
with self._pending_frames_lock:
    self._pending_frames[seq] = raw   # raw.image остаётся в главном процессе

frame_data = {
    'seq': seq,
    'frame_idx': raw.abs_frame_number,
    'frame_number': raw.frame_number,
    'video_idx': raw.video_index,
    'video_name': raw.video_name,
    'image_bytes': raw.image.tobytes(),   # уходит воркеру — это нормально, нужно для детекции
    'image_shape': raw.image.shape,
    'gps_data': {'gps_index': raw.gps_index},
}
self._submit_seq += 1
```

В `_worker_process_frame()` — убери `image_bytes`/`image_shape` из возвращаемого словаря
ПОЛНОСТЬЮ:

```python
return {
    'seq': raw_frame_data['seq'],
    'frame_idx': raw_frame_data['frame_idx'],
    'frame_number': raw_frame_data.get('frame_number', raw_frame_data['frame_idx']),
    'video_idx': raw_frame_data['video_idx'],
    'video_name': raw_frame_data['video_name'],
    'detections': detections_serialized,
    'gps_data': raw_frame_data.get('gps_data'),
    'timestamp': time.time(),
}
```

В `ResultAggregatorThread._process_result()` и `_build_detected_signs()` замени восстановление
кадра из `frame_data['image_bytes']` на выборку из `self._pending_frames` по `frame_data['seq']`
(передай ссылку на словарь `_pending_frames` из `DetectorProcessPool` в конструктор
`ResultAggregatorThread` — сейчас туда уже передаются `sign_handler`, `gpx_handler`, `skipper`,
добавь пятый параметр `pending_frames`). После использования кадра — **обязательно удаляй его**
из `self._pending_frames.pop(frame_data['seq'], None)`, иначе будет утечка памяти (кадры
накапливаются, если аггрегатор отстаёт).

**ВАЖНО (thread-safety):** `_pending_frames` пишется из `_submit_loop()` (отдельный QThread) и
читается/чистится из `ResultAggregatorThread` (другой QThread) — используй `threading.Lock()`
вокруг каждого доступа, либо, что чище, `queue.Queue`-подобную структуру. Не полагайся на GIL
без явной синхронизации, т.к. операции `dict[key] = value` и `dict.pop(key)` не атомарны в
композиции с проверками.

**Защита от утечки при gap/skip в `ReorderBuffer`:** если кадр был пропущен gap-safety-valve'ом
(`ReorderBuffer.add()`, ветка `gap > max_gap`), соответствующий `seq` никогда не придёт в
`_process_result()` — значит, запись в `_pending_frames` для него никогда не будет вычищена.
Добавь периодическую чистку "протухших" записей (например, раз в 5 секунд удаляй все `seq`
старше `self._reorder_buffer._next_expected - REORDER_BUFFER_MAX_GAP * 2`).

**Шаг 3 — повторно измерить после Шага 2.**

Прогони те же бенчмарки, что и в Шаге 1, зафиксируй разницу FPS/памяти ДО/ПОСЛЕ в
`docs/PROCESS_POOL_SLOWDOWN_ANALYSIS.md`. Обнови таблицу сравнения `single_thread` vs
`process_pool` (аналогично таблицам в `WHY_SINGLE_THREAD_FASTER.md`) для всех 4 конфигураций:
CPU+PyTorch, CPU+ONNX, CPU+OpenVINO, GPU+CUDA.

**Шаг 4 — GPU-специфичное решение (находка D).**

Если после Шага 2 `process_pool` на GPU всё ещё медленнее `single_thread`/`pipeline` — это
подтверждает находку D (контентион CUDA-контекстов). В этом случае:

1. В UI (`ui/widgets/settings_page.py`, комбобокс `_processing_mode_combo`) добавь предупреждение
   (`setToolTip` уже частично это делает для CPU — расширь текст, чтобы явно упомянуть GPU):
   *"Process Pool на GPU без NVIDIA MPS не даёт параллелизма вычислений — несколько процессов
   разделяют один GPU через time-slicing драйвера. Рекомендуется 'Один поток' и для GPU тоже,
   если у вас одна видеокарта."*
2. Не отключай режим программно (пользователь может знать что делает, например, есть несколько
   GPU через `CUDA_VISIBLE_DEVICES` на воркер) — но задокументируй ограничение в
   `docs/PROCESS_POOL_SLOWDOWN_ANALYSIS.md` и в `WHY_SINGLE_THREAD_FASTER.md` (добавь раздел
   "GPU" рядом с существующим CPU-анализом).
3. Опционально (если останется время): добавь в `configs/settings.py` поле
   `process_pool_cuda_device_map: str = ""` — позволяющее указать, например,
   `"0,1,0,1"` (по одному device index на воркер по кругу), и применяй его в
   `_worker_process_frame()` через `os.environ["CUDA_VISIBLE_DEVICES"] = ...` ДО импорта torch
   в воркере, для мультиGPU-систем. Это отдельная фича, не блокирует основную часть.

### 1.4 Чеклист приёмки Части 1

- [ ] Добавлена инструментация профилирования в `_worker_process_frame`,
      `ResultAggregatorThread.run()`, `_process_result()`
- [ ] Прогнан бенчмарк ДО правки, зафиксированы числа в `docs/PROCESS_POOL_SLOWDOWN_ANALYSIS.md`
- [ ] Убрано дублирование `image_bytes` в возврате воркера
- [ ] `DetectorProcessPool` хранит `_pending_frames: dict[seq, RawFrame]` с блокировкой
- [ ] `ResultAggregatorThread` берёт кадр из `_pending_frames` вместо распаковки из
      `future.result()`, и чистит запись после использования
- [ ] Добавлена периодическая чистка "протухших" записей `_pending_frames` (защита от утечки
      при gap-skip в ReorderBuffer)
- [ ] Прогнан бенчмарк ПОСЛЕ правки на всех 4 конфигурациях (CPU×3 backend + GPU), числа внесены
      в тот же файл
- [ ] Обновлён `WHY_SINGLE_THREAD_FASTER.md` — добавлен раздел про GPU-контентион и про фикс
      двойной сериализации
- [ ] Обновлены tooltip'ы в `settings_page.py` (текст про GPU без MPS)
- [ ] Ни один существующий тест в `tests/` не сломан (`tests/test_reorder_buffer.py` особенно
      важен — там тестируется именно этот путь данных)
- [ ] Новый unit-тест: `_pending_frames` корректно чистится и не растёт бесконечно при
      искусственном gap (расширь `tests/test_reorder_buffer.py` или создай
      `tests/test_pending_frames_cleanup.py`)

---

## 2. Часть 2 — Видеоплеер на карте не работает (timeout при загрузке)

### 2.1 Симптом (со скриншотов пользователя)

1. Диагностика (`testVideoCodec()`) показывает: видео 3815 МБ, H.264 High + AAC LC, но
   "Поддержка браузером: H.264+AAC: нет" — противоречиво, т.к. H.264+AAC поддерживается всеми
   современными браузерами.
2. При попытке реально проиграть видео на карте: **"Ошибка загрузки видео: Video loading
   timeout (10s)"** — `loadedmetadata` никогда не срабатывает.

### 2.2 Подтверждённая находка — баг в парсинге HTTP Range-заголовка (главная причина)

**Файл:** `server/map_server.py`, функция `api_video()`.

```python
range_header = request.headers.get('Range')

if range_header:
    byte_range = range_header.replace('bytes=', '').split('-')
    start = int(byte_range[0]) if byte_range[0] else 0     # ← БАГ ЗДЕСЬ
    end = int(byte_range[1]) if len(byte_range) > 1 and byte_range[1] else file_size - 1
```

HTTP-спецификация (RFC 7233 §2.1) определяет **suffix-byte-range-spec**: заголовок вида
`Range: bytes=-N` означает *"последние N байт файла"*, а НЕ "с начала файла". У такого
заголовка `byte_range[0]` — пустая строка (т.к. до дефиса ничего нет). Текущий код трактует
пустой `byte_range[0]` как `start = 0` — то есть отдаёт **первые** N байт вместо **последних**.

Это критично именно для видео с сервисов вроде GoPro: если файл не был обработан с
`-movflags +faststart`, атом `moov` (метаданные — длительность, индекс кадров, кодеки) находится
**в конце файла**, а не в начале. Браузер, получив первый ответ (обычно `Range: bytes=0-`,
которое сервер и так обрезает до 10 МБ — см. находку ниже), понимает, что `moov` не найден в
начале, и посылает запрос вида `Range: bytes=-65536` (или похожий) чтобы прочитать хвост файла.
Сервер, из-за бага, возвращает ПЕРВЫЕ 65536 байт вместо последних — браузер получает не тот
кусок, не может найти `moov`, зависает в ожидании `loadedmetadata`, которое никогда не сработает
→ ровно то, что видно на скриншоте ("Video loading timeout (10s)").

### 2.3 Дополнительная находка — искусственное урезание каждого Range-ответа до 10 МБ

```python
chunk_size = min(end - start + 1, 10 * 1024 * 1024)
end = start + chunk_size - 1
```

Даже при корректном парсинге диапазона, сервер всегда возвращает не больше 10 МБ за раз,
независимо от того, что реально запросил браузер. Для файла почти 4 ГБ без `faststart` браузеру
может понадобиться сделать несколько last-chunk запросов подряд, что добавляет round-trip'ы, но
само по себе не является фатальным — фатальна именно находка 2.2. Тем не менее стоит поднять
лимит (например, до 50 МБ) или убрать искусственное ограничение вовсе, оставив только
разумный кэп на случай запроса всего файла целиком без Range.

### 2.4 Дополнительная находка — потенциально дублирующийся `Content-Length` в fallback-ветке

```python
else:
    response = send_file(video_path, mimetype=mimetype, as_attachment=False)
    response.headers.add('Accept-Ranges', 'bytes')
    response.headers.add('Content-Length', str(file_size))   # ← .add(), не .set()!
```

`flask.send_file()` в актуальных версиях Flask/Werkzeug по умолчанию (`conditional=True`) уже
устанавливает заголовки `Content-Length` и `Accept-Ranges` сам. Вызов `.headers.add(...)`
(**добавляет**, а не заменяет) может привести к ДВУМ заголовкам `Content-Length` в ответе —
это невалидный HTTP-ответ, который часть браузеров отклоняет целиком (может проявляться как
зависание/timeout или сетевая ошибка). Нужно проверить реальный ответ сервера (`curl -I` или
DevTools → Network → заголовки ответа) и заменить `.add()` на `.set()` для этих двух заголовков,
либо явно передать `conditional=False` в `send_file()` и полностью управлять заголовками вручную.

### 2.5 Дополнительная находка (менее критичная) — неверная диагностика в `testVideoCodec()`

**Файл:** `templates/map.html`, функция `testVideoCodec()`:

```javascript
const canPlayMP4 = video.canPlayType('video/mp4; codecs="avc1.42E01E, mp4a.40.2"');
```

`avc1.42E01E` — это codec-строка для профиля **Baseline**, уровень 3.0. Реальное видео (по
ffprobe в диагностике) — профиль **High**. Codec-строка для High-профиля выглядит иначе (обычно
что-то вроде `avc1.6400XX`, где `XX` — уровень). Из-за несовпадения `canPlayType()` закономерно
возвращает `""` (не поддерживается) — но это ложноотрицательный результат самой диагностической
функции, а НЕ показатель того, что реальное видео не проигрывается. Это вводит в заблуждение при
отладке (пользователь видит "H.264+AAC: нет" и тратит время, думая что дело в кодеке, хотя
реальная причина — баг Range-заголовка из 2.2).

### 2.6 Что нужно сделать

**Шаг 1 — исправить парсинг Range-заголовка (`server/map_server.py::api_video()`).**

Замени текущий блок парсинга на корректную обработку всех трёх форм Range согласно RFC 7233:
`bytes=start-end`, `bytes=start-` (открытый конец), `bytes=-suffix_length` (суффикс с конца).

```python
range_header = request.headers.get('Range')

if range_header:
    range_spec = range_header.replace('bytes=', '').strip()
    if '-' not in range_spec:
        return jsonify({"error": "Malformed Range header"}), 416

    range_start_str, range_end_str = range_spec.split('-', 1)

    if range_start_str == '':
        # Suffix range: "bytes=-500" = последние 500 байт файла
        if range_end_str == '':
            return jsonify({"error": "Malformed Range header"}), 416
        suffix_length = int(range_end_str)
        start = max(0, file_size - suffix_length)
        end = file_size - 1
    else:
        start = int(range_start_str)
        end = int(range_end_str) if range_end_str != '' else file_size - 1

    # Валидация границ (RFC 7233: невалидный диапазон -> 416)
    if start >= file_size or start > end:
        response = Response(status=416)
        response.headers.add('Content-Range', f'bytes */{file_size}')
        return response
    end = min(end, file_size - 1)

    # Поднимаем лимит на чанк (было 10MB — многовато round-trip'ов для 4ГБ файлов без faststart)
    MAX_CHUNK = 50 * 1024 * 1024
    if end - start + 1 > MAX_CHUNK:
        end = start + MAX_CHUNK - 1

    logger.info(f"[API /api/video/{video_idx}] Range request: {start}-{end}/{file_size}")

    def generate():
        with open(video_path, 'rb') as f:
            f.seek(start)
            remaining = end - start + 1
            while remaining > 0:
                chunk = f.read(min(8192, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    response = Response(generate(), 206, mimetype=mimetype)
    response.headers.set('Content-Range', f'bytes {start}-{end}/{file_size}')
    response.headers.set('Accept-Ranges', 'bytes')
    response.headers.set('Content-Length', str(end - start + 1))
    response.headers.set('Access-Control-Allow-Origin', '*')
    response.headers.set('Access-Control-Expose-Headers', 'Content-Range, Content-Length, Accept-Ranges')
    return response
```

Обрати внимание: используй `.set(...)`, а не `.add(...)`, везде в этой функции, чтобы исключить
дублирование заголовков при повторных вызовах/редиректах.

**Шаг 2 — исправить fallback-ветку (без Range) на `.set()` вместо `.add()`.**

```python
else:
    logger.info(f"[API /api/video/{video_idx}] Полная отдача файла: {file_size} bytes")
    response = send_file(video_path, mimetype=mimetype, as_attachment=False, conditional=False)
    response.headers.set('Accept-Ranges', 'bytes')
    response.headers.set('Content-Length', str(file_size))
    response.headers.set('Cache-Control', 'public, max-age=3600')
    response.headers.set('Access-Control-Allow-Origin', '*')
    response.headers.set('Access-Control-Expose-Headers', 'Content-Range, Content-Length, Accept-Ranges')
    return response
```

`conditional=False` отключает встроенную Range-логику Flask в этой ветке (у нас Range-заголовка
здесь всё равно нет по определению — попадаем в `else`), чтобы точно не было конфликта с ручным
выставлением заголовков.

**Шаг 3 — исправить codec-строку в диагностике (`templates/map.html`, `testVideoCodec()`).**

Не пытайся угадывать codec-строку по профилю — вместо жёстко зашитого `avc1.42E01E` используй
универсальную проверку `canPlayType('video/mp4')` (без конкретных codecs, уже есть как
`canPlayMP4Basic`) как основной индикатор, а детальную codec-строку показывай только
информационно, явно подписав в выводе: *"codec-строка ниже основана на предположении и может не
совпадать с реальным профилем видео — ориентируйтесь на 'video/mp4' проверку выше"*.

**Шаг 4 — проверить, требуется ли поддержка `moov` в начале файла на уровне рекомендаций.**

Добавь в `docs/` (например, дополни `docs/SOLUTION_GOPRO_MSMF.md` или создай
`docs/VIDEO_PLAYER_STREAMING_FIX.md`) рекомендацию для пользователей: если видео "тормозит" при
первой загрузке метаданных даже после фикса, можно ускорить это, предварительно перепаковав файл
командой:
```
ffmpeg -i input.mp4 -c copy -movflags +faststart output.mp4
```
Это не обязательное исправление кода, а операционная рекомендация — Range-фикс должен работать
и без неё, но с `faststart` первая загрузка метаданных будет намного быстрее (не нужно скакать в
конец файла).

**Шаг 5 — ручное тестирование (обязательно, в реальном браузере, не просто curl).**

1. Открой карту, выбери знак с видео объёмом в несколько ГБ (как на скриншотах).
2. В DevTools → Network найди запросы к `/api/video/<idx>`, убедись что:
   - Ответы имеют статус `206 Partial Content`.
   - **Только один** заголовок `Content-Range` и **только один** `Content-Length` в каждом
     ответе (проверить вкладку Headers, не Response Headers "raw", там дубли иногда схлопываются
     визуально — используй `curl -v` для 100% уверенности).
   - При suffix-range запросе (`bytes=-N`, встречается в логах при поиске `moov`) диапазон
     `Content-Range: bytes X-Y/Z` соответствует **концу** файла (X близко к Z), а не началу.
3. Убедись, что `loadedmetadata` срабатывает и видео реально начинает проигрываться, `duration`
   отображается корректно (не `NaN`).
4. Проверь перемотку (`video.currentTime = seconds`) — должна работать без повторного зависания.

### 2.7 Чеклист приёмки Части 2

- [ ] Корректно парсится `bytes=start-end`, `bytes=start-`, `bytes=-suffix`
- [ ] Невалидные/выходящие за границы Range → `416 Range Not Satisfiable` с корректным
      `Content-Range: bytes */filesize`
- [ ] Везде `.set()` вместо `.add()` для заголовков в `api_video()`
- [ ] `conditional=False` в fallback-ветке `send_file()`
- [ ] `testVideoCodec()` не вводит в заблуждение (основной вывод — `video/mp4` без строгих codecs)
- [ ] Ручной тест в браузере: видео с 3+ ГБ файла загружается и проигрывается без timeout
- [ ] Ручной тест: `curl -v -H "Range: bytes=-1024" http://127.0.0.1:3000/api/video/0` возвращает
      именно последние 1024 байта файла (можно сверить побайтово через `tail -c 1024 file.mp4`)
- [ ] Добавлена заметка в docs про `+faststart` как опциональную оптимизацию

---

## 3. Часть 3 — Настройка подложки карты (tile layer) в UI

### 3.1 Текущее состояние

`templates/map.html`, функция `initMap()`:

```javascript
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 19,
}).addTo(map);
```

URL тайлового сервера и атрибуция захардкожены. Нужно вынести в настройки приложения, чтобы
пользователь мог указать другой тайловый провайдер (например, самостоятельно поднятый tile-сервер,
Carto, Stamen, или платный провайдер с ключом API).

### 3.2 Что нужно сделать

**Шаг 1 — добавить поля в `configs/settings.py` (`AppSettings`).**

```python
# ── Карта (подложка) ───────────────────────────────────────────
map_tile_url: str = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
map_tile_attribution: str = "© OpenStreetMap"
map_tile_max_zoom: int = 19
```

Добавь эти поля в блок `@dataclass class AppSettings` рядом с остальными UI-настройками (после
`theme`). Убедись, что `load()`/`save()`/`reset_to_defaults()`/`to_dict()`/`from_dict()` работают
с ними автоматически — они уже реализованы через `__dataclass_fields__`/`asdict()`, никаких
дополнительных правок в этих методах не требуется, если поля объявлены как обычные `str`/`int`.

**Шаг 2 — добавить UI-контролы в `ui/widgets/settings_page.py`.**

В группу `ui_group` ("Интерфейс"), сразу после строки с выбором темы, добавь:

```python
from PyQt6.QtWidgets import QLineEdit  # добавить в импорты, если ещё нет

self._map_tile_url_input = QLineEdit()
self._map_tile_url_input.setText(self._settings.map_tile_url)
self._map_tile_url_input.setPlaceholderText("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
self._map_tile_url_input.setMinimumWidth(280)
self._map_tile_url_input.setToolTip(
    "URL-шаблон тайлового сервера карты (формат Leaflet/XYZ).\n"
    "Плейсхолдеры {s}, {z}, {x}, {y} подставляются автоматически.\n\n"
    "Примеры:\n"
    "  OpenStreetMap: https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png\n"
    "  CartoDB Light: https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png\n"
    "  Свой сервер:   http://localhost:8080/tiles/{z}/{x}/{y}.png\n\n"
    "⚠️ Изменения применяются после перезагрузки карты (кнопка «Перезагрузить» на вкладке Карта)."
)
ui_group.add_row(
    "URL подложки карты",
    "Тайловый сервер для отображения карты (формат Leaflet XYZ)",
    self._map_tile_url_input,
)

self._map_attribution_input = QLineEdit()
self._map_attribution_input.setText(self._settings.map_tile_attribution)
self._map_attribution_input.setMinimumWidth(280)
ui_group.add_row(
    "Атрибуция подложки",
    "Текст копирайта, отображаемый в углу карты",
    self._map_attribution_input,
)

self._map_max_zoom_spin = QSpinBox()
self._map_max_zoom_spin.setRange(1, 22)
self._map_max_zoom_spin.setValue(self._settings.map_tile_max_zoom)
self._map_max_zoom_spin.setFixedWidth(90)
ui_group.add_row(
    "Максимальный zoom подложки",
    "Ограничение приближения для выбранного тайлового сервера",
    self._map_max_zoom_spin,
)

reset_tiles_btn = QPushButton("↻  Сбросить подложку на OSM")
reset_tiles_btn.setObjectName("BtnSecondary")
reset_tiles_btn.setMinimumHeight(32)
reset_tiles_btn.setCursor(Qt.CursorShape.PointingHandCursor)
reset_tiles_btn.clicked.connect(self._reset_map_tiles)
ui_group.add_row(
    "Подложка по умолчанию",
    "Вернуть OpenStreetMap как источник тайлов",
    reset_tiles_btn,
)
```

Добавь метод `_reset_map_tiles`:

```python
def _reset_map_tiles(self):
    from configs.settings import AppSettings
    defaults = AppSettings()
    self._map_tile_url_input.setText(defaults.map_tile_url)
    self._map_attribution_input.setText(defaults.map_tile_attribution)
    self._map_max_zoom_spin.setValue(defaults.map_tile_max_zoom)
```

В `_collect_settings()` добавь сохранение новых полей:

```python
if hasattr(self, '_map_tile_url_input'):
    url = self._map_tile_url_input.text().strip()
    self._settings.map_tile_url = url if url else AppSettings().map_tile_url
if hasattr(self, '_map_attribution_input'):
    self._settings.map_tile_attribution = self._map_attribution_input.text().strip()
if hasattr(self, '_map_max_zoom_spin'):
    self._settings.map_tile_max_zoom = self._map_max_zoom_spin.value()
```
(обрати внимание: если пользователь очистит поле URL полностью, откатывайся на дефолт, а не
сохраняй пустую строку — иначе Leaflet сломается при следующей загрузке карты).

В `_reset()` (сброс всей страницы настроек к дефолтам) добавь аналогичный блок для этих трёх
полей — по образцу остальных `if hasattr(self, ...)` блоков в этом методе.

**Шаг 3 — отдать конфигурацию через API (`server/map_server.py`).**

Добавь новый endpoint:

```python
@app.route("/api/map_config")
def api_map_config():
    """Конфигурация подложки карты (тайловый сервер, атрибуция, zoom)."""
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        return jsonify({
            "tile_url": settings.map_tile_url,
            "attribution": settings.map_tile_attribution,
            "max_zoom": settings.map_tile_max_zoom,
        })
    except Exception as e:
        logger.error(f"ERROR in /api/map_config: {e}")
        # Безопасный fallback на OSM, чтобы карта не осталась совсем без подложки
        return jsonify({
            "tile_url": "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
            "attribution": "© OpenStreetMap",
            "max_zoom": 19,
        })
```

**Шаг 4 — использовать конфигурацию в `templates/map.html`.**

Замени синхронный вызов `L.tileLayer(...)` внутри `initMap()` на асинхронную загрузку конфига
ДО инициализации тайлового слоя. Раздели `initMap()` на синхронную часть (создание `map`,
`markerCluster`, `posMarker`) и асинхронную загрузку тайлов:

```javascript
function initMap() {
  map = L.map("map", { zoomControl: true, attributionControl: true });

  // Подложка загружается асинхронно — с fallback на OSM при любой ошибке
  loadTileLayer();

  markerCluster = L.markerClusterGroup({ /* ...без изменений... */ });
  map.addLayer(markerCluster);

  posMarker = L.marker([0, 0], { /* ...без изменений... */ });
  posMarker.addTo(map);
}

async function loadTileLayer() {
  const DEFAULT_TILE_URL = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
  const DEFAULT_ATTRIBUTION = "© OpenStreetMap";
  const DEFAULT_MAX_ZOOM = 19;

  let tileUrl = DEFAULT_TILE_URL;
  let attribution = DEFAULT_ATTRIBUTION;
  let maxZoom = DEFAULT_MAX_ZOOM;

  try {
    const r = await fetch(`${API}/map_config`);
    if (r.ok) {
      const cfg = await r.json();
      if (cfg.tile_url) tileUrl = cfg.tile_url;
      if (cfg.attribution) attribution = cfg.attribution;
      if (cfg.max_zoom) maxZoom = cfg.max_zoom;
    }
  } catch (err) {
    console.warn("[loadTileLayer] Не удалось загрузить конфиг подложки, используем OSM:", err);
  }

  L.tileLayer(tileUrl, { attribution, maxZoom }).addTo(map);
}
```

Обрати внимание: `API` — уже существующая глобальная константа в `map.html`
(`const API = ...`), определена выше по файлу, переиспользуй её.

**Шаг 5 — проверить взаимодействие с существующим CSS-фильтром тёмной темы.**

В `templates/map.html` есть CSS-правило:

```css
.leaflet-tile {
    filter: brightness(0.55) contrast(1.1) saturate(0.7) hue-rotate(180deg) invert(1);
}
```

Это инвертирует цвета ЛЮБОЙ подложки для имитации тёмной темы — работает нормально для
классических OSM-тайлов, но для некоторых альтернативных провайдеров (уже тёмные темы типа
CartoDB Dark, или спутниковые снимки) двойная инверсия даст странный результат. Это не баг, а
особенность — просто задокументируй это ограничение в tooltip поля URL (уже сделано в шаге 2,
но добавь явную фразу): *"Если подложка выглядит некорректно с этим URL, попробуйте светлую тему
приложения — CSS-фильтр тёмной темы инвертирует цвета тайлов и может конфликтовать с уже тёмными
подложками."*

### 3.3 Чеклист приёмки Части 3

- [ ] `AppSettings` содержит `map_tile_url`, `map_tile_attribution`, `map_tile_max_zoom` с
      дефолтами = текущий хардкод (OSM)
- [ ] UI в `SettingsPage` позволяет менять и сохранять эти три поля, включая кнопку сброса
- [ ] Пустой URL при сохранении не даёт сломать карту (fallback на дефолт)
- [ ] `/api/map_config` отдаёт корректный JSON и не падает даже при отсутствии настроек
      (fallback внутри `except`)
- [ ] `map.html::loadTileLayer()` асинхронно тянет конфиг и не блокирует остальную
      инициализацию карты (маркеры/трек должны продолжать грузиться параллельно, не дожидаясь
      тайлов)
- [ ] При недоступности `/api/map_config` карта всё равно показывает OSM (не остаётся без
      подложки вообще)
- [ ] Ручной тест: меняем URL на `https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}.png`,
      сохраняем, перезагружаем карту кнопкой «Перезагрузить» — подложка визуально меняется
- [ ] Ручной тест: кнопка «Сбросить подложку на OSM» возвращает дефолтные значения в полях (до
      сохранения — просто в UI)

---

## 4. Порядок сдачи работы

1. Часть 1, 2, 3 — три отдельных коммита (или три отдельных PR, если используется такой процесс).
2. Каждая часть обязательно сопровождается обновлением документации в `docs/` с реальными
   цифрами замеров (для Части 1) и результатами ручного тестирования (для Частей 2 и 3) —
   без цифр/скриншотов результат не считается принятым, по аналогии с тем, как в этом репозитории
   уже оформлены `docs/PROFILING_RESULTS.md`, `docs/CACHE_FIX.md`, `WHY_SINGLE_THREAD_FASTER.md`.
3. Финальное summary-сообщение должно явно ответить на исходный вопрос пользователя:
   *"Почему Process Pool был медленнее и что изменилось"* — с конкретными числами до/после.
