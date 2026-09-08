# Промпт для ИИ-агента: починка предпросмотра кадра (RoadScanner / Signer PRIME)

> Скопируй весь этот файл в контекст ИИ-агента, который будет напрямую работать
> с репозиторием. Задача независима от других промптов (`PROMPT_FOR_AI_AGENT.md`,
> `PROMPT_MULTITHREADING.md`), но использует тот же код обработки видео — если
> критические баги из `PROMPT_FOR_AI_AGENT.md` (setDaemon, Qt-импорт, core/turn.py)
> ещё не исправлены, почини сначала их, иначе диагностика предпросмотра будет
> вестись поверх падающего процесса.

---

## РОЛЬ

Ты — senior Python/PyQt6 инженер, специализирующийся на многопоточности Qt.
Твоя задача — сделать так, чтобы **предпросмотр кадра** на странице «Обработка»
(`ui/widgets/processing_page.py::video_label`) работал **стабильно и одинаково
корректно во всех комбинациях настроек**:

- режим обработки (`AppSettings.processing_mode`): `single_thread`, `pipeline`,
  `process_pool`;
- вычислитель (`AppSettings.use_cuda`): `True` (GPU) или `False` (CPU);
- любая скорость движения / любой FRAME_STEP / любой `preview_fps_limit`.

Сейчас поведение противоречиво: подсказка в `ui/widgets/settings_page.py` прямо
говорит про режим Process Pool: **«⚠️ Preview не отображается (технические
ограничения)»** — то есть один из трёх режимов официально считается сломанным.
При этом остальные два режима (`single_thread`, `pipeline`) используют код,
который нарушает базовое правило потокобезопасности Qt (см. Часть 1) — то есть
формально «рабочий» путь на самом деле хрупкий и может ломаться непредсказуемо
в зависимости от машины, драйверов GPU, версии Qt, DPI-масштабирования и т.д.
Это и есть причина жалобы «предпросмотр не работает при всех возможных
настройках CPU/GPU» — три режима обработки используют **три разных, независимо
написанных и разошедшихся друг с другом** куска кода для одной и той же задачи
«показать кадр в UI», и минимум два из них некорректны с точки зрения
Qt-threading, а третий не оптимизирован и может «захлёбываться».

---

## ВАЖНЕЙШИЙ КОНТЕКСТ

В репозитории уже есть прецедент: в `processing/detector_process_pool.py` разработчик
**явно знал** про проблему и написал комментарий:

```python
def _emit_frame(self, image: np.ndarray, detections: list[dict]) -> None:
    """
    Рисует bbox'ы и отправляет BGR numpy кадр в UI.

    ВАЖНО: НЕ создаём QPixmap здесь! ResultAggregatorThread — это QThread,
    а QPixmap нельзя создавать в non-GUI потоке (Qt ограничение).
    Вместо этого отправляем annotated numpy array, а ProcessingController
    или ProcessingPage создаст QPixmap в главном GUI потоке.
    """
```

Но **это же самое правило было нарушено** в двух других местах того же
проекта: `processing/detector_thread.py` (используется режимами `single_thread`
и `pipeline` — то есть двумя из трёх режимов!) и в мёртвом коде
`processing/detector_pool.py`. Официальная документация Qt прямо говорит:
`QPixmap` — GUI-класс, который можно создавать и использовать **только в
главном (GUI) потоке**; `QImage` в этом смысле безопаснее (не привязан к
platform-специфичным хендлам экрана), но `QPixmap.fromImage(...)` и
`.scaled(...)` на `QPixmap` — уже нет. Именно расхождение реализаций и
объясняет «работает через раз в зависимости от настроек».

**Правило №1 при работе с этим промптом: не патчить симптомы через
`try/except: pass`, не добавлять `time.sleep`, не оборачивать в дополнительные
проверки «на всякий случай». Нужно унифицировать все три пути под уже
существующий в этом же репозитории ПРАВИЛЬНЫЙ паттерн** (dict с сырыми байтами
→ конвертация в `QPixmap` только в главном потоке), который уже частично
реализован для Process Pool в `ProcessingController._on_process_pool_frame`.

---

## ЧАСТЬ 1. КОРНЕВОЙ БАГ: `QPixmap` создаётся вне GUI-потока

### 1.1. `processing/detector_thread.py::DetectorThread._emit_frame`

