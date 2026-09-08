# Промпт для ИИ-агента: аудит и исправление проекта RoadScanner / Signer PRIME

> Скопируй весь этот файл в контекст ИИ-агента (Claude Code / Cursor / любой другой),
> который будет напрямую работать с репозиторием.

---

## РОЛЬ

Ты — senior Python/PyQt6 инженер. Твоя задача — провести ревизию и довести до
рабочего состояния проект **RoadScanner (Signer PRIME)**: desktop-приложение на
PyQt6 для распознавания дорожных знаков на видео с видеорегистратора, привязки
их к GPS-треку и экспорта в GeoJSON, со встроенной картой (Flask + Leaflet) и
редактором для проверки низкоуверенных распознаваний.

---

## ВАЖНЕЙШИЙ КОНТЕКСТ — ПРОЧИТАЙ ПЕРЕД НАЧАЛОМ РАБОТЫ

В репозитории лежит ~20 markdown-файлов (`CHANGELOG_*.md`, `BUGFIX_*.md`,
`FIX_*.md`, `CRITICAL_*.md`, `CURRENT_STATE.md`, `FINAL_SUMMARY.md`,
`SUMMARY_ALL_CONFIDENCE_FIXES.md` и т.д.), написанных предыдущим ИИ-агентом.
Они детально, убедительно и профессионально описывают десятки «исправленных»
багов: краши при загрузке GeoJSON, неправильный расчёт уверенности
распознавания, зависания при сохранении, проблемы с картой и т.д.

**Я построчно сверил актуальный код в репозитории с этими файлами и выяснил:
подавляющее большинство описанных там исправлений в реальности НЕ применено к
коду.** Либо агент писал документацию, не проверяя, попало ли изменение в
файл, либо изменения были потеряны/отменены без обновления документации.
Итог: документация и код разошлись, и **документации доверять нельзя**.

**Правило №1: игнорируй нарратив `.md`-файлов о том, «что уже пофикшено», и
проверяй реальное состояние кода самостоятельно** — чтением файлов, `grep`,
статическим анализом, запуском кода. Ни в коем случае не пиши новый
`.md`-changelog, декларирующий исправление, если ты не убедился, что оно
реально в коде и работает (см. Часть 5 — «Антипаттерны»).

---

## ЧТО Я ХОЧУ ПОЛУЧИТЬ НА ВЫХОДЕ

1. Рабочее, самосогласованное приложение без описанных ниже багов.
2. Единый правдивый документ `STATUS.md` (архитектура, что работает, что нет,
   известные ограничения), который заменит собой всю пачку исторических
   `.md`-файлов.
3. Исторические `.md`-файлы — перенести в `docs/archive/` с пометкой
   «историческая переписка ИИ-агента, может не соответствовать текущему коду»,
   либо удалить. Они не должны больше никого вводить в заблуждение.
4. Изменения — обычные git-коммиты с понятными сообщениями, а не очередной
   markdown-роман.

---

## ЧАСТЬ 1. ПОДТВЕРЖДЁННЫЕ КРИТИЧЕСКИЕ БАГИ (делать первыми)

### 1.1. `server/server_thread.py` — краш при запуске карты

```python
class ServerThread(QThread):
    def __init__(self, port: int = 3000, parent=None):
        super().__init__(parent)
        self.port = port
        self.setDaemon(True)   # <-- у QThread НЕТ метода setDaemon()!
```

`setDaemon()` — метод `threading.Thread`, а не `QThread`. Вызов упадёт с
`AttributeError` в момент создания `ServerThread`, то есть при первом же
нажатии «Начать обработку» (`MainWindow._on_start()` →
`self.page_map.start_server()`). Это, вероятно, и есть одна из первопричин
крашей, которые лечили переменными окружения в `main.py`.

**Исправление:** убрать `self.setDaemon(True)`. Корректное закрытие потока
обеспечивается через `MainWindow.closeEvent` (см. 1.4/4.4), а не через
daemon-флаг.

### 1.2. `processing/detector_thread.py` — `NameError: name 'Qt' is not defined` на каждом кадре

