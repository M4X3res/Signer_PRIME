# BLOCK SIGN-LOSS / SETTINGS-UX — Промпт для AI-агента

**Файл предназначен для:** `prompts/PROMPT_FIX_SIGN_LOSS_AND_SETTINGS_MODES.md`
**Дата составления:** 2026-09-04
**Статус:** Требует выполнения
**Приоритет:** КРИТИЧНЫЙ (Часть A — потеря данных), ВЫСОКИЙ (Часть B — UX настроек)

---

## 0. Как пользоваться этим документом

Это не абстрактное ТЗ, а конкретный список багов с указанием файла/метода, объяснением
причины и предложенным диффом. Работай строго по разделам ниже, по порядку:

1. Сначала прочитай раздел 1 «Контекст» и раздел 2 «Правила работы».
2. Выполни **Часть A** целиком (это критично — сейчас теряются данные пользователя).
   Каждый баг — это отдельный коммит с собственным regression-тестом.
3. Только после того как все тесты из Части A зелёные — переходи к **Части B**
   (разделение настроек на Простой/Расширенный режим).
4. В конце пройди чек-лист из раздела 5 (Definition of Done) и раздел 6 («Что НЕ трогать»).

Каждое исправление обязано:
- использовать `logging` (модульный `logger = logging.getLogger(__name__)`), а не голый `print`,
  если рядом уже есть `logger` — следуй существующему стилю файла;
- не убирать существующие защитные `try/except`, а расширять их так, чтобы **ошибка была
  видна** (в логе и, где уместно, в UI), а не тонула молча;
- сопровождаться отдельным тестовым файлом в `tests/` в том же стиле, что и уже
  существующие (`tests/test_reorder_buffer.py`, `tests/check_dashboard_page.py` —
  простые скрипты с `assert` и `if __name__ == "__main__": ... print("PASS"/"FAIL")`,
  без обязательной зависимости от pytest, чтобы их можно было прогнать без тяжёлых
  ML-зависимостей).

---

## 1. Контекст

Проект — десктопное приложение (PyQt6) для детекции дорожных знаков на видео с GPS-треком.
Конвейер обработки:

```
VideoReaderThread → frame_queue → DetectorThread → result_queue → ProcessingController
                                        │                                  │
                                        ▼                                  ▼
                                  SignHandler                    MainWindow._on_finish()
                                  (трекинг знаков)                       │
                                        │                                ▼
                                        ▼                        FinalHandler.save_result()
                              result_signs (финализированные)              │
                                                                            ▼
                                                                     signs.geojson
```

Пользователь сообщает: **«снова сломалась сама обработка и сохранение знаков»**.
Это уже не первый раз (см. `docs/BUGFIXES_2026-07-09.md`, `docs/CRASH_FIX_v1.3.3.md`,
`CRASH_FIX_GEOJSON_BUTTON.md`, `docs/CACHE_FIX.md` и т.д. — история повторяющихся
регрессий в этом самом месте). Ниже — результат построчного аудита текущего кода,
который выявил **4 конкретных, воспроизводимых источника потери/недостоверности
данных**, независимо от версии моделей и настроек детекции.

---

## 2. Правила работы (обязательно к прочтению)

- **Не чини одно — не ломай другое.** В истории проекта уже был случай, когда за
  устранение бага с потерей знаков приняли «увеличение размера очереди»
  (`RESULT_QUEUE_SIZE` был поднят с 500 до 5000, см. `processing/processing_controller.py`,
  комментарий `# увеличено с 500 до 5000 для длинных видео`). Это не устраняет причину
  (см. БАГ №1 ниже), а лишь отодвигает её проявление. **Всегда исправляй причину, а не
  симптом.**
- **Каждое исправление подтверждай тестом**, а не декларацией "должно работать теперь".
  Если для теста нужны тяжёлые зависимости (torch/YOLO/OpenCV с реальным видео) —
  вместо этого пиши unit-тест на чистой логике (как это уже сделано в
  `tests/test_reorder_buffer.py`), не требующий реальных моделей.
- **Логируй достаточно, чтобы будущую регрессию можно было найти по `roadscan.log`
  за 5 минут**, а не через повторный построчный аудит всего конвейера.
- Работай маленькими коммитами по одному багу за раз, и после каждого — прогоняй
  уже существующие тесты в `tests/`, которые не требуют реальных видео/моделей
  (например, `tests/check_eager_loading.py`, `tests/test_reorder_buffer.py`,
  `tests/test_performance_optimizations.py`, `tests/check_socketio_config.py`,
  `tests/check_dashboard_page.py`), чтобы не создавать новых регрессий.

---

## 3. ЧАСТЬ A — Устранение потери знаков при обработке и сохранении

### A.1 БАГ №1 (КРИТИЧНО): знаки теряются навсегда при переполнении `result_queue`

**Файл:** `processing/detector_thread.py`, метод `DetectorThread._process_loop()`.

**Текущий код:**

```python
# Финальные знаки → в очередь результатов
if self._sign_handler.result_signs:
    logger.debug(f"Добавляю {len(self._sign_handler.result_signs)} знаков в очередь")
for sign in self._sign_handler.result_signs:
    # Ограниченная очередь — неблокирующий put
    try:
        self._result_q.put(sign, timeout=0.1)
    except queue.Full:
        # При переполнении — пропускаем с предупреждением
        # (знаки не теряются — они остаются в sign_handler.turns)
        logger.warning(f"result_queue переполнена! Пропуск знака {sign.best_cnn}. Размер очереди: {self._result_q.qsize()}")
        break  # Выходим из цикла, остальные знаки обработаем в следующий раз

self._sign_handler.result_signs.clear()
```

**Почему это баг:** при `queue.Full` цикл прерывается через `break`, но строка
`self._sign_handler.result_signs.clear()` выполняется **безусловно**, вне зависимости
от того, сколько знаков реально попало в очередь. В результате:
- знак, на котором случился `queue.Full`, теряется;
- ВСЕ знаки, которые шли за ним в списке (до которых цикл не дошёл из-за `break`),
  тоже теряются;