Используется **и режимом `single_thread`, и режимом `pipeline`** (в
`_process_loop()` разница между этими режимами — только флаг `skip_ocr`,
вызовы `_emit_frame` общие). Код:

```python
def _emit_frame(self, image: np.ndarray) -> None:
    """Конвертирует BGR numpy → QPixmap и отправляет в UI."""
    rgb   = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg  = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg).scaled(
        960, 540,
        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
    )
    self.frame_ready.emit(pixmap)
```

Этот метод вызывается изнутри `DetectorThread.run() → _process_loop()`, то
есть **внутри самого `QThread`**, не в главном потоке. `QPixmap.fromImage()` и
`.scaled()` создают/модифицируют объект `QPixmap` — при этом полностью
нарушается требование Qt «GUI-объекты только из GUI-потока». На части систем
(Windows + `QT_OPENGL=software`, как сейчас в `main.py`) это может «просто
работать» случайно, но является потенциальным источником: искажённой картинки,
зависаний, падений `0xC0000409`-подобных ошибок (в проекте уже была целая серия
похожих крашей — см. `docs/CRASH_FIX_0xC0000409.md`, `BUGFIX_GEOJSON_CRASH.md`
и др.), либо просто «предпросмотр иногда не обновляется» на других
конфигурациях GPU/драйверов/масштабирования экрана.

**Вызывается в 4 местах внутри `_process_loop()`:**
1. Когда машина стоит (`speed < MIN_SPEED_KMH`) — `self._emit_frame(raw.image)`.
2. Когда кадр пропущен умным skipping'ом — `self._emit_frame(raw.image)`.
3. В финале обработки кадра — `self._emit_frame(annotated)` (кадр с bbox).

Все три вызова обёрнуты в `if self._should_emit_preview():` (троттлинг FPS —
это часть работает правильно и её трогать не нужно), но сам `_emit_frame`
одинаково нарушает threading-правило во всех случаях, то есть баг проявляется
**и в single_thread, и в pipeline режиме, независимо от CPU/GPU** — оба
использующих один и тот же метод.

### 1.2. `processing/detector_pool.py::DetectorWorker`/`DetectorPool` (мёртвый, но опасный код)

```python
def _emit_frame(self, image, detections):
    """Отправляет кадр с bbox'ами в UI."""
    ...
    rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
    pixmap = QPixmap.fromImage(qimg).scaled(
        960, 540,
        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
    )
    self.frame_ready.emit(pixmap)
```

Этот метод вызывается из `AggregatorThread._aggregator_loop()`, тоже внутри
`QThread`. **ВАЖНО:** этот класс `DetectorPool` сейчас **не используется**:

```python
# processing/processing_controller.py
USE_DETECTOR_POOL = False  # ВРЕМЕННО ОТКЛЮЧЕНО (требует тестирования на реальном видео)
...
def start(self) -> None:
    ...
    if config.PROCESSING_MODE == "process_pool":
        self._start_process_pool()
    elif config.PROCESSING_MODE == "single_thread" or config.PROCESSING_MODE == "pipeline":
        self._start_detector()
    else:
        ...
        self._start_detector()
```

Метод `_start_detector_pool()` определён в файле, но **нигде не вызывается** —
ни через `USE_DETECTOR_POOL`, ни как-то ещё. `ui/widgets/settings_page.py`
предлагает пользователю только 3 варианта режима («Один поток», «Pipeline»,
«Process Pool») — варианта, соответствующего `DetectorPool`, в UI просто нет.
Это подтверждённо мёртвый код, который: (а) содержит тот же баг, что и раздел
1.1, (б) не синхронизирован с более новыми исправлениями в `SignHandler`/
`config` (нет привязки к настройкам bearing-geometry, нет OCR-троттлинга и
т.д.), (в) создаёт риск, что кто-то в будущем случайно включит его и вернёт уже
исправленный где-то ещё баг.

### 1.3. `processing/detector_process_pool.py` — ЧАСТИЧНО правильный путь

`ResultAggregatorThread._emit_frame` (это тоже `QThread`) **правильно** не
создаёт `QPixmap`, а отправляет чистые данные:

```python
def _emit_frame(self, image: np.ndarray, detections: list[dict]) -> None:
    ...
    frame_dict = {
        'image_bytes': frame.tobytes(),
        'shape': frame.shape,
        'dtype': str(frame.dtype),
    }
    self.frame_ready.emit(frame_dict)
```