```python
class DetectorThread(QThread):
    ...
    def _emit_frame(self, image: np.ndarray) -> None:
        ...
        pixmap = QPixmap.fromImage(qimg).scaled(
            960, 540,
            aspectRatioMode=Qt.AspectRatioMode.KeepAspectRatio,  # type: ignore
        )
        self.frame_ready.emit(pixmap)
    ...
    # Нужен для _emit_frame
    from PyQt6.QtCore import Qt
```

Импорт `from PyQt6.QtCore import Qt` стоит в теле класса (не в `__init__`, не
на уровне модуля) — он создаёт **атрибут класса** `DetectorThread.Qt`, а НЕ
глобальное имя, видимое внутри методов. Python не ищет имена в пространстве
имён класса при разрешении переменных внутри методов (LEGB: Local → Enclosing
→ Global → Built-in — пространства класса там нет). Значит, `Qt` внутри
`_emit_frame` — неопределённое имя, и метод упадёт с `NameError` при первом же
вызове, то есть сразу после старта обработки видео.

**Исправление:** перенести `from PyQt6.QtCore import Qt` на уровень модуля,
рядом с `from PyQt6.QtCore import QThread, pyqtSignal`. Убрать импорт из тела
класса.

### 1.3. `core/turn.py` — файл содержит НЕ ТОТ класс

Открой `core/turn.py`. В нём находится **полная копия `core/gpx_handler.py`**
(класс `GPXHandler`), а не класс `Turn`, который используется по всему
проекту:

- `processing/detector_thread.py`: `from Turn import Turn`, `turn = Turn()`
- `core/sign_handler.py`: обращается к `turn.was_there_turn`, `turn.is_turn()`,
  `turn.signs`, `turn.coordinates`, `turn.azimuths`, `turn.frames`,
  `turn.add_points()`, `turn.set_direction_signs()`, `turn.handle_turn()`,
  `turn.clean()`
- `core/final_handler.py`: `self._calc.calculation_four_dots(turn)`
  использует `turn.coordinates`, `turn.azimuths`

Ни одного из этих атрибутов/методов в `GPXHandler` нет. **Вся логика
обработки знаков на поворотах гарантированно не работает** (падение с
`AttributeError`/`ImportError` при первом же повороте на маршруте).

**Исправление:** восстановить/написать класс `Turn` в `core/turn.py` с
интерфейсом:
- поля: `was_there_turn: bool`, `signs: list[TrackedSign]`,
  `coordinates: list[tuple[float, float]]`, `azimuths: list[float]`,
  `frames: list[int]`
- методы: `is_turn() -> bool`, `add_points()`, `set_direction_signs()`,
  `handle_turn()`, `clean()`

Сначала выполни `git log -p --all --full-history -- '*Turn*.py' '*turn*.py'`
— возможно, оригинальная реализация есть в истории и была случайно затёрта
содержимым `gpx_handler.py` при копипасте во время рефакторинга. Если в
истории её нет — восстанови по смыслу использования в `sign_handler.py`
(`_handle_turn_end`, `_separate_turn_signs`) и `final_handler.py`
(`_process_turn_signs`, `calculation_four_dots`), и явно пометь этот модуль
как «восстановлен по косвенным данным, требует ручной проверки на реальных
данных с поворотами».

### 1.4. Устаревшие импорты корневых модулей вместо пакета `core`

`processing/detector_thread.py`:
```python
from core.detector import Detector
from core.sign_handler import SignHandler
from GPXHandler import GPXHandler      # модуля GPXHandler.py в корне больше нет
...
from Turn import Turn                  # модуля Turn.py в корне больше нет
```

Это остатки дорефакторинговой плоской структуры (`GPXHandler.py`, `Turn.py`,
`Detector.py`, `FinalHandler.py` и т.п. в корне, упоминаемые в старых `.md`
как «оригинальный проект»). После переноса в `core/gpx_handler.py` и
`core/turn.py` эти импорты не обновили.

**Исправление:**
```python
from core.gpx_handler import GPXHandler
from core.turn import Turn
```
Проверь **весь репозиторий**:
```bash
grep -rn "^from [A-Z]" --include=*.py .
grep -rn "^import [A-Z]" --include=*.py .
```
и поправь все аналогичные «осиротевшие» импорты — это системная проблема
рефакторинга, не единичный случай.

