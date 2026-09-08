# Промпт для ИИ-агента: исправление краша при запуске обработки в режиме CPU (RoadScanner / Signer PRIME)

> Скопируй этот файл целиком в контекст ИИ-агента, работающего напрямую с
> репозиторием RoadScanner (Signer PRIME).

---

## РОЛЬ

Ты — senior Python/PyQt6 инженер. Твоя задача — найти и устранить причину
краша, который происходит при запуске обработки видео в CPU-режиме
(`processing_mode = "single_thread"` или `"pipeline"`, `use_cuda = False`,
либо просто на машине без CUDA). Не полагайся на нарратив в исторических
`.md`-файлах репозитория (`CPU_OPT_*.md`, `BUGFIX_*.md`, `CRASH_FIX_*.md`) —
они описывают предыдущие попытки исправлений, но, как показывает практика
этого проекта, документация в этом репозитории систематически расходится с
реальным состоянием кода. Проверяй код напрямую.

---

## ГЛАВНАЯ НАЙДЕННАЯ ПРИЧИНА: SyntaxError/IndentationError в `processing/detector_thread.py`

При статическом чтении файла `processing/detector_thread.py`, метод
`DetectorThread._process_loop()`, обнаружен явно испорченный блок кода —
похоже, результат неаккуратного мёрджа при добавлении счётчиков троттлинга
OCR (комментарии `# BLOCK CPU-4`). Блок отвечает за отправку знака на OCR и
инкремент статистики:

```python
                                # Отправляем в OCR Worker
                                self._submit_ocr_task(ocr_det_sign, raw.image)
                                
                                # Отмечаем, что OCR запрошен
                                tracked_sign.mark_ocr_requested(raw.abs_frame_number)
                                self._ocr_calls_total += 1  # BLOCK CPU-4: счётчик
                        else:
                            self._ocr_calls_skipped += 1  # BLOCK CPU-4: пропущено
                                self._ocr_calls_total += 1  # BLOCK CPU-4: счётчик
                        else:
                            self._ocr_calls_skipped += 1  # BLOCK CPU-4: пропущено

            # Финальные знаки → в очередь результатов
```

**Это гарантированный `IndentationError` / `SyntaxError`:**
- После строки `self._ocr_calls_skipped += 1` (простой statement, без
  двоеточия перед ним) идёт строка с **бо́льшим отступом**
  (`self._ocr_calls_total += 1`), что Python интерпретирует как
  «unexpected indent» — синтаксическая ошибка.
- Сразу после этого идёт **второй `else:`**, не имеющий пары `if` на своём
  уровне отступа (первый `if/else` уже был закрыт), что тоже ломает разбор
  файла.

**Почему это проявляется именно как «краш при выборе CPU»:**
`processing/detector_thread.py` импортируется лениво — только в момент
запуска обработки, в `ProcessingController._start_detector()`
(`from processing.detector_thread import DetectorThread` внутри
`DetectorThread.run()` / `processing_controller.py`). До этого момента
приложение стартует нормально, потому что модуль ещё не был импортирован.
Поэтому краш происходит не при старте приложения, а именно в момент нажатия
«Начать обработку» — то есть ровно тогда, когда пользователь выбрал
режим обработки (в том числе CPU-режим, который в тултипах настроек прямо
рекомендован: *«⚡ Для CPU всегда выбирайте 'Один поток'»*). Является ли
ошибка `SyntaxError` или тихо проглатывается — зависит от того, где именно
происходит импорт и обёрнут ли он в `try/except`; в `DetectorThread.run()`
есть `try/except Exception as e: self.error.emit(...)` вокруг блока с
`from core.detector import Detector` и импортами настроек — если импорт
`processing.detector_thread` происходит **до** входа в `run()` (то есть при
создании объекта `DetectorThread(...)` в главном потоке через
`from processing.detector_thread import DetectorThread`), исключение
`SyntaxError` вылетит **необработанным** в главном потоке UI — это и
похоже на «краш» с точки зрения пользователя (приложение падает без
дружелюбного сообщения об ошибке).

### Что нужно сделать

1. Открой `processing/detector_thread.py`, найди метод `_process_loop()`,
   раздел под комментарием `# BLOCK CPU-4: OCR Throttling на уровне TrackedSign`.