А сборка `QPixmap` происходит в `ProcessingController._on_process_pool_frame`,
который благодаря цепочке сигнал→сигнал (`ResultAggregatorThread.frame_ready`
→ `DetectorProcessPool.frame_ready` → `ProcessingController._on_process_pool_frame`)
и тому, что `DetectorProcessPool`/`ProcessingController` живут в главном потоке
(созданы без `moveToThread`), реально выполняется **в главном GUI-потоке**:

```python
def _on_process_pool_frame(self, frame_data):
    ...
    if isinstance(frame_data, dict) and 'image_bytes' in frame_data:
        dtype = np.dtype(frame_data['dtype'].replace('dtype(', '').replace(')', '').strip("'"))
        image = np.frombuffer(frame_data['image_bytes'], dtype=dtype).reshape(frame_data['shape'])
        rgb = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
        h, w, ch = rgb.shape
        qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888)
        pixmap = QPixmap.fromImage(qimg).scaled(960, 540, aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio)
        self.frame_ready.emit(pixmap)
    elif isinstance(frame_data, np.ndarray):
        ...  # тот же код для «сырого» numpy
    else:
        # Fallback: если пришёл готовый QPixmap (Single Thread / Pipeline)
        self.frame_ready.emit(frame_data)
```

Это **правильный, потокобезопасный паттерн** — но, как ни странно, он же
используется как fallback-заглушка для QPixmap, приходящего из
`single_thread`/`pipeline` (см. ветку `else`), то есть даже сам код
подразумевает, что этот путь (баг 1.1) — костыль, который «просто прокидывается
дальше», а не исправляется.

**Вывод части 1:** нужно унифицировать все источники кадра под уже готовый,
рабочий, потокобезопасный паттерн из `_on_process_pool_frame`, вместо того
чтобы держать 3 разных реализации.

---

## ЧАСТЬ 2. Второй баг: в Process Pool режиме нет троттлинга FPS предпросмотра

`DetectorThread` троттлит частоту обновления UI через `_should_emit_preview()`
(настройка `AppSettings.preview_fps_limit`, по умолчанию 12 FPS) — см. блок
CPU-2 в `processing/detector_thread.py`. А вот `ResultAggregatorThread._process_result`
в `processing/detector_process_pool.py` вызывает `_emit_frame(...)`
**безусловно на каждом обработанном кадре**, без какого-либо троттлинга:

```python
def _process_result(self, frame_data: dict):
    ...
    logger.info(f"[ProcessPool._process_result] Вызываем _emit_frame для кадра {frame_data['frame_idx']}")
    self._emit_frame(image, frame_data['detections'])
    ...
```

При этом сам процесс сериализации кадра (`frame.tobytes()`, ~6 МБ на кадр
1920×1080×3) и его последующая десериализация в главном потоке
(`np.frombuffer` + `reshape` + `cv2.cvtColor` + создание `QImage`/`QPixmap` +
`.scaled()` дважды — один раз в `_on_process_pool_frame`, второй раз в
`ProcessingPage.set_frame`) — это ощутимая по объёму работа. В режиме Process
Pool несколько воркер-**процессов** могут поставлять результаты быстрее, чем
главный GUI-поток успевает их отрисовывать (особенно с GPU, где детекция
намного быстрее). Из-за отсутствия троттлинга и backpressure на уровне сигнала
`frame_ready` (в отличие от `_futures_q`, у которого `maxsize` есть, у очереди
Qt-событий для сигнала `frame_ready` лимита нет) главный поток может «тонуть» в
очереди накопившихся кадров для конвертации — GUI выглядит зависшим, лагает
или показывает сильно устаревшие кадры. Это, вероятно, и стоит за
формулировкой в `settings_page.py`: **«⚠️ Preview не отображается (технические
ограничения)»** — вероятно, ранее (или на конкретной машине разработчика) это
выглядело именно как «не отображается», хотя по коду видно, что механизм
технически пытается отправлять кадры.

Дополнительно, `ResultAggregatorThread._process_result` логирует **на уровне
`INFO` при каждом кадре**:
```python
logger.info(f"[ProcessPool._process_result] Вызываем _emit_frame для кадра {frame_data['frame_idx']}")
```
— это раздувает `roadscan.log` (аналогичная проблема с print()-per-frame уже
не раз чинилась в проекте, см. `docs/LOGGING_MIGRATION_GUIDE.md`,
`scripts/analyze_print_usage.py`), и является дополнительным подтверждением
отсутствия троттлинга.

---