### 1.5. `server/map_server.py` — некорректный `async_mode`

```python
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="processing")
```

`"processing"` не является допустимым значением `async_mode` для
`flask-socketio` (допустимые: `"threading"`, `"eventlet"`, `"gevent"`,
`"gevent_uwsgi"`, либо `None` для автоопределения). Поскольку Flask и так уже
выполняется в отдельном `QThread` (`server/server_thread.py`), правильное
значение — `"threading"`.

**Исправление:** `async_mode="threading"`.

---

## ЧАСТЬ 2. СЛОМАННЫЙ / «ОСИРОТЕВШИЙ» КОНВЕЙЕР УВЕРЕННОСТИ (confidence pipeline)

Это главная тема почти половины `.md`-файлов (`FIX_CNN_COUNT_CALCULATION.md`,
`FIX_GPS_CONFIDENCE.md`, `CRITICAL_UPDATE_CNN_COUNT.md`,
`REVERT_CNN_COUNT_TO_ORIGINAL.md`, `SUMMARY_ALL_CONFIDENCE_FIXES.md`,
`FIX_ZERO_CONFIDENCE.md`, `CHECK_CLASSIFICATION_WORKING.md` и др.) — и при этом
**ни одно из описанных там изменений фактически не присутствует в текущем
коде**. Проверь сам:

- **`core/sign.py`** — метод `calc_confidence()` полностью реализован
  (считает `conf_cnn`, `conf_placement`, `conf_total`, `snap_distance`,
  `azimuth_delta`), но **нигде в проекте не вызывается**. Мёртвый код.

- **`core/final_handler.py`** — метод `_build_feature()` формирует `props`
  для GeoJSON и НЕ содержит полей `cnn_count`, `observation_count`,
  `conf_cnn`, `conf_placement`, `conf_total`, хотя все `.md`-файлы утверждают
  обратное. `_snap_sign_coords()` вызывает `snap_sign(...)` из
  `core/osm_snap.py`, но использует только `result.azimuth`, отбрасывая
  `result.snapped` и расстояние до дороги — данные, необходимые для
  `calc_confidence()`, даже не собираются.

- **`ui/widgets/error_editor_page.py`** — `SignRecord._calc_confidence()`:
  ```python
  def _calc_confidence(self) -> float:
      raw = self.props.get("frame_numbers", "")
      total = len(self._parse_int_list(raw))
      ...
      length = int(self.props.get("length", total) or total)
      ...
      return min(1.0, length / max(total, 1))
  ```
  `length` — это `str(sign.observation_count)`, а `total` — тоже длина
  `frame_numbers`, которая **равна** `observation_count`. То есть
  `length / total` практически всегда ≈ 1.0. **Метрика не варьируется и
  бесполезна** — что прямо противоречит собственным критериям приёмки из
  `CURRENT_STATE.md` («должно быть разнообразие значений от 10% до 100%»).
  Полей `conf_cnn`/`conf_placement`/`conf_total` в `props` нет вообще (см.
  выше), значит и читать их неоткуда — код, «использующий готовое значение
  conf_cnn из GeoJSON» (как описано в `FIX_CNN_COUNT_CALCULATION.md`), в
  файле физически отсутствует.

- Атрибутов `gps_confidence` / `total_confidence` у `SignRecord` в текущем
  коде **нет вообще** — при этом UI (`SignItemDelegate.paint`) показывает
  только `rec.confidence`. Вся «GPS-уверенность» и «общая уверенность»,
  которым посвящено несколько `.md`-файлов, в UI никак не отображается.

### Что сделать (реализовать один раз, консистентно, с тестами):

1. В `core/osm_snap.py`: добавить в `SnapResult` поле `distance_m: float`,
   прокинуть реально вычисленное расстояние из `_find_closest_segment` наружу
   (сейчас `dist` считается внутри, но не возвращается).

2. В `core/final_handler.py._snap_sign_coords()`:
   - сохранить исходный (до перезаписи) азимут как `gpx_azimuth` до вызова
     snap;
   - после snap вызвать `sign.calc_confidence(snap_dist_m=result.distance_m
     if result.snapped else -1, osm_azimuth=result.azimuth if
     result.snapped else None, gpx_azimuth=gpx_azimuth)`.