- комментарий «знаки не теряются — они остаются в sign_handler.turns» неверен: это
  уже **финализированные** знаки (`result_signs`), они не хранятся в `turns` и нигде
  больше не восстанавливаются.

Это же — самое вероятное объяснение того, почему увеличение `RESULT_QUEUE_SIZE` до 5000
«помогло, но не до конца»: баг воспроизводится реже, но не исчез.

**Требуемое исправление:**

```python
# Финальные знаки → в очередь результатов
if self._sign_handler.result_signs:
    logger.debug(f"Добавляю {len(self._sign_handler.result_signs)} знаков в очередь")

remaining: list = []
for sign in self._sign_handler.result_signs:
    try:
        self._result_q.put(sign, timeout=0.1)
    except queue.Full:
        # BLOCK SIGN-LOSS-1 FIX: НЕ теряем знак — откладываем его и пробуем
        # отправить повторно на следующей итерации цикла, когда в очереди
        # освободится место (её вычитывает ProcessingController.get_result_signs()
        # только в конце обработки, поэтому переполнение — явление временное).
        logger.warning(
            f"result_queue переполнена (размер={self._result_q.qsize()})! "
            f"Знак {sign.best_cnn} отложен и будет отправлен повторно."
        )
        remaining.append(sign)

# ВАЖНО: очищаем список знаний, которые ДЕЙСТВИТЕЛЬНО ушли в очередь.
# Всё, что не поместилось, остаётся в self._sign_handler.result_signs и
# НИКОГДА не удаляется молча.
self._sign_handler.result_signs = remaining
if remaining:
    logger.warning(f"[SignLoss-Guard] {len(remaining)} знаков ожидают повторной отправки в очередь")
```

То же самое (по аналогии) нужно проверить и поправить в блоке `finally` метода
`DetectorThread.run()`, где идёт финальная отправка знаков после
`sign_handler.finalize_remaining()` — там сейчас `break` без сохранения "хвоста":

```python
if self._sign_handler.result_signs:
    logger.debug(f"Добавляю финальные {len(self._sign_handler.result_signs)} знаков в очередь")
    for sign in self._sign_handler.result_signs:
        try:
            self._result_q.put(sign, timeout=0.1)
        except queue.Full:
            logger.warning(f"result_queue переполнена при финальной отправке! Пропуск знака {sign.best_cnn}")
            break
    self._sign_handler.result_signs.clear()
```

Здесь `break` внутри `finally` — это последний шанс что-либо сохранить (после этого
поток завершается), поэтому механизм «отложить на следующую итерацию» не работает.
Правильное решение здесь: **блокирующий put с разумным таймаутом на каждый знак**
(например, `timeout=2.0`) вместо `timeout=0.1`, и цикл **не прерывать** через `break`,
а пытаться каждый знак по отдельности, логируя реальные потери (если совсем не
получилось — это единственное место, где потеря действительно допустима, но она
обязана быть громко залогирована с точным списком типов потерянных знаков, а не
одной строкой "пропуск знака X"):

```python
if self._sign_handler.result_signs:
    logger.debug(f"Финальная отправка {len(self._sign_handler.result_signs)} знаков в очередь")
    lost = []
    for sign in self._sign_handler.result_signs:
        try:
            self._result_q.put(sign, timeout=2.0)
        except queue.Full:
            lost.append(sign.best_cnn)
    if lost:
        logger.error(
            f"[SignLoss-Guard] КРИТИЧНО: {len(lost)} знаков потеряны при финальной "
            f"отправке (очередь не освободилась даже за 2с/знак): {lost}"
        )
    self._sign_handler.result_signs.clear()
```

**Regression-тест:** `tests/test_result_queue_no_loss.py`
- Создать `queue.Queue(maxsize=2)`.
- Создать 5 фиктивных объектов (можно использовать `TrackedSign()` из `core/sign.py`
  без реальных детекций, просто с заполненным `cnn_results=["3.24"]`).
- Смоделировать `SignHandler.result_signs = [...]` вручную (без реального трекинга —
  тест логики отправки в очередь, а не трекинга) и прогнать логику из
  исправленного блока (лучше вынести саму логику "отправить и вернуть остаток" в
  отдельную тестируемую функцию/метод, например `DetectorThread._flush_result_signs(sign_handler, result_q)`,
  чтобы её можно было протестировать без создания `QThread`).
- Утверждение: после нескольких проходов (эмулирующих то, что очередь освобождают
  между вызовами) сумма отправленных + оставшихся в `result_signs` знаков **всегда**
  равна изначальному количеству — ни один объект не исчезает.

> Рекомендация по рефакторингу для тестируемости: вынеси кусок «положить result_signs
> в result_q» в приватный метод `_flush_result_signs()` внутри `DetectorThread`,
> который принимает `sign_handler` и `queue`, а не читает их из `self`. Это упростит
> модульное тестирование без поднятия реального `QThread`/моделей.

---

### A.2 БАГ №2 (КРИТИЧНО): восстановление из checkpoint фактически не работает

**Файлы:** `processing/processing_controller.py` (`ProcessingController.start()`,
`_reset_config()`, `load_checkpoint()`), `processing/detector_thread.py`
(`DetectorThread.__init__`, `DetectorThread.run()`).

**Проблема 1 — индексы восстанавливаются и тут же обнуляются.**

`MainWindow._on_start()` вызывает (в таком порядке):

```python
if self._controller.has_checkpoint():
    ...
    if reply == QMessageBox.StandardButton.Yes:
        if self._controller.load_checkpoint():   # ← восстанавливает config.INDEX_OF_*
            ...
...
self._controller.start()                          # ← а start() их тут же обнуляет!
```

А `ProcessingController.start()` первой же строкой делает:

```python
def start(self) -> None:
    if self._running:
        return
    self._reset_config()   # ← безусловно: INDEX_OF_FRAME=0, INDEX_OF_VIDEO=0, ...
    ...
```

и `_reset_config()`:

```python
def _reset_config(self) -> None:
    ...
    config.COUNT_PROCESSED_FRAMES = 0
    config.INDEX_OF_FRAME       = 0
    config.INDEX_OF_VIDEO       = 0
    config.INDEX_OF_All_FRAME   = 0
    config.INDEX_OF_GPS         = 0
    config.INDEX_OF_SING        = 0
```

То есть какие бы индексы ни восстановил `load_checkpoint()`, `start()` их безусловно
затирает нулями. Восстановление позиции в видео **никогда не срабатывает**.

**Проблема 2 — сами найденные знаки из checkpoint нигде не применяются.**

`load_checkpoint()` пишет:

```python
# Знаки будут восстановлены при старте DetectorThread
self._checkpoint_data = checkpoint_data
```

Но ни в `ProcessingController._start_detector()`, ни в `DetectorThread.__init__()`,
ни в `DetectorThread.run()` **нет ни одного обращения** к `self._checkpoint_data`
или к `controller._checkpoint_data`. `SignHandler` создаётся с нуля:

```python
self._sign_handler = SignHandler(settings=settings)
```

Итог: диалог «Найден сохранённый прогресс… Продолжить?» полностью честно врёт —
даже нажав «Да», пользователь теряет все ранее найденные знаки и начинает читать
видео с кадра 0, просто дополнительно неся риск дублирования (если файл видео
частично уже был обработан в прошлый раз и знаки из старого прогона всё равно
потеряны).

**Требуемое исправление, пошагово:**

**Шаг 1.** В `ProcessingController.__init__` явно завести состояние восстановления:

```python
def __init__(self, parent: Optional[QObject] = None):
    super().__init__(parent)
    self._reader:   Optional[VideoReaderThread] = None
    self._detector: Optional[DetectorThread]    = None
    self._detector_pool = None
    self._frame_q:  Optional[queue.Queue]       = None
    self._result_q: Optional[queue.Queue]       = None
    self._running   = False

    self._checkpoint_timer: Optional[QThread] = None
    self._last_checkpoint_time = 0

    # BLOCK SIGN-LOSS-2: состояние восстановления из checkpoint
    self._resume_from_checkpoint: bool = False
    self._checkpoint_data: Optional[dict] = None
```

**Шаг 2.** В `load_checkpoint()` выставлять флаг явно при успехе (сейчас он просто
пишет в `self._checkpoint_data`, флага нет вовсе):

```python
def load_checkpoint(self) -> bool:
    ...
    try:
        checkpoint_data = joblib.load(self.CHECKPOINT_PATH)
        cfg = checkpoint_data['config']
        config.INDEX_OF_FRAME = cfg['INDEX_OF_FRAME']
        config.INDEX_OF_VIDEO = cfg['INDEX_OF_VIDEO']
        config.INDEX_OF_All_FRAME = cfg['INDEX_OF_All_FRAME']
        config.INDEX_OF_GPS = cfg['INDEX_OF_GPS']
        config.FRAME_STEP = cfg['FRAME_STEP']
        config.VIDEOS = cfg['VIDEOS']
        config.PATH_TO_VIDEO = cfg['PATH_TO_VIDEO']
        config.PATH_TO_GPX = cfg['PATH_TO_GPX']
        config.PATH_TO_GEOJSON = cfg['PATH_TO_GEOJSON']

        self._checkpoint_data = checkpoint_data
        self._resume_from_checkpoint = True   # ← НОВОЕ

        logger.info(...)
        return True
    except Exception as e:
        logger.error(f"[Checkpoint] Ошибка загрузки: {e}")
        self._resume_from_checkpoint = False
        self._checkpoint_data = None
        return False
```

**Шаг 3.** `_reset_config()` — не трогать индексы, если восстанавливаемся:

```python
def _reset_config(self) -> None:
    """
    Сбрасывает индексы обработки перед НОВЫМ запуском.

    BLOCK SIGN-LOSS-2 FIX: если восстанавливаемся из checkpoint
    (self._resume_from_checkpoint == True), индексы НЕ трогаем — они уже
    выставлены в load_checkpoint(). Раньше это делалось безусловно, из-за
    чего восстановление позиции в видео не работало никогда.
    """
    from configs.settings import get_app_settings
    settings = get_app_settings()

    if settings.frame_step_mode == "manual" and settings.frame_step_manual > 0:
        config.FRAME_STEP = max(1, int(settings.frame_step_manual))
    else:
        config.FRAME_STEP = 5

    if self._resume_from_checkpoint:
        logging.getLogger(__name__).info(
            f"[ProcessingController] Resume: индексы НЕ сбрасываются "
            f"(video={config.INDEX_OF_VIDEO}, frame={config.INDEX_OF_FRAME}, "
            f"abs_frame={config.INDEX_OF_All_FRAME})"
        )
        return

    config.COUNT_PROCESSED_FRAMES = 0
    config.INDEX_OF_FRAME       = 0
    config.INDEX_OF_VIDEO       = 0
    config.INDEX_OF_All_FRAME   = 0
    config.INDEX_OF_GPS         = 0
    config.INDEX_OF_SING        = 0
```

**Шаг 4.** Прокинуть знаки из checkpoint в `DetectorThread`. Добавить параметр
конструктора:

```python
def __init__(
    self,
    frame_queue: queue.Queue,
    result_queue: queue.Queue,
    controller=None,
    checkpoint_signs: Optional[dict] = None,   # ← НОВОЕ
    parent=None,
):
    super().__init__(parent)
    ...
    self._checkpoint_signs = checkpoint_signs
```

И в `run()`, сразу после создания `self._sign_handler`:

```python
self._sign_handler = SignHandler(settings=settings)
self._gpx          = GPXHandler()
self._converter     = Converter()

# BLOCK SIGN-LOSS-2: восстанавливаем знаки из checkpoint, если есть
if self._checkpoint_signs:
    restored_result = list(self._checkpoint_signs.get('result_signs', []))
    restored_active = list(self._checkpoint_signs.get('active_signs', []))
    restored_turns  = list(self._checkpoint_signs.get('turns', []))
    self._sign_handler.result_signs = restored_result
    self._sign_handler.signs        = restored_active
    self._sign_handler.turns        = restored_turns
    logger.info(
        f"[Checkpoint] Восстановлено в SignHandler: "
        f"{len(restored_result)} финализированных, "
        f"{len(restored_active)} активных, {len(restored_turns)} поворотов"
    )
```