## ЧАСТЬ 3. Дополнительные наблюдения (проверить, но не факт что баги)

Эти пункты **нужно перепроверить экспериментально** — они логически возможны,
но в предоставленном коде не 100% доказаны, в отличие от Частей 1 и 2:

1. **Контигуальность буфера перед `tobytes()`/`QImage`.** `image.copy()` в
   `_draw_boxes()`/`_emit_frame()` почти всегда даёт C-contiguous массив, а
   `ndarray.tobytes(order='C')` по умолчанию сам линеаризует данные в
   правильном порядке независимо от исходного layout — то есть по этому пункту,
   скорее всего, проблем нет, но стоит явно задокументировать это допущение
   комментарием / добавить `np.ascontiguousarray(...)` как defensive-код перед
   `.tobytes()`, если после рефакторинга источником кадра станет не только
   «полный» массив из VideoReader, но и, например, произвольный `crop`.

2. **`frame_data['dtype'].replace('dtype(', '')...`** в `_on_process_pool_frame`
   — защитный код для случая, если `str(np.dtype(...))` когда-либо вернёт
   `"dtype('uint8')"` вместо `"uint8"`. На практике `str(np.uint8_array.dtype)`
   всегда возвращает просто `"uint8"`, так что это мёртвая, но безвредная
   строка — можно упростить, но не обязательно.

3. **Первичный размер `video_label`.** `ProcessingPage.set_frame()` масштабирует
   `pixmap.scaled(self.video_label.size(), ...)` — если виджет ещё не
   отрисован (макет не устаканился при первом кадре сразу после переключения
   страницы), `self.video_label.size()` может быть маленьким/дефолтным, и
   первый кадр отобразится «сплюснутым».低-приоритетная полировка, не
   критично, но стоит проверить визуально.

4. **CUDA/CPU напрямую не участвует в отрисовке.** `use_cuda` влияет только на
   `device` YOLO-моделей (`configs/sign_models.py::_resolve_device()`) и на
   `easyocr.Reader(gpu=...)` — то есть сам путь «кадр → QPixmap» одинаков для
   CPU и GPU. Единственная связь с GPU/CPU — это **скорость появления кадров**:
   чем быстрее модели работают (GPU), тем чаще срабатывает Часть 1/Часть 2
   баги, то есть GPU-конфигурации будут проявлять проблему заметнее/чаще, а
   не наоборот.

---

## ЧАСТЬ 4. Целевая архитектура (что нужно сделать)

Единая, потокобезопасная точка сборки `QPixmap`, используемая **всеми тремя**
режимами. План:

### 4.1. Новый общий модуль-конвертер

Создать `processing/preview_utils.py`:

```python
"""
processing/preview_utils.py
Единая точка конвертации "сырой BGR-кадр" -> QPixmap.

ВАЖНО: функция build_pixmap_from_frame_dict() создаёт QImage/QPixmap и поэтому
ДОЛЖНА вызываться только из главного (GUI) потока. Воркеры (QThread или
worker-процессы) должны отправлять только словарь с сырыми байтами через
build_frame_dict(), не создавая никаких Qt GUI-объектов самостоятельно.
"""
from __future__ import annotations

import numpy as np
import cv2
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QImage, QPixmap


def build_frame_dict(image_bgr: np.ndarray) -> dict:
    """
    Вызывается из ЛЮБОГО потока/процесса.
    Сериализует BGR numpy-кадр в примитивные данные без создания Qt-объектов.
    """
    return {
        "image_bytes": image_bgr.tobytes(),
        "shape": image_bgr.shape,
        "dtype": str(image_bgr.dtype),
    }


def build_pixmap_from_frame_dict(
    frame_dict: dict,
    target_size: tuple[int, int] = (960, 540),
) -> QPixmap:
    """
    Вызывать ТОЛЬКО из главного GUI-потока.
    Восстанавливает numpy-массив и создаёт QPixmap.
    """
    dtype = np.dtype(frame_dict["dtype"])
    arr = np.frombuffer(frame_dict["image_bytes"], dtype=dtype).reshape(frame_dict["shape"])
    rgb = cv2.cvtColor(arr, cv2.COLOR_BGR2RGB)
    h, w, ch = rgb.shape
    # .copy() отвязывает QImage от временного буфера rgb до вызова .scaled()
    qimg = QImage(rgb.data, w, h, ch * w, QImage.Format.Format_RGB888).copy()
    return QPixmap.fromImage(qimg).scaled(
        target_size[0], target_size[1],
        aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,
    )
```