3. В `_build_feature()` добавить в `props`:
   ```python
   "cnn_count":         str(sign.cnn_count),
   "observation_count": str(sign.observation_count),
   "conf_cnn":          f"{sign.conf_cnn:.3f}",
   "conf_placement":    f"{sign.conf_placement:.3f}",
   "conf_total":        f"{sign.conf_total:.3f}",
   "snap_distance":     f"{sign.snap_distance:.1f}",
   "azimuth_delta":     f"{sign.azimuth_delta:.1f}",
   ```

4. В `ui/widgets/error_editor_page.py::SignRecord.__init__`: читать
   `conf_cnn`/`conf_placement`/`conf_total` из `self.props` напрямую, с
   понятным fallback-расчётом для старых GeoJSON без этих полей (по формулам
   из `core/sign.py.calc_confidence`, НЕ по формуле `length/total`). Добавить
   атрибуты `self.gps_confidence` и `self.total_confidence`, использовать
   `total_confidence` для сортировки (`SignListModel.load`) и для фильтра
   «< 50%» (`_apply_filter`) вместо `confidence`.

5. В UI (`SignItemDelegate.paint` + панель деталей `_show_record`) — реально
   показать GPS-уверенность отдельной строкой/цветом, а не только CNN, раз уж
   это заявленная фича.

6. Определись с окончательной семантикой `cnn_count` в `core/sign.py`: сейчас
   там «стабильность CNN» (`most_common(cnn_results)[1]`, независимо от
   финального типа), без fallback на `yolo_results` при пустом
   `cnn_results`. Рекомендация: оставить «стабильность CNN» как основную
   семантику + fallback на `yolo_results`, если `cnn_results` пуст (как в
   `FIX_ZERO_CONFIDENCE.md`). Реализуй это **один раз, окончательно** — не
   продолжай цикл «исправили → откатили → снова исправили» без тестов,
   который явно виден в истории `.md`-файлов (`FIX_CNN_COUNT_CALCULATION.md`
   → `CRITICAL_UPDATE_CNN_COUNT.md` → `REVERT_CNN_COUNT_TO_ORIGINAL.md` →
   `FIX_ZERO_CONFIDENCE.md`).

7. Напиши `tests/test_confidence.py` на `TrackedSign.calc_confidence`,
   покрывающий: пустой `cnn_results`, стабильный CNN, нестабильный CNN,
   наличие/отсутствие snap. Это единственный надёжный способ прекратить цикл
   «чиню — ломаю — чиню» вокруг этой метрики.

---

## ЧАСТЬ 3. ДРУГИЕ РАСХОЖДЕНИЯ «ДОКУМЕНТАЦИЯ vs КОД»

Для каждой строки — проверь актуальность и либо реализуй по-настоящему, либо
явно реши, что фича не нужна, и вычеркни её из `STATUS.md`.