**Шаг 5.** В `ProcessingController._start_detector()` передать данные и **сразу
одноразово сбросить** флаг восстановления (чтобы следующий обычный запуск в этой
же сессии приложения не подхватил устаревший checkpoint):

```python
def _start_detector(self) -> None:
    checkpoint_signs = None
    if self._resume_from_checkpoint and self._checkpoint_data:
        checkpoint_signs = self._checkpoint_data.get('signs')

    self._detector = DetectorThread(
        self._frame_q, self._result_q,
        controller=self,
        checkpoint_signs=checkpoint_signs,
        parent=self
    )
    self._detector.frame_ready.connect(self._on_worker_frame_ready)
    self._detector.sign_detected.connect(self.sign_found)
    self._detector.stats_updated.connect(self.stats)
    self._detector.error.connect(self.error)
    self._detector.finished_work.connect(self._on_detector_finished)
    self._detector.start()

    # Одноразовое восстановление — данные переданы, флаг больше не нужен
    self._resume_from_checkpoint = False
    self._checkpoint_data = None
```

**Шаг 6 (SHOULD, не MUST — но настоятельно рекомендуется).** Защита от несоответствия
путей: если пользователь между сессиями сменил папку с видео/GPX, `load_checkpoint()`
молча подставит СТАРЫЕ `config.PATH_TO_VIDEO`/`config.VIDEOS`, что может привести к
попытке читать несуществующие/другие файлы. Добавь в `MainWindow._on_start()` перед
диалогом восстановления сверку: если `config.PATH_TO_VIDEO` (текущее, выбранное в
Dashboard) не совпадает с тем, что лежит в checkpoint-файле (можно получить лёгким
предварительным чтением заголовка `joblib.load` — или добавить в `ProcessingController`
метод `peek_checkpoint_paths() -> tuple[str, str]`, не грузящий тяжёлые списки знаков),
— показать отдельное предупреждение и не предлагать «Да» по умолчанию.

**Шаг 7 (SHOULD).** Режим `process_pool` сейчас **не поддерживает** восстановление
вообще (`SignHandler` в нём создаётся синхронно в `DetectorProcessPool.start()` в
главном потоке — гораздо проще прокинуть данные). Либо реализуй аналогичную инъекцию
в `DetectorProcessPool.start()` сразу после `self._sign_handler = SignHandler()`,
либо (минимум) залогируй явное предупреждение и НЕ восстанавливай молча частично:
```python
if config.PROCESSING_MODE == "process_pool" and self._resume_from_checkpoint:
    logging.getLogger(__name__).warning(
        "[ProcessingController] Восстановление знаков из checkpoint пока "
        "поддерживается только в режимах 'Один поток'/'Pipeline'. "
        "В Process Pool будут восстановлены только индексы позиции, "
        "но НЕ ранее найденные знаки."
    )
```

**Regression-тест:** `tests/test_checkpoint_resume.py`
- Создать `SignHandler`, добавить в `result_signs`/`signs`/`turns` несколько
  фиктивных объектов.
- Сохранить checkpoint через `ProcessingController.save_checkpoint()` (с моком
  `self._detector`/`self._detector_pool`, у которых есть `_sign_handler`).
- Создать новый `ProcessingController`, вызвать `load_checkpoint()`.
- Утверждение №1: после `load_checkpoint()` `config.INDEX_OF_FRAME` и т.д. равны
  сохранённым значениям, а `controller._resume_from_checkpoint is True`.
- Утверждение №2: вызвать `controller._reset_config()` напрямую и убедиться, что
  индексы **не обнулились** (это именно то место, где раньше терялось восстановление).
- Утверждение №3: смоделировать создание `DetectorThread` с `checkpoint_signs=...`
  и убедиться (без реального `run()`, просто вызвав кусок инициализации отдельно
  или проверив, что конструктор корректно сохраняет `self._checkpoint_signs`), что
  данные передаются насквозь.
- Не забудь удалить тестовый `checkpoint.pkl` после теста (`os.remove`), чтобы не
  засорять рабочую директорию.

---

### A.3 БАГ №3: одна повреждённая запись обнуляет весь пакет «прямых» знаков

**Файл:** `core/final_handler.py`, методы `save_result()`, `_process_straight_signs()`,
`_batch_snap_signs()`.

**Проблема.** `_batch_snap_signs()` строит список точек так:

```python
points = [(sign.car_y[-1], sign.car_x[-1]) for sign in signs]  # (lat, lon)
```

Если хотя бы у одного `TrackedSign` в `signs` пустые `car_x`/`car_y` (например,
после клонирования при разворачивании составного знака 5.8 через `copy.copy()`,
либо любой другой пограничный случай трекинга), это бросает `IndexError`. Само
исключение перехватывается ВЕРХНИМ `try/except` в `save_result()`:

```python
try:
    ...
    features = self._process_straight_signs(result_signs, progress_cb, total_signs)
    ...
except Exception as e:
    logger.error(f"[FinalHandler] ОШИБКА в _process_straight_signs: {e}")
    import traceback
    traceback.print_exc()
    features = []
```

В итоге: **все** прямые (не на поворотах) знаки этого прогона исчезают из GeoJSON
разом, из-за одной проблемной записи. При этом обработка "успешно" продолжается,
пишет файл, и `MainWindow` рапортует об успехе (см. БАГ №4 — вдобавок ещё и с
неверным числом).

**Требуемое исправление:**

1. Добавить валидацию входных данных ДО пакетного snap, чтобы один дефектный
   объект не мог обрушить обработку всех остальных:

```python
def _validate_signs_for_processing(self, signs: list[TrackedSign]) -> list[TrackedSign]:
    """
    BLOCK SIGN-LOSS-3: отфильтровывает знаки без валидных координат автомобиля,
    чтобы одна повреждённая запись не приводила к потере ВСЕХ остальных знаков
    в этом пакете (см. _batch_snap_signs — там раньше падал IndexError на
    sign.car_x[-1] для всего списка целиком).
    """
    valid, skipped = [], []
    for sign in signs:
        if not sign.car_x or not sign.car_y:
            skipped.append(sign)
            continue
        valid.append(sign)

    if skipped:
        logger.warning(
            f"[FinalHandler] Пропущено {len(skipped)} знаков без car_x/car_y "
            f"(типы: {[s.best_cnn for s in skipped]}) — не могут быть привязаны к карте"
        )
    return valid
```

Вызвать этот метод в начале `_process_straight_signs()`, до `_group_by_position()`
и до `_batch_snap_signs()`:

```python
def _process_straight_signs(self, signs, progress_cb=None, total_signs=0):
    signs = self._validate_signs_for_processing(signs)
    ...
```

2. В `save_result()` заменить `logger.error(f"... {e}")` + ручной
   `traceback.print_exc()` на `logger.exception(...)` (он сам приложит traceback
   в лог, это устойчивее и меньше кода):

```python
except Exception as e:
    logger.exception(f"[FinalHandler] ОШИБКА в _process_straight_signs")
    features = []
```

3. Добавить итоговую сводку в конец `save_result()`, чтобы расхождение
   «сколько знаков пришло / сколько реально записано» было видно с первого
   взгляда в логе (а не терялось среди сотен строк):

```python
total_input = len(result_signs) + sum(len(t.signs) for t in turns)
logger.info(
    f"[FinalHandler] ИТОГ: на входе знаков≈{total_input}, "
    f"после обработки и дедупликации записано {len(features)} features "
    f"→ {config.PATH_TO_GEOJSON}"
)
if len(features) < total_input * 0.5 and total_input > 0:
    logger.error(
        f"[FinalHandler] ВНИМАНИЕ: в файл попало менее половины знаков "
        f"({len(features)} из ~{total_input}). Проверь лог выше на ошибки этапов."
    )
```

**Regression-тест:** `tests/test_final_handler_resilience.py`
- Создать 3 нормальных `TrackedSign` (с заполненными `car_x`/`car_y`,
  `cnn_results`, `observation_count`) и 1 «битый» (`car_x = []`, `car_y = []`).
- Вызвать `FinalHandler()._validate_signs_for_processing([...])` напрямую.
- Утверждение: возвращены ровно 3 нормальных знака, битый отфильтрован, в
  логах (можно проверить через `caplog` при pytest, либо просто убедиться что
  функция не бросает исключение и возвращает нужную длину списка).
- Если инфраструктура позволяет без сети/моделей — дополнительно прогнать
  весь `_process_straight_signs()` на смеси нормальных+битых знаков и
  убедиться, что **нормальные знаки не теряются** из-за присутствия битого
  (можно замокать `_batch_snap_signs`, чтобы не ходить в Overpass API).

---

### A.4 БАГ №4: UI показывает недостоверное число «сохранённых» знаков

**Файлы:** `ui/main_window.py` (класс `SaveThread` внутри `_save_results()`),
`core/final_handler.py` (`FinalHandler.save_result()`).

**Проблема.** `save_result()` сейчас ничего не возвращает (`-> None`). А
`SaveThread.run()` делает так:

```python
def run(self):
    try:
        handler = FinalHandler()
        handler.save_result(self.signs, self.turns, progress_cb=self.progress.emit)
        self.finished_ok.emit(len(self.signs))   # ← число ВХОДНЫХ знаков, а не сохранённых!
    except Exception as e:
        ...
```

`len(self.signs)` — это количество `TrackedSign`, переданных В `FinalHandler`, а
не количество `Feature`, реально записанных в `signs.geojson` после дедупликации
и (в текущем виде, до фикса БАГ №3) возможных потерь на промежуточных этапах.
Пользователь видит в логе «Сохранено 214 знаков», хотя в файле может быть
меньше — из-за дедупликации (это нормально) либо из-за багов №1–3 (это не
нормально), и никак не может отличить одно от другого.

**Требуемое исправление:**

1. `FinalHandler.save_result()` должен возвращать фактическое количество
   записанных `Feature` (после дедупликации, прямо перед `geojson.dump`):

```python
def save_result(
    self,
    result_signs: list[TrackedSign],
    turns:        list,
    progress_cb=None,
) -> int:
    """
    ...
    Returns:
        Количество знаков (features), реально записанных в GeoJSON.
    """
    ...
    try:
        logger.info("[FinalHandler] Сохраняем GeoJSON...")
        collection = FeatureCollection(features)
        with open(config.PATH_TO_GEOJSON, "w", encoding="utf-8") as f:
            geojson.dump(collection, f, ensure_ascii=False)
        logger.info(f"[FinalHandler] Сохранено {len(features)} знаков → {config.PATH_TO_GEOJSON}")
    except Exception as e:
        logger.exception("[FinalHandler] ОШИБКА при сохранении файла")
        raise

    return len(features)
```

2. `SaveThread.run()` — использовать возвращённое значение:

```python
def run(self):
    try:
        handler = FinalHandler()
        saved_count = handler.save_result(
            self.signs,
            self.turns,
            progress_cb=self.progress.emit
        )
        self.finished_ok.emit(saved_count)
    except Exception as e:
        import traceback
        self.error.emit(f"{e}\n{traceback.format_exc()}")
```

3. (SHOULD) В `_on_save_finished(self, sign_count: int)` — если `sign_count`
   существенно меньше числа, которое было передано на вход (`len(signs)` из
   `_save_results()`, сохрани его в замыкании/атрибуте перед запуском потока),
   показать предупреждение пользователю, а не просто «успех»:

```python
def _save_results(self):
    ...
    signs = self._controller.get_result_signs()
    turns = self._controller.get_turn_data()
    self._last_input_sign_count = len(signs)   # ← сохранить для сравнения
    ...

def _on_save_finished(self, sign_count: int):
    print(f"[MainWindow] Сохранение завершено: {sign_count} знаков")
    t = theme_manager.tokens
    input_count = getattr(self, "_last_input_sign_count", sign_count)
    if input_count > 0 and sign_count < input_count * 0.5:
        self.status_bar.set_status(
            f"Сохранено только {sign_count} из {input_count} знаков — см. лог", t["warning"]
        )
        self.page_processing.log(
            f"⚠️ В файл попало заметно меньше знаков, чем было найдено "
            f"({sign_count} из {input_count}). Проверьте roadscan.log.", "warn"
        )
    else:
        self.status_bar.set_status("GeoJSON сохранён", t["success"])
        self.page_processing.log(f"Сохранено {sign_count} знаков в GeoJSON", "success")
    ...
```

**Regression-тест:** `tests/test_final_handler_return_value.py`
- Смонтировать вызов `save_result()` с двумя-тремя валидными `TrackedSign` (можно
  замокать `_batch_snap_signs`, чтобы не стучаться в сеть) и проверить, что
  возвращаемое значение — целое число, равное `len(features)` в записанном
  GeoJSON-файле (прочитать файл после вызова и сравнить `len(features)` внутри
  него с возвращённым значением).

---

### A.5 Дополнительное сквозное логирование (обязательно)

Чтобы будущую регрессию в этой цепочке можно было диагностировать по одному
`grep` в `roadscan.log`, а не повторным аудитом всего кода, добавь единый
«трейсер количества знаков» на каждой границе передачи данных:

| Точка | Что залогировать |
|---|---|
| `DetectorThread._process_loop()` — перед put в очередь | `len(self._sign_handler.result_signs)` каждый раз, когда список непустой |
| `ProcessingController.get_result_signs()` | уже логирует — не менять, но убедиться что уровень `INFO`, не `DEBUG` |
| `MainWindow._save_results()` | `len(signs)`, `len(turns)` — уже логируется, оставить |
| `FinalHandler.save_result()` (начало) | уже логируется |
| `FinalHandler.save_result()` (конец, после фикса БАГ №3) | итоговая сводка "на входе / записано" — добавлено выше |
| `SaveThread.finished_ok` | теперь несёт реальное число — логируется в `_on_save_finished` |

---

### A.6 Обязательные регрессионные тесты (сводка)

Создать в `tests/`:
1. `tests/test_result_queue_no_loss.py` — БАГ №1.
2. `tests/test_checkpoint_resume.py` — БАГ №2.
3. `tests/test_final_handler_resilience.py` — БАГ №3.
4. `tests/test_final_handler_return_value.py` — БАГ №4.

Каждый тест — самостоятельный скрипт, запускаемый как
`python tests/test_XXX.py`, с явным `PASS`/`FAIL` выводом в консоль и
`sys.exit(0/1)`, по аналогии с `tests/test_reorder_buffer.py`.

### A.7 Ручная проверка (чек-лист)

После выполнения всех фиксов из Части A прогнать вручную:

- [ ] Запустить обработку короткого тестового видео с GPX, дождаться
      естественного завершения → в логе видна итоговая сводка из A.5, число
      «записано» совпадает с числом объектов в получившемся `signs.geojson`.
- [ ] Запустить обработку, нажать «Завершить» в середине → GeoJSON всё равно
      содержит все знаки, найденные до этого момента (свериться по логу).
- [ ] Принудительно убить процесс (или закрыть окно) в середине обработки →
      запустить снова → согласиться на восстановление checkpoint → в логе
      видно `[Checkpoint] Восстановлено в SignHandler: N финализированных...`,
      и `config.INDEX_OF_VIDEO`/`INDEX_OF_FRAME` не равны 0 (если checkpoint
      был сделан не на первом кадре).
- [ ] Искусственно уменьшить `RESULT_QUEUE_SIZE` до `5` в
      `ProcessingController` (временно, для теста) и прогнать видео с большим
      количеством знаков — убедиться по логам, что появляются предупреждения
      `[SignLoss-Guard] N знаков ожидают повторной отправки`, но НЕ появляется
      `КРИТИЧНО: N знаков потеряны`, и итоговое число знаков в файле совпадает
      с ожидаемым. Вернуть `RESULT_QUEUE_SIZE` обратно к 5000 после теста.

---

## 4. ЧАСТЬ B — Простой / Расширенный режим настроек

### B.1 Требования (от пользователя, дословно)

> «нужно доработать настройки, чтобы был вариант простых и расширенных настроек,
> в простых оставь включение и выключения CUDA, её проверку, выбор на CPU моделей»

То есть:
- Должно быть два режима отображения страницы «Настройки»: **Простой** и
  **Расширенный**.
- В **Простом** режиме видны РОВНО три элемента управления (плюс сам
  переключатель режима):
  1. Переключатель «Использовать CUDA» (`_cuda_toggle`).
  2. Кнопка «Проверить GPU» + строка статуса (`gpu_check_btn` + `_gpu_status_label`).
  3. Выбор бэкенда инференса на CPU (`_cpu_backend_combo`: PyTorch / ONNX
     Runtime / OpenVINO).
- Всё остальное (тема, шаг кадра, пороги уверенности, дедупликация, GPS,
  многопоточность, разметка полос, логирование, геометрия перекрёстков,
  количество потоков ONNX/OpenVINO, экспорт моделей, экспорт/импорт настроек)
  — видно только в **Расширенном** режиме.
- По умолчанию для нового пользователя должен быть выбран **Простой** режим.

### B.2 Изменения в `configs/settings.py`

Добавить новое поле в `AppSettings` (например, рядом с `theme`):

```python
# ── UI режим страницы настроек (BLOCK SETTINGS-UX-1) ──────────
settings_ui_mode: Literal["simple", "advanced"] = "simple"
```

Больше ничего менять не нужно: `AppSettings.load()`, `.save()`, `.to_dict()`,
`.from_dict()` уже работают универсально через `__dataclass_fields__`, новое
поле подхватится автоматически (не забудь при этом проверить веткy типа `str`/
`Literal` в `load()` — она и так просто оставляет значение как есть для
нестандартных типов, что корректно для `Literal[...]`, который на деле хранится
как `str`).

### B.3 Изменения в `ui/widgets/settings_page.py`