### 4.2. `processing/detector_thread.py`

`_emit_frame` должен **перестать создавать `QPixmap`**, только собирать
словарь и эмитить его (сигнал `frame_ready = pyqtSignal(object)` менять не
нужно — тип уже generic):

```python
from processing.preview_utils import build_frame_dict

def _emit_frame(self, image: np.ndarray) -> None:
    """Сериализует BGR-кадр и отправляет его как данные (без QPixmap!) —
    QPixmap собирается только в главном потоке, см. processing_controller.py."""
    self.frame_ready.emit(build_frame_dict(image))
```

Троттлинг (`_should_emit_preview()`) и все места вызова `_emit_frame(...)` —
**не трогать**, они уже корректны.

### 4.3. `processing/detector_pool.py` (мёртвый код)

Два варианта на выбор агента (принять решение и явно задокументировать его в
итоговом отчёте):

- **(Рекомендуется) Удалить файл целиком.** Класс нигде не используется
  (`USE_DETECTOR_POOL` не читается в `start()`, UI не предлагает такой режим).
  Перед удалением сделать `grep -rn "DetectorPool\|DetectorWorker" --include=*.py .`
  и убедиться, что единственные упоминания — внутри самого файла и
  неиспользуемый импорт/атрибут в `processing_controller.py` (`USE_DETECTOR_POOL`,
  `_start_detector_pool`) — их тоже убрать. Это соответствует принципу проекта
  «не оставлять вводящий в заблуждение мёртвый код» (см. `AUDIT_REPORT.md`,
  `WORK_SUMMARY.md`).
- **(Альтернатива, если планируется вернуть режим в строй)** Применить тот же
  фикс, что и в 4.2 (`build_frame_dict` вместо прямого создания `QPixmap`), и
  реально подключить режим через `AppSettings`/`config.PROCESSING_MODE` и
  выпадающий список в `settings_page.py`. Делать только если явно попросили —
  по умолчанию предпочтительно удаление.

### 4.4. `processing/detector_process_pool.py`

`ResultAggregatorThread._emit_frame` уже правильно не создаёт `QPixmap` —
достаточно:

1. Заменить самодельную сборку словаря на использование общей функции:
   ```python
   from processing.preview_utils import build_frame_dict
   ...
   def _emit_frame(self, image: np.ndarray, detections: list[dict]) -> None:
       frame = image.copy()
       for det in detections:
           ...  # рисование bbox остаётся как есть
       self.frame_ready.emit(build_frame_dict(frame))
   ```
2. **Добавить троттлинг**, аналогичный `DetectorThread._should_emit_preview()`.
   Проще всего — скопировать ту же логику (или вынести общий миксин/утилиту
   `PreviewThrottler`, если хочется чуть более DRY) в `ResultAggregatorThread`,
   используя то же значение `AppSettings.preview_fps_limit`:
   ```python
   # в __init__ ResultAggregatorThread:
   from configs.settings import get_app_settings
   settings = get_app_settings()
   self._preview_min_interval = (
       1.0 / settings.preview_fps_limit if settings.preview_fps_limit > 0 else 0.0
   )
   self._last_emit_time = 0.0

   def _should_emit_preview(self) -> bool:
       if self._preview_min_interval <= 0:
           return True
       now = time.monotonic()
       if now - self._last_emit_time < self._preview_min_interval:
           return False
       self._last_emit_time = now
       return True
   ```
   И в `_process_result`:
   ```python
   if self._should_emit_preview():
       self._emit_frame(image, frame_data['detections'])
   ```
3. Понизить/убрать шумное `logger.info(...)` на каждый кадр в
   `_process_result` до `logger.debug(...)`, и логировать его только внутри
   ветки, где реально произошёл эмит (иначе теряется смысл троттлинга по
   логам — лог должен показывать реальную частоту, а не частоту обработки).

### 4.5. `processing/processing_controller.py`

Здесь всё уже почти готово — `_on_process_pool_frame` уже умеет превращать
`dict` в `QPixmap` в главном потоке. Нужно:

1. Вынести саму конвертацию в `build_pixmap_from_frame_dict` из
   `preview_utils.py` (не дублировать код):
   ```python
   from processing.preview_utils import build_pixmap_from_frame_dict

   def _on_worker_frame_ready(self, frame_data):
       """Единый обработчик кадров от ЛЮБОГО источника детекции
       (DetectorThread / DetectorProcessPool). Выполняется в главном потоке —
       здесь и только здесь можно создавать QPixmap."""
       try:
           if isinstance(frame_data, dict) and "image_bytes" in frame_data:
               pixmap = build_pixmap_from_frame_dict(frame_data)
               self.frame_ready.emit(pixmap)
           elif isinstance(frame_data, np.ndarray):
               pixmap = build_pixmap_from_frame_dict(build_frame_dict(frame_data))
               self.frame_ready.emit(pixmap)
           else:
               # QPixmap уже готов (не должно происходить после фикса 4.2,
               # оставлено как безопасный fallback на переходный период)
               self.frame_ready.emit(frame_data)
       except Exception as e:
           logger.error(f"[ProcessingController] Ошибка конвертации кадра: {e}", exc_info=True)
   ```
2. Переподключить **оба** источника кадров на этот единый обработчик:
   ```python
   def _start_detector(self) -> None:
       self._detector = DetectorThread(...)
       self._detector.frame_ready.connect(self._on_worker_frame_ready)  # было: self.frame_ready
       ...

   def _start_process_pool(self) -> None:
       self._detector_pool = DetectorProcessPool(...)
       self._detector_pool.frame_ready.connect(self._on_worker_frame_ready)  # было: self._on_process_pool_frame
       ...
   ```
   (можно оставить имя `_on_process_pool_frame` и просто расширить его
   применение на оба источника — главное, чтобы **одна и та же функция**
   обслуживала оба пути, а не две почти идентичные копии).
3. Ничего в `ui/widgets/processing_page.py::ProcessingPage.set_frame()` менять
   не нужно — он как принимал `QPixmap`, так и продолжит принимать.

---

## ЧАСТЬ 5. UI/сообщения, которые нужно обновить

`ui/widgets/settings_page.py`, тултип для `_processing_mode_combo`:

```python
self._processing_mode_combo.setToolTip(
    "Режим обработки видео:\n\n"
    "• Один поток (рекомендуется для CPU) — ...\n\n"
    "• Pipeline — ...\n\n"
    "• Process Pool — детекция в нескольких процессах.\n"
    "  ⚠️ Медленнее на CPU из-за overhead!\n"
    "  Полезно только с GPU и большими батчами.\n"
    "  ⚠️ Preview не отображается (технические ограничения).\n\n"
    "⚡ Для CPU всегда выбирайте 'Один поток'"
)
```
и рядом:
```python
mt_group.add_row(
    "Режим обработки",
    "⚠️ Process Pool: нет preview, но результаты сохраняются",
    self._processing_mode_combo,
)
```

После фикса Части 4 предпросмотр в Process Pool должен полноценно работать —
**убрать формулировку «Preview не отображается»**. Если после реальных тестов
(Часть 6) выяснится, что предпросмотр в Process Pool всё ещё заметно лагает
из-за накладных расходов межпроцессной сериализации (это ожидаемо и нормально
при большом числе воркеров), скорректировать текст на честный, но не
пугающий: например, «Предпросмотр может обновляться реже, чем в других
режимах, из-за передачи кадров между процессами» — и оставить обновление
частоты через `preview_fps_limit` настраиваемым.

---

## ЧАСТЬ 6. План тестирования / матрица приёмки

Это ключевая часть — фикс из Части 4 нужно проверить **не только чтением
кода**, а фактическим запуском, на матрице:

| # | processing_mode | use_cuda | Ожидаемый результат |
|---|------------------|----------|----------------------|
| 1 | single_thread    | False (CPU) | Кадр обновляется плавно, без искажений, без крашей, bbox рисуются |
| 2 | single_thread    | True (GPU, если есть) | То же самое; частота кадров может быть выше, троттлинг должен удерживать её на уровне `preview_fps_limit` |
| 3 | pipeline         | False (CPU) | То же, что и (1) |
| 4 | pipeline         | True (GPU) | То же, что и (2) |
| 5 | process_pool     | False (CPU) | Кадр реально появляется и обновляется (а не «не отображается»), без сильного лага, без роста памяти со временем |
| 6 | process_pool     | True (GPU) | То же, что и (5); частота может быть ограничена троттлингом из 4.4 |

Для каждой строки прогнать короткое тестовое видео (1-3 минуты) целиком через
UI («Начать обработку» → дождаться нескольких секунд → «Завершить») и
зафиксировать:

1. **Визуально**: кадр в `video_label` действительно меняется (не «заморожен»
   на первом кадре), картинка не «зелёная»/не искажена по цвету (проверка, что
   BGR→RGB конвертация выполняется ровно один раз), рамки знаков (bbox)
   отрисованы поверх правильного кадра.
2. **Логи**: нет ни одного `Exception`/traceback, связанного с `QPixmap`,
   `QImage`, `frame_ready`; для Process Pool — в логах видно, что троттлинг
   реально снижает число эмитов относительно числа обработанных кадров
   (аналогично существующему логу `[SmartSkip] ... FPS: ...` у `DetectorThread`,
   можно завести похожий лог `[PreviewThrottle] ...` для ResultAggregatorThread).
3. **Память**: при обработке видео 5+ минут потребление памяти процессом не
   растёт монотонно (утечка через накопление необработанных `frame_ready`
   событий в очереди Qt-событий главного потока — косвенный признак того, что
   троттлинг из 4.4 не работает).
4. **Стабильность закрытия**: штатное закрытие приложения (крестик окна) во
   время активного предпросмотра не крашится и не зависает (см. существующий
   `MainWindow.closeEvent`).
5. **`pytest`, если добавлен** (см. Часть 7) — зелёный.

---

## ЧАСТЬ 7. Регрессионный тест (обязательно добавить)

Создать `tests/test_preview_utils.py`, не требующий реального `QApplication`
с видимым окном (использовать offscreen-платформу Qt: `QT_QPA_PLATFORM=offscreen`
или `pytest-qt`, если он уже используется в проекте; если нет — минимум
проверить `build_frame_dict()` без Qt вообще, а `build_pixmap_from_frame_dict()`
— с `QApplication` в offscreen-режиме):

```python
"""
tests/test_preview_utils.py
Тесты для processing/preview_utils.py — единой точки конвертации кадра в QPixmap.
"""
import numpy as np
import pytest

from processing.preview_utils import build_frame_dict, build_pixmap_from_frame_dict


def test_build_frame_dict_roundtrip():
    """Проверяет, что сериализация/десериализация не искажает данные."""
    img = np.random.randint(0, 255, (100, 200, 3), dtype=np.uint8)
    frame_dict = build_frame_dict(img)

    assert frame_dict["shape"] == (100, 200, 3)
    assert frame_dict["dtype"] == "uint8"

    restored = np.frombuffer(frame_dict["image_bytes"], dtype=np.dtype(frame_dict["dtype"]))
    restored = restored.reshape(frame_dict["shape"])
    assert np.array_equal(img, restored)


def test_build_pixmap_from_frame_dict(qapp):  # qapp — фикстура offscreen QApplication
    """Проверяет, что итоговый QPixmap имеет ожидаемый размер и не пуст."""
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:, :, 1] = 255  # зелёный кадр в BGR
    frame_dict = build_frame_dict(img)

    pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=(960, 540))

    assert not pixmap.isNull()
    assert pixmap.width() <= 960
    assert pixmap.height() <= 540
```

(добавить фикстуру `qapp` в `conftest.py`, если её ещё нет в проекте —
`QApplication(["-platform", "offscreen"])`, если тестов на PyQt в проекте
раньше не было).

Также желательно добавить простой юнит-тест на троттлинг из 4.4
(`ResultAggregatorThread._should_emit_preview`) — по аналогии с логикой,
которая уже используется в `DetectorThread`: при `preview_fps_limit=0` всегда
`True`; при высоком значении — не чаще одного `True` в измеряемый интервал.

---

## ЧАСТЬ 8. Антипаттерны, которых нужно избегать (важно!)

В истории этого проекта уже было много `.md`-файлов, декларирующих «исправлено»
без факта проверки (см. `AUDIT_REPORT.md`, `WORK_SUMMARY.md`,
`REVERT_CNN_COUNT_TO_ORIGINAL.md` и т.д. — цикл «починили → откатили → опять
починили» вокруг одной и той же метрики без тестов). Не повторяй это:

1. **Не добавляй `try/except: print(...)` вокруг `QPixmap`/`QImage`** как
   способ «не крашиться» — если исключение возникает из-за неправильного
   потока, обработка исключения не чинит причину, а просто прячет симптом.
2. **Не добавляй `time.sleep`/искусственные задержки** «чтобы GUI успевал» —
   верное решение — троттлинг по времени (Часть 4.4), а не блокировка потоков.