| Заявлено в `.md` | Реальность в коде | Что делать |
|---|---|---|
| `BUGFIX_GEOJSON_CRASH.md`: `__del__` в `ErrorEditorPage` заменён на явный `cleanup()` | В `ui/widgets/error_editor_page.py` всё ещё `def __del__(self): if self._cap: self._cap.release()` | Заменить на `cleanup()`, вызывать из `MainWindow.closeEvent` |
| `BUGFIX_GEOJSON_CRASH.md`: в `MainWindow` есть `closeEvent` | В `ui/main_window.py` метода `closeEvent` нет вообще | Добавить `closeEvent`: остановить `ProcessingController`, `ServerThread`, вызвать `page_errors.cleanup()` |
| `FIX_SAVING_HANG.md`: сохранение GeoJSON вынесено в `SaveThread` (QThread), UI не блокируется | `MainWindow._save_results()` вызывает `handler.save_result(...)` синхронно в главном потоке | Реализовать `SaveThread`, реально перенести сохранение в фон |
| `CHANGELOG_FINISH_BUTTON_FIX.md`: кнопка «Завершить» защищена от двойного клика, текст меняется на «⏳ Завершение…» | `ProcessingPage.btn_finish.clicked.connect(self.finish_requested)` — прямое подключение без защит | Реализовать защиту (актуально, т.к. после п. выше сохранение асинхронное — двойной клик реально может быть проблемой) |
| `CRASH_FIX_GEOJSON_BUTTON.md`: `/api/geojson_export` использует `normpath`/`abspath`, try/except | `server/map_server.py::api_geojson_export` — простой `send_file` без нормализации путей и без try/except | Добавить обработку ошибок вокруг чтения/отдачи файла |
| Несколько `.md`: подробное логирование в `/api/track`, `/api/signs` | Логов в коде нет | Добавить логирование через `logging`, а не `print` (см. Часть 5) |
| `RESTORE_NATIVE_FILE_DIALOG.md`: нативный диалог без `DontUseNativeDialog` | Проверь актуальный `ui/widgets/dashboard_page.py::FilePickerRow._pick()` | Свериться и привести к описанному поведению |
| Два разных `main.py`: простой vs с `os.environ`-workaround'ами (`KMP_DUPLICATE_LIB_OK`, `OMP_NUM_THREADS=1`, `QT_OPENGL=software`, `AA_ShareOpenGLContexts`) | Неясно, какой реально в репозитории | См. отдельный пункт ниже |

### Про `os.environ`-workaround'ы в `main.py`

Велика вероятность, что крашами `0xC0000409`, которые пытались лечить
переменными окружения (`QT_OPENGL=software`, `OMP_NUM_THREADS=1` и т.п.),
были **баги 1.1 и 1.2** (`AttributeError`/`NameError`), а не конфликт
Qt/OpenMP/WebEngine. План:

1. Сначала исправь баги из Части 1.
2. Собери и прогони приложение **без** `os.environ`-workaround'ов.
3. Если краш `0xC0000409` больше не воспроизводится — убери лишние
   workaround'ы, оставь только реально необходимые (если есть), с
   комментарием, зачем они нужны.
4. Если краш всё ещё воспроизводится — тогда это отдельная, реальная
   проблема; задокументируй чёткие шаги воспроизведения и продолжай
   диагностику (не бросай кучу переменных окружения «на всякий случай»).
5. В репозитории должен остаться **ровно один** `main.py`.

---

## ЧАСТЬ 4. ДУБЛИРОВАНИЕ И ИНФРАСТРУКТУРНЫЕ ПРОБЛЕМЫ

### 4.1. Три модуля загрузки моделей

- `configs/models.py` — **эагерная** загрузка YOLO/Keras моделей прямо при
  импорте.
- `configs/sign_models.py` — **ленивая** загрузка через
  `_LazyModel`/`_LazyKeras`/`_LazyJoblib` (специально, чтобы не грузить веса
  в главном потоке рядом с PyQt6/WebEngine — это и есть решение крашей на
  Windows, судя по комментарию в файле).
- `configs/sign_config.py` — реэкспортирует из `sign_data.py` и
  `sign_models.py` (ленивого варианта).

`configs/models.py` — судя по всему, устаревший файл от дорефакторинговой
версии. Если что-то ещё импортирует `configs.models`
(`grep -rn "from configs.models\|from configs import models"`), это сводит на
нет весь смысл ленивой загрузки и возвращает краши.

**Действие:** найти все использования `configs/models.py`, переключить на
`configs/sign_models.py` (через `configs/sign_config.py`), затем **удалить**
`configs/models.py`.

### 4.2. `.gitattributes` превращает `requirements.txt` в LFS-заглушку

```
*.pt filter=lfs diff=lfs merge=lfs -text
.txt filter=lfs diff=lfs merge=lfs -text
*.txt filter=lfs diff=lfs merge=lfs -text
```

Правило `*.txt filter=lfs` заставляет Git LFS трекать **любой** `.txt`-файл,
включая `requirements.txt`. В материалах, которые я анализировал,
`requirements.txt` буквально встречается в двух видах: один раз как реальный
список зависимостей, другой — как LFS pointer-заглушка (`version
https://git-lfs.github.com/spec/v1 ...`). Это значит, что у клонов без
настроенного `git lfs` команда `pip install -r requirements.txt`
**гарантированно упадёт**, потому что вместо списка пакетов там окажутся 3
строки LFS-метаданных.