2. Убери дублирующийся, неправильно проиндентированный кусок. Корректная
   версия этого фрагмента должна выглядеть так (единственная пара if/else,
   без дублирования инкремента счётчика):

```python
            if self._use_pipeline and self._sign_handler.signs:
                for tracked_sign in self._sign_handler.signs:
                    # Проверяем нужен ли OCR для этого типа знака
                    if self._detector.needs_ocr(tracked_sign.best_cnn, tracked_sign.best_yolo):
                        # Проверяем троттлинг на уровне TrackedSign
                        if tracked_sign.should_run_ocr(raw.abs_frame_number):
                            # Отправляем в OCR Worker
                            # Нужен crop последнего наблюдения
                            if tracked_sign.pixel_x and tracked_sign.pixel_y:
                                last_x = tracked_sign.pixel_x[-1]
                                last_y = tracked_sign.pixel_y[-1]
                                last_w = tracked_sign.widths[-1]
                                last_h = tracked_sign.heights[-1]

                                # Вырезаем crop из текущего кадра
                                crop = raw.image[last_y:last_y+last_h, last_x:last_x+last_w]

                                # Создаём DetectedSign для OCR Worker (нужен для совместимости)
                                ocr_det_sign = DetectedSign(
                                    x=last_x, y=last_y, w=last_w, h=last_h,
                                    name_sign=tracked_sign.best_yolo,
                                    number_sign=tracked_sign.best_cnn,
                                    frame_number=raw.frame_number,
                                    absolute_frame_number=raw.abs_frame_number,
                                    latitude=0.0, longitude=0.0,  # не используется в OCR
                                    text_on_sign="",
                                    is_side=tracked_sign.side_results[-1] if tracked_sign.side_results else False
                                )

                                # Отправляем в OCR Worker
                                self._submit_ocr_task(ocr_det_sign, raw.image)

                                # Отмечаем, что OCR запрошен
                                tracked_sign.mark_ocr_requested(raw.abs_frame_number)
                                self._ocr_calls_total += 1  # BLOCK CPU-4: счётчик
                        else:
                            self._ocr_calls_skipped += 1  # BLOCK CPU-4: пропущено
```

   То есть удали именно эти четыре «лишние» строки (второй `self._ocr_calls_total += 1`
   со сбитым отступом и повторяющуюся пару `else: self._ocr_calls_skipped += 1`),
   сохранив только один `if tracked_sign.should_run_ocr(...): ... else: ...`.

3. После правки убедись, что файл валиден:
   ```bash
   python -m py_compile processing/detector_thread.py
   ```
   Команда не должна выдавать ошибок.

4. Прогони статическую проверку по **всему** проекту на случай, если
   аналогичный «мусор» от неаккуратного мёрджа остался и в других местах
   (особенно в файлах, упомянутых в `CPU_OPT_BLOCK_*.md` — они правились в
   несколько заходов):
   ```bash
   python -m py_compile $(git ls-files '*.py')
   ```
   Исправь все файлы, которые не проходят компиляцию, тем же способом —
   восстанови корректную структуру `if/else`, не удаляя функциональность
   (счётчики `_ocr_calls_total` / `_ocr_calls_skipped` нужны для лога
   троттлинга OCR, их нужно оставить работающими).

---

## ВТОРИЧНЫЕ ПРИЧИНЫ, КОТОРЫЕ СТОИТ ПРОВЕРИТЬ, ЕСЛИ КРАШ ОСТАЁТСЯ

Если после исправления синтаксиса краш всё ещё воспроизводится — это
отдельная, реальная проблема. Не гадай, а проверь по порядку:

### 1. Обёртка импорта моделей в необработанное исключение

`DetectorThread.run()` оборачивает загрузку моделей в `try/except`, но сам
факт `from processing.detector_thread import DetectorThread` (импорт всего
модуля) происходит **вне** этого `try/except`, в `processing_controller.py`
или `main_window.py`. Если модуль содержит синтаксическую ошибку (как в
пункте выше) или любая из строк верхнего уровня модуля (уровня класса, не
внутри метода) кидает исключение при импорте — приложение упадёт без
диалога об ошибке. Убедись, что:
- В `ui/main_window.py::_ensure_controller()` создание `ProcessingController`
  и последующий `controller.start()` тоже обёрнуты в try/except с выводом
  сообщения пользователю (сейчас там `self._controller.error.connect(...)`,
  но это сигнал, а не защита от исключений на этапе импорта/конструирования).