3. **Не оставляй два места с одинаковой логикой конвертации кадра.** Если
   после фикса в коде всё ещё есть больше одного места, которое явно вызывает
   `QPixmap.fromImage(...)` — считай задачу не выполненной.
4. **Не удаляй троттлинг предпросмотра** (`_should_emit_preview` в
   `DetectorThread`) при рефакторинге — он важен для производительности и не
   связан с багом из Части 1.
5. **Не декларируй фикс «готовым» без прогона хотя бы одного реального видео**
   в каждом из 3 режимов (см. матрицу в Части 6) — обнови `STATUS.md` или
   создай новый отчёт только с конкретными результатами, а не общими фразами
   «исправлено и протестировано» без деталей (это именно то, за что уже
   критиковали предыдущих агентов в этом репозитории).

---

## ЧАСТЬ 9. Пошаговый план работы

1. Прочитать `processing/detector_thread.py`, `processing/detector_pool.py`,
   `processing/detector_process_pool.py`, `processing/processing_controller.py`,
   `ui/widgets/processing_page.py`, `ui/widgets/settings_page.py` полностью,
   сверить с описанием в Частях 1–3 — убедиться, что код с момента написания
   этого промпта не изменился (если изменился — актуализировать анализ).
2. Создать `processing/preview_utils.py` (Часть 4.1).
3. Поправить `processing/detector_thread.py::_emit_frame` (Часть 4.2).
4. Принять и задокументировать решение по `processing/detector_pool.py`
   (удалить или почистить + подключить, Часть 4.3), выполнить `grep`-проверку
   перед удалением.
5. Поправить `processing/detector_process_pool.py`: единая сериализация +
   троттлинг + понижение уровня логов (Часть 4.4).
6. Поправить `processing/processing_controller.py`: единый обработчик
   `_on_worker_frame_ready`, переподключить оба источника кадров (Часть 4.5).
7. Обновить тексты в `ui/widgets/settings_page.py` (Часть 5) — но только
   ПОСЛЕ реальной проверки по матрице (Часть 6), не раньше.
8. Написать `tests/test_preview_utils.py` (Часть 7), прогнать `pytest`.
9. Прогнать матрицу из Части 6 вручную (минимум CPU-конфигурацию по всем трём
   режимам; GPU — если физически доступна на машине, где выполняется задача;
   если GPU недоступна физически, явно пометить эти строки матрицы как «не
   проверено — нет GPU на машине агента», а не выдумывать результат).
10. Написать краткий отчёт (можно добавить в `STATUS.md` или отдельный
    `PREVIEW_FIX_REPORT.md`) со **фактическими** результатами по каждой строке
    матрицы, включая логи/скриншоты там, где это возможно, и явно указать,
    что осталось не проверенным.

---

## КРИТЕРИИ ПРИЁМКИ

- [ ] В проекте есть **ровно одно** место, создающее `QPixmap`/`QImage.copy()`
      из кадра детекции — и оно гарантированно выполняется в главном потоке.
- [ ] `processing/detector_thread.py` больше не импортирует/не использует
      `QPixmap` внутри `run()`/`_process_loop()`/`_emit_frame()`.
- [ ] `processing/detector_pool.py` либо удалён, либо использует тот же
      безопасный паттерн, что и остальные пути, и явно подключён к UI/настройкам.
- [ ] `processing/detector_process_pool.py::ResultAggregatorThread` троттлит
      частоту эмита предпросмотра через `AppSettings.preview_fps_limit`,
      аналогично `DetectorThread`.
- [ ] Убрано избыточное `logger.info(...)` на каждый кадр в
      `ResultAggregatorThread._process_result`.
- [ ] Предпросмотр реально работает (проверено вручную) в режиме Process Pool
      — устаревшая формулировка «Preview не отображается» в
      `settings_page.py` убрана или заменена на честное, актуальное описание.
- [ ] Добавлены и проходят тесты `tests/test_preview_utils.py`.
- [ ] Матрица из Части 6 прогнана хотя бы для CPU-конфигураций всех трёх
      режимов, результаты задокументированы фактически (не декларативно).
- [ ] Нет новых `print()` — только `logging` (согласуется с общей политикой
      проекта, см. `docs/LOGGING_MIGRATION_GUIDE.md`).
- [ ] `ProcessingPage.set_frame()` не изменялся (или изменён обоснованно и с
      той же обратной совместимостью сигнатуры `set_frame(pixmap: QPixmap)`).