**Действие:** убрать `*.txt`/`.txt` из `.gitattributes` (или сузить правило
до конкретных больших текстовых файлов, если такие реально нужны в LFS —
`requirements.txt`, `debug.txt` и подобные туда попадать не должны).
Перепроверить, что `requirements.txt` в репозитории сейчас — реальный
контент, а не LFS pointer; при необходимости — `git lfs migrate` /
перезакоммитить.

### 4.3. Дублирующийся ключ в справочнике имён знаков

`configs/sign_data.py::NAMES_SIGNS_BY_TYPE` содержит **два** определения
ключа `"3.27"`:
```python
"3.27": "Поворот налево запрещен",
...
"3.27": "Таможня",
```
В Python-словаре второе определение молча перезаписывает первое. Это баг
данных, и он может быть не единственным.

**Действие:** напиши скрипт, который парсит все словари в `sign_data.py`
(`CODES_SIGNS`, `NAMES_SIGNS_BY_TYPE`, `NAME_SIGNS_CNN`, `TYPE_SIGNS_YOLO`)
через `ast`-парсинг исходника (не через `exec`/`import`, чтобы поймать сами
дубли ключей ДО того, как Python их молча схлопнет), и печатает все
дублирующиеся ключи с обоими значениями. Исправь найденные конфликты вручную,
сверяясь с `signs.json` (там, судя по всему, более полный справочник — но и
его тоже проверь на дубли `_Key`/`_Code`).

### 4.4. `MapPage.stop_server()` не существует

`MainWindow` (в задокументированном варианте) вызывает
`self.page_map.stop_server()` через `hasattr`-guard — метод `stop_server` в
`MapPage` нигде не определён. Из-за `hasattr`-проверки исключения не будет,
но сервер Flask/SocketIO при закрытии приложения не остановится — поток
`ServerThread` останется висеть, мешая нормальному завершению процесса.

**Действие:** реализовать `MapPage.stop_server()`, останавливающий
`self._server_thread` (добавь механизм грациозной остановки в
`ServerThread`/`server/map_server.py` — флаг остановки + `QThread.quit()` /
`wait()` с таймаутом), и вызывать его из `MainWindow.closeEvent`.

---

## ЧАСТЬ 5. АНТИПАТТЕРНЫ, КОТОРЫЕ НУЖНО ПРЕКРАТИТЬ

По истории `.md`-файлов виден повторяющийся нездоровый паттерн: при любой
ошибке — обмотать код в `try/except: print(...)` и объявить проблему
решённой, вместо диагностики первопричины. Пожалуйста, не продолжай эту
традицию:

1. **Не используй `print()` для диагностики.** Используй модуль `logging` с
   именованными логгерами (`logging.getLogger(__name__)`), уровнями
   (`DEBUG`/`INFO`/`WARNING`/`ERROR`), единой конфигурацией в `main.py`. Это
   даст те же «детальные логи», что запрашивались в `.md`-файлах, но
   управляемо (можно включить/выключить, писать в файл, ротация).

2. **Не оборачивай широкие блоки в `except Exception: print(...); continue`**,
   если не понимаешь, какое именно исключение ожидаешь. Это маскирует
   реальные баги (как в этом проекте маскировало баги из Части 1). Лови
   конкретные исключения; непредвиденные — логируй через
   `logger.exception(...)` и осознанно решай, должна ли программа продолжать
   работу.

3. **Не добавляй `time.sleep`/таймауты как способ «прекратить зависание»**, не
   выяснив причину (O(n²)-алгоритм? deadlock? бесконечный цикл?). В этом
   репозитории `_deduplicate` в `final_handler.py` уже нормальный O(n) через
   пространственную сетку — 60-секундный таймаут из `FIX_SAVING_HANG.md`,
   к счастью, не понадобился/не был добавлен. Сохрани эту чистоту, не
   привноси таймаут обратно «на всякий случай».

4. **Не добавляй переменные окружения без диагностики** конкретной причины
   краша (см. разбор в конце Части 3).