- При необходимости добавь try/except вокруг `self._controller.start()` в
  `MainWindow._on_start()` / `_on_multiple()`, чтобы любое исключение при
  запуске (включая ошибки импорта worker-модулей) показывалось пользователю
  через `QMessageBox`, а не ронялo процесс молча.

### 2. Конфликт OpenMP/MKL (исторический 0xC0000409)

В `main.py` установлены переменные окружения:
```python
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"
os.environ["MKL_THREADING_LAYER"] = "GNU"
os.environ["TBB_NUM_THREADS"] = "1"
os.environ["OPENCV_NUM_THREADS"] = "1"
os.environ["QT_OPENGL"] = "software"
```
и `torch.set_num_threads(1)` дополнительно вызывается в трёх местах:
`processing/detector_thread.py::run()`, `processing/detector_pool.py::DetectorWorker.run()`,
`processing/detector_process_pool.py::_worker_process_frame()`.

Если краш всё ещё воспроизводится на CPU **после** исправления синтаксиса —
проверь, не является ли он вариантом `STATUS_STACK_BUFFER_OVERRUN
(0xC0000409)`, задокументированным в `docs/CRASH_FIX_0xC0000409.md` и
`BUGFIX_GEOJSON_CRASH.md`. Это может проявляться именно на CPU-пути, потому
что CPU-инференс активнее грузит `torch`/`MKL`/`OpenCV`, которые все
одновременно живут в потоке `DetectorThread` рядом с Qt WebEngine. Если
краш воспроизводится стабильно и коррелирует с этим кодом ошибки —
собери минимальный репродюсер (короткое тестовое видео, `use_cuda=False`,
`processing_mode="single_thread"`) и приложи traceback/код ошибки Windows,
не добавляй новые `os.environ` workaround-ы «на всякий случай» без
диагностики (см. антипаттерны ниже).

### 3. `processing_mode="process_pool"` — известный незавершённый путь

`processing/processing_controller.py::_on_process_pool_frame()` **не
передаёт** детекции в `SignHandler` — данные просто прокидываются как
`ProcessedFrame` напрямую в `frame_ready`, без вызова
`sign_handler.check_the_data_to_add(...)`. Это не краш, а тихий баг
(пустой GeoJSON), но если пользователь выбирает "Process Pool" в
настройках как «CPU режим» — стоит либо диагностировать реальный краш там
отдельно (`ProcessPoolExecutor` + PyQt6 сигналы — частый источник проблем
на Windows из-за `multiprocessing.spawn`), либо временно заблокировать этот
пункт в UI с понятным сообщением, если он не является причиной репортнутого
краша.

### 4. Неверный `async_mode`/threading в `server/map_server.py`

Убедись, что `SocketIO(app, ..., async_mode="threading")` — это правильное
значение (см. `server/map_server.py`, ищи `async_mode=`). Если там что-то
иное — это отдельная причина краша при старте сервера карты, который
запускается сразу после старта обработки (`self.page_map.start_server()` в
`MainWindow._on_start()`), и может маскироваться под «краш при выборе CPU»,
если совпадает по времени.

---

## ЧТО НЕ ДЕЛАТЬ (антипаттерны, см. историю репозитория)

1. **Не оборачивай проблему в широкий `try/except: print(...)`**, не
   разобравшись в причине — в этом проекте уже была история, когда
   реальные баги (`AttributeError`, `NameError`, синтаксические ошибки)
   маскировались обёртками вместо исправления по существу
   (`prompts/PROMPT_FOR_AI_AGENT.md`, разделы 1 и 5).