**Шаг 1. Переключатель режима.** Добавь его в `outer` layout (то есть ВНЕ
`QScrollArea`, чтобы был виден постоянно, даже при скролле длинного списка
настроек), сразу под подзаголовком страницы, перед `scroll`:

```python
# ── Переключатель Простой/Расширенный ───────────────────────────
mode_row = QHBoxLayout()
mode_row.setSpacing(6)

self._btn_mode_simple = QPushButton("Простой режим")
self._btn_mode_advanced = QPushButton("Расширенный режим")
for b in (self._btn_mode_simple, self._btn_mode_advanced):
    b.setObjectName("BtnSecondary")
    b.setCheckable(True)
    b.setMinimumHeight(34)
    b.setCursor(Qt.CursorShape.PointingHandCursor)

self._btn_mode_simple.clicked.connect(lambda: self._set_ui_mode("simple"))
self._btn_mode_advanced.clicked.connect(lambda: self._set_ui_mode("advanced"))

mode_row.addWidget(self._btn_mode_simple)
mode_row.addWidget(self._btn_mode_advanced)
mode_row.addStretch()

outer.addLayout(mode_row)
outer.addSpacing(16)
```

Визуально «активную» кнопку нужно выделять — используй тот же паттерн, что
уже применяется в `SidebarItem.set_active()` или в фильтр-чипах на карте
(`templates/map.html`, `.filter-chip.active`): достаточно менять
`setObjectName`/стиль или просто эксплицитно красить фон активной кнопки
токеном `theme_manager.tokens['accent']`, а неактивной — `bg_hover`. Не
изобретай новую систему стилей — переиспользуй `theme_manager.tokens`.

**Шаг 2. Разделить группу «Диагностика системы» на две.**

Сейчас всё (CUDA-тумблер, проверка GPU, выбор бэкенда, потоки ONNX/OpenVINO,
экспорт моделей) лежит в одном `diag_group`. Нужно:

- `compute_group` — **новая** группа (можно назвать «Вычисления (CPU / GPU)»),
  строится ПЕРВОЙ, содержит только:
  - строку с `self._cuda_toggle`;
  - строку с `gpu_widget` (кнопка «Проверить GPU» + `self._gpu_status_label`);
  - строку с `self._cpu_backend_combo`.
  Эта группа **видна в обоих режимах** (не добавляется в список
  `self._advanced_only_widgets`, см. ниже).

- `diag_group_advanced` (переименовать текущий `diag_group`, оставить только
  оставшиеся строки) — содержит:
  - потоки ONNX intra_op (`self._cpu_onnx_intra_spin`);
  - потоки OpenVINO (`self._cpu_openvino_threads_spin`);
  - кнопку экспорта моделей + статус (`export_models_widget`).
  Эта группа видна **только в Расширенном режиме**.

Порядок конструирования групп в `__init__`: `compute_group` теперь стоит
логично разместить одной из первых (например, сразу после `ui_group`), чтобы
в Простом режиме пользователь сразу видел именно её, а не пустую страницу с
одним переключателем сверху.

**Шаг 3. Список групп, скрываемых в Простом режиме.**

После того как все группы добавлены в `content_layout`, сохрани ссылки на
те из них, что должны быть скрыты в Простом режиме:

```python
self._advanced_only_widgets: list[QWidget] = [
    ui_group,             # Интерфейс / тема
    proc_group,           # Обработка видео
    gps_group,             # GPS и координаты
    mt_group,               # Многопоточность
    lane_group,             # Разметка полос движения
    log_group,               # Логирование
    turn_group,               # Перекрёстки и повороты
    diag_group_advanced,       # Расширенная диагностика (потоки, экспорт)
    export_group,                # Резервное копирование (экспорт/импорт JSON)
]
```

`compute_group` в этот список **не входит** — она всегда видима.

**Шаг 4. Метод переключения режима.**

```python
def _set_ui_mode(self, mode: str) -> None:
    is_advanced = (mode == "advanced")
    for w in self._advanced_only_widgets:
        w.setVisible(is_advanced)

    self._btn_mode_simple.setChecked(not is_advanced)
    self._btn_mode_advanced.setChecked(is_advanced)
    self._restyle_mode_buttons()  # обновить визуальное выделение активной кнопки

    # Сохраняем выбор немедленно (аналогично мгновенному применению темы
    # в _on_theme_changed), чтобы режим не сбрасывался, если пользователь
    # закроет приложение не нажав "Сохранить".
    self._settings.settings_ui_mode = mode
    try:
        self._settings.save()
    except Exception as e:
        print(f"[SettingsPage] Не удалось сохранить режим настроек: {e}")

def _restyle_mode_buttons(self) -> None:
    t = theme_manager.tokens
    for btn, active in (
        (self._btn_mode_simple, self._btn_mode_simple.isChecked()),
        (self._btn_mode_advanced, self._btn_mode_advanced.isChecked()),
    ):
        if active:
            btn.setStyleSheet(f"background:{t['accent']}; color:{t['text_on_accent']}; border-radius:8px;")
        else:
            btn.setStyleSheet("")
```

**Шаг 5. Применить сохранённый режим при открытии страницы.**

В самом конце `__init__`, после `scroll.setWidget(content); outer.addWidget(scroll)`:

```python
self._set_ui_mode(self._settings.settings_ui_mode)
```

**Шаг 6. `_reset()`.** После сброса всех полей к `AppSettings()` по умолчанию
(в конце метода) добавить:

```python
self._set_ui_mode(defaults.settings_ui_mode)
```

**Шаг 7. Подсказка про экспорт моделей в Простом режиме (SHOULD).**

Поскольку кнопка «Экспортировать модели для CPU» и статус экспорта в Простом
режиме скрыты, а без экспорта выбор ONNX/OpenVINO в `_cpu_backend_combo`
молча откатывается на PyTorch (см. существующую логику в `_LazyModel._load()`
в `configs/sign_models.py`), нужно короткое предупреждение прямо рядом с
`compute_group`, чтобы пользователь Простого режима не терялся в догадках,
почему выбор бэкенда «ничего не меняет»:

```python
self._backend_hint_label = QLabel("")
self._backend_hint_label.setWordWrap(True)
self._backend_hint_label.setStyleSheet(
    f"color: {theme_manager.tokens['warning']}; font-size: 11px; background: transparent;"
)
compute_group.add_row("", "", self._backend_hint_label)

def _update_backend_hint():
    if self._cuda_toggle.is_checked():
        self._backend_hint_label.setText("")
        return
    idx = self._cpu_backend_combo.currentIndex()
    if idx == 0:  # PyTorch
        self._backend_hint_label.setText("")
        return
    backend_name = {1: "onnx", 2: "openvino"}[idx]
    if not self._is_backend_exported(backend_name):
        self._backend_hint_label.setText(
            f"⚠️ Модели ещё не экспортированы в {backend_name.upper()}. "
            f"Пока используется PyTorch. Экспорт — в Расширенном режиме "
            f"(«Диагностика системы» → «Экспорт моделей»)."
        )
    else:
        self._backend_hint_label.setText("")

self._cpu_backend_combo.currentIndexChanged.connect(lambda _: _update_backend_hint())
self._cuda_toggle.toggled_state.connect(lambda _: _update_backend_hint())
_update_backend_hint()
```

Вынеси проверку наличия экспортированных файлов в переиспользуемый метод
`_is_backend_exported(self, backend_name: str) -> bool`, использующий тот же
`glob`-паттерн, что уже есть внутри `_check_backend_readiness()` (не дублируй
логику копипастой — там и там нужен один и тот же список паттернов
`CNN_side/*.onnx`, `small_models/*.onnx`, `lane_guidance_models/*.onnx` и
аналогично для `*_openvino_model`).

**Шаг 8. НЕ менять поведение существующих методов.**

`_collect_settings()`, `_save()`, `_reset()` (кроме добавленного вызова
`_set_ui_mode` в конце), `_export_settings()`, `_import_settings()`,
`_check_backend_readiness()`, `_check_gpu()`, `_export_models()` должны
продолжать работать **идентично сегодняшнему поведению**, независимо от того,
в каком режиме сейчас находится UI — скрытые виджеты в Qt полностью
сохраняют своё состояние и доступны для чтения/записи (`.value()`,
`.currentIndex()`, `.is_checked()` и т.д.) даже когда `setVisible(False)`.
Никаких дополнительных `hasattr`-проверок для новых полей не требуется сверх
уже существующих в этих методах.

### B.4 Приёмочный чек-лист для Части B

- [ ] При первом запуске (нет сохранённых `QSettings`) страница «Настройки»
      открывается в Простом режиме: видны переключатель режима и ровно одна
      группа «Вычисления (CPU / GPU)» с тремя элементами.
- [ ] Переключение на «Расширенный режим» показывает все остальные группы,
      значения полей не сбрасываются.
- [ ] Переключение обратно на «Простой» скрывает расширенные группы, но их
      значения (например, введённый вручную шаг кадра) сохраняются в памяти
      и применяются при нажатии «Сохранить», даже если группа сейчас скрыта.
- [ ] Выбранный режим сохраняется между перезапусками приложения (проверить:
      переключиться на «Расширенный», закрыть приложение БЕЗ нажатия
      «Сохранить», открыть заново — должен открыться в «Расширенном»).
- [ ] Кнопка «Сбросить» возвращает режим к «Простой» вместе со всеми
      остальными настройками.
- [ ] Экспорт/импорт настроек в JSON продолжают работать одинаково в обоих
      режимах и включают поле `settings_ui_mode`.
- [ ] В Простом режиме при выборе ONNX/OpenVINO без экспортированных моделей
      появляется однострочная жёлтая подсказка; при выборе PyTorch или после
      включения CUDA подсказка исчезает.
- [ ] Ни один из существующих сценариев (`_check_gpu`, `_export_models`,
      `_check_backend_readiness`, диалог предупреждения при сохранении с
      неготовым бэкендом) не сломан.

---

## 5. Итоговый чек-лист готовности (Definition of Done)

- [ ] Все 4 бага из Части A исправлены, каждый — со своим regression-тестом,
      все тесты зелёные.
- [ ] Ручная проверка A.7 пройдена полностью.
- [ ] Часть B реализована и приёмочный чек-лист B.4 пройден полностью.
- [ ] `roadscan.log` после тестового прогона содержит понятную сквозную
      трассировку количества знаков на каждом этапе (см. A.5) — можно
      показать её как пруф в описании коммита/PR.
- [ ] Ни один из уже существующих тестов в `tests/` (не требующих реальных
      видео/тяжёлых ML-зависимостей) не стал падать после изменений.
- [ ] Никакие `print()` не добавлены там, где рядом уже используется
      `logging` — используется `logger.info/warning/error/exception`.
- [ ] Обновлён/добавлен файл документации по аналогии с уже существующими
      (например, `docs/CHANGELOG_PERFORMANCE.md`, `docs/BUGFIXES_2026-07-09.md`):
      кратко — что было сломано, что исправлено, как проверялось. Это не
      бюрократия, а единственный способ не повторить эти же баги в третий раз.

---

## 6. Что НЕ трогать (явно вне рамок этой задачи)

- Архитектуру `process_pool`/`pipeline` режимов обработки (кроме точечного SHOULD
  из A.2, шаг 7) — не переписывать `processing/detector_process_pool.py`.
- Логику геометрии (`core/osm_snap.py`, `core/intersection_geometry.py`,
  `core/coordinate_calculation.py`) — только добавляется валидация входных данных
  перед вызовом, сам алгоритм не менять.
- Дизайн-систему (`ui/themes/*`) — переиспользовать существующие токены,
  не вводить новые хардкод-цвета.
- `templates/map.html`, `server/map_server.py` — не связаны с этой задачей.
- Скиллы/форматы файлов (docx/pdf/pptx/xlsx) — не относятся к задаче.
- Существующие пороги confidence, дедупликации и т.п. — не менять их значения
  по умолчанию, задача не про качество детекции, а про целостность конвейера
  сохранения и про UX настроек.