5. **Не пиши «чейнджлог» вместо теста.** Каждое исправление в этой сессии
   должно сопровождаться либо (а) юнит/интеграционным тестом (`pytest`,
   папка `tests/`), либо (б) чётким воспроизводимым ручным сценарием
   проверки, который ты сам прогнал и получил ожидаемый результат — **до**
   того, как пометить пункт как исправленный.

---

## ЧАСТЬ 6. ПЛАН РАБОТЫ (по шагам)

1. **Аудит.** Пройтись по каждому `.md`-файлу в корне репозитория, для
   каждого заявленного изменения найти соответствующий код и явно определить
   статус: `ПРИМЕНЕНО` / `НЕ ПРИМЕНЕНО` / `ЧАСТИЧНО`. Свести в таблицу
   (черновик — Часть 3 этого промпта, но проверь предположения и дополни).
2. **Критические баги (Часть 1)** — исправить, вручную проверить, что
   приложение хотя бы запускается, обрабатывает видео и не падает на первом
   кадре / при старте карты.
3. **Импорты и структура (1.3, 1.4, 4.1)** — восстановить/переписать
   `core/turn.py`, поправить все «осиротевшие» импорты, удалить
   `configs/models.py`.
4. **Confidence pipeline (Часть 2)** — реализовать сквозной, консистентный
   расчёт и отображение уверенности, с тестами.
5. **Расхождения doc vs code (Часть 3)** — по каждой строке таблицы принять
   решение и реализовать.
6. **Инфраструктура (4.2–4.4)** — почистить `.gitattributes`, поправить дубли
   в `sign_data.py`/`signs.json`, реализовать `stop_server`.
7. **Логирование (Часть 5, п.1)** — заменить все `print()` на `logging` по
   всему проекту.
8. **Регрессионный прогон.** Запустить приложение целиком: Dashboard → выбор
   видео/GPX/GeoJSON → «Начать обработку» → дождаться нескольких кадров →
   «Завершить» → открыть карту → открыть редактор ошибок → отредактировать и
   сохранить знак → удалить знак → закрыть приложение штатно (проверить, что
   процесс завершается, а не висит).
9. **Документация.** Написать `STATUS.md` с реальным текущим состоянием,
   перенести/удалить исторические `.md`.
10. **Итоговый отчёт** — короткое резюме: что было сломано, что исправлено,
    что осталось под вопросом (например, если оригинал `Turn` не нашёлся в
    истории git и пришлось восстанавливать по смыслу — явно пометь это как
    «требует ручной проверки логики поворотов на реальных данных»).

---

## КРИТЕРИИ ПРИЁМКИ

- [ ] Приложение стартует без ошибок в консоли.
- [ ] Обработка видео проходит хотя бы 50 кадров без `NameError` /
      `AttributeError` / необработанных исключений в потоках.
- [ ] Карта (`/`, `/api/track`, `/api/signs`, `/api/sign/<id>` GET/PATCH/DELETE,
      `/api/geojson_export`) открывается и отвечает без 500.
- [ ] После обработки в GeoJSON присутствуют поля `cnn_count`,
      `observation_count`, `conf_cnn`, `conf_placement`, `conf_total`, и их
      значения **варьируются** между разными знаками (не все одинаковые).
- [ ] Редактор ошибок показывает разные уровни уверенности (не всегда
      ~50%/~100%), сортирует от низкой к высокой, цветовой индикатор
      соответствует реальным диапазонам.
- [ ] `pip install -r requirements.txt` работает из чистого клона репозитория
      **без** предварительного `git lfs pull` (файл — не LFS-заглушка).
- [ ] `grep -rn "^from [A-Z]\|^import [A-Z]"` не находит осиротевших импортов
      старых корневых модулей в `core/`, `processing/`, `ui/`, `server/`.
- [ ] Закрытие приложения (крестик окна) корректно останавливает все
      `QThread` (обработка, сервер карты) без зависания процесса.
- [ ] `pytest` (новые тесты на `calc_confidence` как минимум) — зелёный.
- [ ] В репозитории остался ровно один актуальный `main.py`.
- [ ] Нет ни одного `print()` в `core/`, `processing/`, `server/`, `ui/` —
      только `logging`.