2. **Не добавляй новые переменные окружения / workaround-ы** для
   `OMP_NUM_THREADS`/`torch.set_num_threads` без чёткой диагностики — в
   репозитории уже накопился слой таких «на всякий случай» настроек,
   некоторые из которых могли маскировать (а не решать) исходную причину
   первого краша (см. `prompts/PROMPT_FOR_AI_AGENT.md`, раздел
   «Про os.environ-workaround'ы в main.py»).
3. **Не пиши очередной `CRASH_FIX_*.md` с формулировкой «исправлено»**, не
   убедившись явным тестом (см. критерии приёмки ниже), что: (а) файл
   компилируется, (б) обработка видео в CPU-режиме реально стартует и
   доходит хотя бы до нескольких десятков кадров без исключений в
   консоли/логе `roadscan.log`.
4. Используй `logging`, а не `print()`, для любых новых диагностических
   сообщений, которые добавишь в процессе отладки (в этом файле уже
   используется `logger = logging.getLogger(__name__)` — следуй этому
   паттерну, `print()` в `processing/detector_thread.py` использовать не
   нужно, только в старых модулях типа `core/osm_snap.py`,
   `processing/processing_controller.py` он ещё остался как техдолг —
   не обязательно чинить всё сразу, но не добавляй новых `print()`).

---

## ПЛАН РАБОТЫ

1. Открой `processing/detector_thread.py`, локализуй и исправь
   испорченный блок `if tracked_sign.should_run_ocr(...) / else` внутри
   `_process_loop()` (см. точный diff выше).
2. `python -m py_compile processing/detector_thread.py` — должен пройти
   без ошибок.
3. `python -m py_compile $(git ls-files '*.py')` — прогони по всему
   репозиторию, исправь любые другие файлы с аналогичными артефактами
   мёрджа (в первую очередь смотри файлы, которые правились в рамках
   `CPU_OPT_BLOCK_*` серии: `core/detector.py`, `core/sign.py`,
   `core/sign_handler.py`, `processing/video_reader.py`,
   `configs/settings.py`).
4. Запусти приложение (`python main.py`), в настройках выставь
   `Использовать CUDA` = выключено (или просто работай на машине без
   GPU), `Режим обработки` = «Один поток».
5. На Dashboard укажи тестовое видео + GPX + путь для GeoJSON, нажми
   «Начать обработку».
6. Убедись, что:
   - приложение не крашится и не закрывается без сообщения;
   - в `roadscan.log` / консоли нет необработанных `Traceback`;
   - обработка реально идёт — счётчик кадров в UI растёт, лог
     `[SmartSkip] Обработано: ...` появляется;
   - если знаков в видео есть текстовые — после ~10-20 секунд в логе
     видно `OCR: N calls, M skipped (...)` без ошибок.
7. Повтори тот же прогон с `Режим обработки` = «Pipeline» (это тот путь,
   где непосредственно находился испорченный блок) — он тоже не должен
   крашиться.
8. Если в процессе диагностики обнаружится, что причина краша **не** в
   синтаксической ошибке (например, воспроизводится другой traceback) —
   задокументируй точный traceback/код ошибки Windows в отчёте и переходи
   к разделу «Вторичные причины» этого промпта, не выдумывая новых
   workaround-ов без понимания первопричины.
9. Напиши короткий, честный отчёт (не путать с historical `CRASH_FIX_*.md`
   стилем): что было сломано (точная строка/файл), что исправлено, каким
   тестом проверено. Не создавай новый `.md`-файл, если можно ограничиться
   сообщением/коммитом — в репозитории и так избыточно много исторических
   markdown-документов, которые не отражают реальное состояние кода.

---

## КРИТЕРИИ ПРИЁМКИ

- [ ] `python -m py_compile processing/detector_thread.py` завершается без ошибок.
- [ ] `python -m py_compile $(git ls-files '*.py')` завершается без ошибок для всего репозитория.
- [ ] Обработка видео с `use_cuda=False` и `processing_mode="single_thread"`
      запускается и обрабатывает минимум 100 кадров без необработанных
      исключений.
- [ ] Обработка видео с `use_cuda=False` и `processing_mode="pipeline"`
      запускается и обрабатывает минимум 100 кадров без необработанных
      исключений (это путь, где непосредственно был баг).
- [ ] В `roadscan.log` нет новых `Traceback (most recent call last)` записей
      после старта обработки, которых не было до правки.
- [ ] Если корневая причина оказалась не в синтаксисе, а в чём-то из
      «Вторичных причин» — эта причина явно определена (конкретный код
      ошибки/traceback), а не «исправлена» добавлением ещё одного
      `try/except` без понимания сути.
