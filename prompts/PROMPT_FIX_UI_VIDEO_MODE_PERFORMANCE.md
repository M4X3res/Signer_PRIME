# Промпт для ИИ-агента: UI-баги, видео на карте, упрощение режимов обработки, регресс CPU-производительности

## Контекст

Это RoadScanner — приложение на PyQt6 для детекции дорожных знаков из видео с GPS-треком.
Ниже — конкретный список проблем, обнаруженных пользователем (со скриншотами) и через анализ
кода. Для части багов ниже уже указана вероятная корневая причина (найдена по коду) — начни
именно с неё, не гадай заново. Для остальных — даны гипотезы и шаги диагностики.

**Работай по задачам последовательно, каждую задачу — отдельным коммитом.** После каждой задачи
запускай соответствующую проверку из раздела "Как проверить" ниже, прежде чем переходить к следующей.

---

## TL;DR — что уже установлено анализом кода (не нужно передоказывать)

1. **`/api/video_info/<idx>` возвращает не тот `frames_per_video_hint`.**
   В `server/map_server.py::api_video_info()` реально вычисляется `frame_count` конкретного
   видео через cv2, но в ответ уходит не он, а глобальная захардкоженная константа
   `config.FRAMES_PER_VIDEO` (дефолт 63600, "60fps × 60s × 17.67мин"):
   ```python
   frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
   ...
   return jsonify({
       ...
       "frames_per_video_hint": config.FRAMES_PER_VIDEO,  # <-- БАГ: должно быть frame_count
   })
   ```
   Это делает "фикс" BLOCK FIX-4.2 из `map.html` no-op'ом — если хотя бы одно видео в наборе
   отличается по длине/fps от дефолтной константы, расчёт `video_idx`/`frame_in_video` в
   `loadVideoForSign()` (map.html) окажется неверным.

2. **Та же логика (без вообще какого-либо фикса) продублирована минимум в 3 местах**, и везде
   использует ту же неверную константу вместо реальных длин видео:
   - `ui/widgets/error_editor_page.py::SignRecord.abs_frame_for_video()`
   - `ui/main_window.py::_on_jump_to_second()`
   - `core/final_handler.py::_build_feature()` (!) — это значит, что уже сейчас в сохранённый
     GeoJSON может писаться неверный `name_video`/`time` для знаков, если видео в наборе разной
     длины.

   Это прямая причина "чёрного кадра" в редакторе ошибок (Task C) и, вероятно, одна из причин
   "видео на карте не открывается" (Task D) — потому что секунда/видео вычисляются неверно ещё
   до похода к ffmpeg.

3. **Регресс производительности ONNX/OpenVINO почти наверняка вызван "паритетом потоков"
   (BLOCK CPU-5)** в `configs/inference_threading.py` + вызовом в `main.py`:
   ```python
   num_workers = settings.process_pool_workers if settings.processing_mode == "process_pool" else 1
   if num_workers <= 0:
       num_workers = max(1, (os.cpu_count() or 4) - 1)
   intra = settings.cpu_onnx_intra_threads or compute_safe_intra_threads(num_workers)
   ov_threads = settings.cpu_openvino_threads or intra
   apply_cpu_thread_limits(intra_threads=intra, ..., disable_cuda_providers=True)
   ```
   Ограничение PyTorch до 1 потока (`torch.set_num_threads(1)`, `OMP_NUM_THREADS=1`) — это обход
   **конкретного** краша 0xC0000409 (конфликт libiomp5md.dll с Qt на Windows, см.
   `docs/CRASH_FIX_0xC0000409.md`). ONNX Runtime и OpenVINO используют другие раннтаймы потоков
   и к этому крашу не имеют отношения. Насильно уравнивать их с PyTorch "для честности сравнения"
   было ошибкой — она не устраняет никакого риска, а просто режет реальную пропускную способность.
   Смотри Task F ниже для точного плана исправления.

---

## Task A — Попап QComboBox рендерится нечитаемым (чёрный фон, тёмный текст)

**Скриншот:** выпадающий список "Бэкенд CPU-инференса" в Settings появляется как чёрный
прямоугольник, смещённый в сторону от самого комбобокса, текст пунктов "ONNX Runtime" /
"OpenVINO" почти не читается (тёмный на чёрном), только выбранный пункт с подсветкой виден
нормально.

**Вероятная причина:** Windows OS-level dark mode переопределяет нативное окно попапа
`QComboBox` (это `Qt::Popup`-окно) на чёрный фон, при этом сам Qt рисует текст пунктов
стилями из **светлой** темы приложения (тёмный текст, рассчитанный на белый фон) — отсюда
почти невидимый текст. Подсвеченный (`selection-background-color`) пункт виден, потому что
его фон переопределяется явным QSS и "перебивает" системное окрашивание.

**Что сделать:**
1. В `main.py`, **до** создания `QApplication(sys.argv)`, попробовать:
   ```python
   from PyQt6.QtWidgets import QApplication
   QApplication.setStyle("Fusion")
   ```
   Fusion — программный (не нативный) стиль, полностью рисуется Qt и не подвержен подхвату
   OS dark-mode для попапов/менюшек. Это должно решить проблему сразу и для всех `QComboBox`
   в приложении (включая `_theme_combo`, `_frame_mode_combo`, `_filter_combo` в редакторе и т.д.),
   а не только для одного комбобокса.
2. Если `setStyle("Fusion")` даёт другие визуальные регрессии (не должен, но проверь), альтернатива —
   явно отключить интеграцию Windows dark-mode переменной окружения **до** импорта Qt:
   ```python
   os.environ["QT_QPA_PLATFORM"] = "windows:darkmode=0"
   ```
   Оба варианта можно применить одновременно как defense-in-depth.
3. После фикса — открыть Settings в **обеих** темах (светлой и тёмной) и проверить каждый
   `QComboBox` в проекте: `_theme_combo`, `_cpu_backend_combo`, `_frame_mode_combo` (Settings),
   `_filter_combo`, `_type_combo` (Error Editor). Убедиться, что попап рисуется прямо под/над
   виджетом (без "отлёта" в сторону) и текст читаем в обеих темах.
4. Если позиционирование попапа всё ещё странное после смены стиля — это отдельная, более редкая
   проблема; проверить нет ли где-то ручного `setGeometry()`/`move()` на `view()` комбобокса.

**Файлы:** `main.py`.

---

## Task B — Кнопка "Сохранить" в Settings почти невидима (низкий контраст)

**Скриншот:** кнопка "Сохранить" (`BtnPrimary`) выглядит как еле заметный серый текст без
видимого фона, в то время как "Сбросить" (`BtnSecondary`) читается нормально.

**Гипотезы (проверить обе, не выбирать вслепую):**

1. **Контраст disabled-состояния.** В `ui/themes/modern_styles.py`:
   ```css
   #BtnPrimary:disabled {
       background-color: {t['bg_elevated']};
       color: {t['text_disabled']};
   }
   ```
   В светлой теме (`ui/themes/modern_light.py`) `bg_elevated = "#FFFFFF"`, `text_disabled = "#B4AE9F"`.
   Это почти белый фон с бледно-бежевым текстом — очень низкий контраст. Если кнопка на скриншоте
   была в disabled-состоянии в момент захвата (например, во время 1.5-секундного окна после клика
   в `SettingsPage._save()`, где `sender.setEnabled(False)` на время показа "✓ Сохранено"), это
   объясняет баг напрямую.

   **Фикс:** сделать disabled-стиль `BtnPrimary` (и остальных кнопок) заметно контрастнее в обеих
   темах — например, использовать `bg_hover`/`border_default` с `text_tertiary` вместо
   `bg_elevated`+`text_disabled`, либо добавить видимую рамку в disabled-состоянии. Проверить
   визуально в обеих темах (контраст текст/фон должен быть отчётливо читаемым, не "призрачным").

2. **Кнопка "залипла" в disabled без явной причины** (баг логики, а не только стиля). Проверить,
   нет ли пути в `SettingsPage`, где `save_btn`/кнопка остаётся `setEnabled(False)` дольше, чем
   задумано (например, исключение внутри `_check_backend_readiness()` до восстановления состояния
   кнопки, либо гонка с `QTimer.singleShot(1500, restore)` если пользователь быстро кликает ещё раз).
   Добавить try/finally вокруг восстановления enabled-состояния кнопки в `_save()`, чтобы кнопка
   гарантированно возвращалась в активное состояние при любом исходе (включая исключение).

**Файлы:** `ui/themes/modern_styles.py`, `ui/themes/modern_light.py`, `ui/themes/modern_dark.py`,
`ui/widgets/settings_page.py::_save()`.

---

## Task C — Чёрный кадр без данных в редакторе ошибок / панель метаданных пустая

**Скриншоты:** панель "КАДР" в Error Editor — сплошной чёрный прямоугольник без текста и без
bbox; панель метаданных показывает "НАЗВАНИЕ —", "ВРЕМЯ / ВИДЕО —", "СТОРОНА —" (заглушки).

**Корневая причина №1 (см. TL;DR п.1-2) — исправить в первую очередь:**

Добавить единую, корректную функцию преобразования "средний абсолютный номер кадра → (video_idx,
frame_in_video)", основанную на **реальных** длинах видеофайлов, а не на константе
`config.FRAMES_PER_VIDEO`.

1. В `configs/config.py` добавить кэш реальных длин видео:
   ```python
   VIDEO_FRAME_COUNTS: list[int] = []  # заполняется лениво по мере открытия файлов
   ```
2. Добавить утилиту (например, в новый `core/video_index.py` или в `utils.py`):
   ```python
   def resolve_video_and_frame(abs_frame: int) -> tuple[int, int]:
       """
       Корректно определяет (video_idx, frame_in_video) по абсолютному номеру кадра,
       используя РЕАЛЬНЫЕ длины видеофайлов (config.VIDEO_FRAME_COUNTS), а не
       config.FRAMES_PER_VIDEO. Заполняет VIDEO_FRAME_COUNTS лениво через cv2, если пусто.
       """
   ```
   Логика: если `config.VIDEO_FRAME_COUNTS` пуст или короче `config.VIDEOS` — досчитать
   недостающие длины через `cv2.VideoCapture(...).get(cv2.CAP_PROP_FRAME_COUNT)` и закэшировать.
   Затем пройти по кумулятивным суммам, найти видео, в которое попадает `abs_frame`, вернуть
   `(video_idx, abs_frame - cumulative_before_this_video)`.
3. Использовать эту функцию везде, где сейчас `// config.FRAMES_PER_VIDEO` и
   `% config.FRAMES_PER_VIDEO`:
   - `ui/widgets/error_editor_page.py::SignRecord.abs_frame_for_video()`
   - `ui/main_window.py::_on_jump_to_second()`
   - `core/final_handler.py::_build_feature()` (важно: это меняет то, что пишется в GeoJSON —
     проверить регрессию на тестовом видео до/после)
   - `server/map_server.py::api_video_info()` — заменить `frames_per_video_hint` на реальный
     `frame_count` **этого конкретного видео** (или ещё лучше — добавить новый эндпоинт
     `/api/resolve_frame?abs_frame=N`, который сразу отдаёт `{video_idx, frame_in_video}`,
     вычисленные на сервере той же функцией `resolve_video_and_frame`, и переписать
     `map.html::loadVideoForSign()` на использование этого эндпоинта вместо клиентского деления).

**Корневая причина №2 — отсутствие диагностики при сбое.**

Даже после фикса №1, `error_editor_page.py::_load_frame()` должен **никогда** не оставлять
чёрный `QLabel` без текста молча:
- Если `cv2.VideoCapture` не открылся — уже есть `setText("Не удалось открыть видео")` (ок).
- Если `cap.read()` вернул кадр успешно, но кадр реально почти чёрный (например, попали на
  чёрную заглушку/переход) — добавить проверку среднего яркости кадра (`frame.mean() < 5`) и
  в этом случае дополнительно вывести небольшой оверлей-текст поверх картинки (например,
  "⚠ Кадр выглядит пустым — возможно неверный индекс") — это не баг сам по себе, но полезная
  диагностика на будущее.

**Проверить также:** почему панель метаданных показывает одни прочерки — это нормальное
начальное состояние `ErrorEditorPage` **до** выбора записи (`self._lbl_name = self._meta_val("—")`
и т.д. в конструкторе). Убедиться, что `reload()`/`load_geojson()` после завершения обработки
реально находит `config.PATH_TO_GEOJSON` и загружает записи (проверить логи "[ErrorEditor] Найдено
N features"). Если список пуст — это баг в другом месте (например, GeoJSON не сохранился, или
путь не совпадает), не в самой панели.

**Файлы:** `configs/config.py`, `core/video_index.py` (новый), `ui/widgets/error_editor_page.py`,
`ui/main_window.py`, `core/final_handler.py`, `server/map_server.py`, `templates/map.html`.

---

## Task D — Видео знака на карте не открывается

**Текущая реализация** (`templates/map.html::loadVideoForSign()` + `server/map_server.py::api_video_clip()`):
при клике на знак фронтенд запрашивает `${API}/video_clip/${videoIdx}?start=0&duration=0`, что
означает **"перекодировать ВСЁ видео целиком"** в WebM (VP9/Opus) через ffmpeg, с фронтенд-таймаутом
ожидания метаданных **10 секунд**.

**Корневая причина:** полное дашкам-видео (может быть 15-20+ минут в 1080p/60fps) кодируется в
VP9 **гораздо** медленнее реального времени на CPU. За 10 секунд транскод почти никогда не
успевает — фронтенд получает таймаут и падает в ошибку ещё до того, как ffmpeg вообще закончил
писать файл. Это и есть причина "видео не открывается".

(Отдельно: MP4/H.264 отдаётся напрямую без транскода не подойдёт как основной путь — судя по
наличию `testVideoCodec()` в проекте и самому факту, что команда уже сделала транскод в WebM,
скорее всего используемая сборка QtWebEngine (Chromium) не включает проприетарные кодеки H.264/AAC,
поэтому исходный MP4 в `<video>` внутри QWebEngineView может не воспроизводиться вообще. Транскод
в VP9/Opus остаётся нужным — но не для всего файла целиком.)

**План исправления:**

1. В `map.html::loadVideoForSign()` перестать запрашивать `start=0&duration=0` (весь файл).
   Вместо этого вычислять окно вокруг момента знака, например:
   ```js
   const clipBuffer = 8; // секунд запаса до/после
   const clipStart = Math.max(0, secondsInVideo - clipBuffer);
   const clipDuration = clipBuffer * 2; // ~16 секунд клипа
   const videoSrc = `${API}/video_clip/${videoIdx}?start=${clipStart}&duration=${clipDuration}`;
   ```
   и после загрузки метаданных ставить `video.currentTime = secondsInVideo - clipStart` (а не
   `secondsInVideo` от начала клипа).
2. В `server/map_server.py::api_video_clip()` ускорить кодирование короткого клипа:
   добавить `-deadline realtime -cpu-used 8` к параметрам `ffmpeg` для VP9 (сильно быстрее при
   приемлемом качестве для превью), и убедиться что `-ss` стоит **до** `-i` (уже так — быстрый
   seek по ключевым кадрам, ок).
3. Увеличить фронтенд-таймаут ожидания `loadedmetadata` с 10 до 25-30 секунд (короткий клип с
   `-deadline realtime` должен укладываться в это время с большим запасом), и показывать
   пользователю статус-текст на время ожидания (например, в `#video-status`:
   "Подготовка видео… это может занять несколько секунд"), а не молчаливое ожидание.
4. Имя кэш-файла уже включает `start`/`duration` (`_clip_{start}_{duration}.webm`) — с этим
   изменением кэш будет из коротких клипов, что нормально (клипы для одного и того же знака будут
   переиспользоваться при повторном клике).
5. Применить фикс из Task C (корректный `video_idx`/`secondsInVideo`) **до** тестирования этой
   задачи — иначе можно чинить транскод для заведомо неверного видео/времени.
6. Убедиться, что путь `video_idx` действительно валиден (`config.VIDEOS[video_idx]` существует)
   до вызова ffmpeg — сейчас так и есть, но перепроверить после фикса Task C.

**Файлы:** `templates/map.html`, `server/map_server.py`.

---

## Task E — Убрать выбор режима обработки (Один поток / Pipeline / Process Pool)

Обоснование уже задокументировано в самом проекте (`WHY_SINGLE_THREAD_FASTER.md`,
`docs/BUGFIXES_2026-07-09.md`): на CPU "Один поток" стабильно быстрее, Pipeline и Process Pool
дают только оверхед. Задача — убрать выбор из UI и всегда работать в режиме single_thread,
**минимально рискованным способом** (не удалять целиком код Process Pool/Pipeline в этом заходе,
чтобы не сломать что-то незаметно — только перестать его использовать и показывать в UI).

**Что сделать:**

1. **`ui/widgets/settings_page.py`:**
   - Полностью удалить группу `mode_group` ("Режим обработки"): `_processing_mode_combo` и весь
     её `add_row(...)` блок с тултипом.
   - Полностью удалить группу `mt_group` ("Многопоточность (дополнительные параметры)"):
     `_workers_spin`, `_ocr_use_pool_toggle`, `_ocr_workers_spin` и их `add_row(...)`.
   - Убрать из `_advanced_only_widgets` ссылки на `mt_group` (mode_group и так не добавлялась
     туда — она "всегда видна"; проверить, что после удаления группы ничего не падает).
   - В `_collect_settings()` удалить блок:
     ```python
     mode_idx = self._processing_mode_combo.currentIndex()
     mode_map = ["single_thread", "pipeline", "process_pool"]
     self._settings.processing_mode = mode_map[mode_idx]
     self._settings.process_pool_workers = self._workers_spin.value()
     ```
     и OCR-pool-related блок (`_ocr_use_pool_toggle`, `_ocr_workers_spin`).
   - Аналогично убрать соответствующие куски в `_reset()` и `_import_settings()`
     (`hasattr(self, '_processing_mode_combo')`, `hasattr(self, '_workers_spin')`,
     `hasattr(self, '_ocr_use_pool_toggle')`, `hasattr(self, '_ocr_workers_spin')`).
   - `_cpu_backend_combo` ("Бэкенд CPU-инференса": PyTorch/ONNX/OpenVINO) — **не трогать**, это
     другая настройка (про инференс-бэкенд, а не про архитектуру потоков), пользователь просил
     убрать именно выбор архитектуры обработки.

2. **`processing/processing_controller.py::start()`:** упростить ветвление —
   всегда вызывать `self._start_detector()`, убрать проверку `config.PROCESSING_MODE ==
   "process_pool"` и вызов `_start_process_pool()`. Строку
   ```python
   config.PROCESSING_MODE = settings.processing_mode
   ```
   заменить на:
   ```python
   config.PROCESSING_MODE = "single_thread"  # Task E: выбор режима убран из UI, всегда single_thread
   ```

3. **`processing/detector_thread.py::run()`:** убрать ветвление `self._use_pipeline`:
   - `self._use_pipeline = settings.processing_mode == "pipeline"` заменить на
     `self._use_pipeline = False` с комментарием, что pipeline-режим больше не выбирается из UI.
   - Оставить только "else"-ветку (прогрев EasyOCR, синхронный OCR), удалить ветку с
     `OCRPool`/`OCRWorkerThread` запуском (или оставить код недостижимым за явным `if False:` —
     предпочтительно просто удалить ветку и связанные импорты, раз она гарантированно не
     используется).
   - В `_process_single_frame()` убрать блок, отправляющий задачи в `self._ocr_worker` (он
     завязан на `self._use_pipeline`, станет мёртвым кодом) — можно оставить методы
     `_submit_ocr_task`/`_on_ocr_result`/`_on_ocr_result_pool` неиспользуемыми на первое время,
     либо удалить, если уверен что тесты не завязаны на них.

4. **`configs/settings.py`:** поля `processing_mode`, `process_pool_workers`,
   `ocr_use_process_pool`, `ocr_pool_workers` — **оставить в датаклассе** (для обратной
   совместимости чтения старых сохранённых `QSettings`, чтобы `AppSettings.load()` не падал на
   старых профилях), но добавить комментарий `# DEPRECATED (Task E): UI-выбор убран, всегда
   single_thread; поле оставлено только для совместимости десериализации`.

5. **Не удалять** файлы `processing/detector_process_pool.py`, `processing/ocr_pool.py`,
   `processing/ocr_worker.py` в этом заходе — они станут недостижимым кодом, но их полное
   удаление — отдельная, более рискованная задача (нужно сначала убедиться, что тесты
   `tests/test_reorder_buffer.py` и `test_coordinates.py`, ссылающиеся на
   `detector_process_pool.py`, не нужны/будут тоже удалены осознанно). Оставь TODO-комментарий
   в начале `detector_process_pool.py`: `# DEPRECATED (Task E): больше не вызывается из
   ProcessingController. Кандидат на удаление в отдельном PR.`

**Файлы:** `ui/widgets/settings_page.py`, `processing/processing_controller.py`,
`processing/detector_thread.py`, `configs/settings.py`.

---

## Task F — Регресс производительности CPU ONNX/OpenVINO

Смотри TL;DR п.3 выше для диагноза. Здесь — конкретный план.

1. Открыть `configs/inference_threading.py` полностью, найти `compute_safe_intra_threads()` и
   `apply_cpu_thread_limits()`. Понять, что именно возвращает `compute_safe_intra_threads(1)` —
   это ключевой вызов теперь, когда Task E гарантирует, что `num_workers` в проде всегда `1`
   (Process Pool больше не выбирается).

2. Требуемое поведение для `num_workers == 1` (единственный оставшийся сценарий после Task E):
   - `intra_threads` (ONNX `intra_op_num_threads`) должен быть `max(1, os.cpu_count() - 1)`
     (оставляем одно ядро под GUI/чтение видео), **а не** число, посчитанное исходя из "деления
     поровну между несколькими воркерами" или "паритета с PyTorch".
   - `openvino_threads` (аналог `INFERENCE_NUM_THREADS`) — аналогично, `max(1, os.cpu_count() - 1)`.
   - Единственное, что нужно реально сохранить из BLOCK CPU-5 — `disable_cuda_providers=True`
     (это безопасно и не влияет на скорость на CPU, просто гарантирует, что ONNX/OpenVINO не
     пытаются достучаться до CUDA-провайдера когда CUDA выключена).

3. Обнови вызов в `main.py`:
   ```python
   num_workers = 1  # после Task E process_pool больше не существует как выбор
   intra = settings.cpu_onnx_intra_threads or compute_safe_intra_threads(num_workers)
   ```
   — либо исправь саму `compute_safe_intra_threads(1)` так, чтобы она возвращала
   `cpu_count() - 1`, либо (если функция используется где-то ещё с иной семантикой) добавь
   отдельную ветку/константу специально для `num_workers == 1`, не трогая сигнатуру функции
   ради других вызывающих (проверь `processing/detector_process_pool.py::_worker_process_frame`
   — он тоже вызывает `compute_safe_intra_threads`, но после Task E этот путь не должен
   исполняться в проде; тем не менее не должен и падать, если случайно вызван).

4. **Обязательно бенчмарк до/после**, не полагаться только на рассуждения:
   ```bash
   python scripts/benchmark_detector.py --video <test.mp4> --frames 150 --force-cpu --backend onnx
   python scripts/benchmark_detector.py --video <test.mp4> --frames 150 --force-cpu --backend openvino
   ```
   Сравнить FPS до и после изменения. Целевой результат: заметное (не в пределах погрешности)
   увеличение FPS относительно текущего (регрессировавшего) состояния. Если прироста нет —
   не выдавать желаемое за действительное: тогда переходи к пункту 5.

5. **План Б, если увеличение потоков не помогает** (правдоподобно — детектор гоняет много
   *маленьких* классификаций 32×32 по одному кропу за раз, и intra-op параллелизм на таких
   крошечных операциях иногда не даёт выигрыша или даже вредит из-за оверхеда синхронизации
   потоков на каждый вызов, см. по аналогии `docs/BATCHING_FAILURE_ANALYSIS.md` — там похожая
   ловушка с батчингом на CPU): в этом случае лучше **полностью откатить** явное управление
   потоками ONNX/OpenVINO (не звать `intra_op_num_threads`/`INFERENCE_NUM_THREADS` вообще,
   оставить дефолтные настройки раннтайма как было до BLOCK CPU-5), сохранив только
   `disable_cuda_providers`. Дефолтные настройки ORT/OpenVINO почти всегда сами разумно
   определяют число потоков под доступные ядра — не нужно указывать что-то более "умное" без
   измеренного выигрыша.

6. Дополнительно (не блокирующая, но дешёвая проверка): в `main.py` глобально стоит
   `os.environ["OPENCV_NUM_THREADS"] = "1"`. Так как `core/detector.py` очень часто вызывает
   `cv2.resize`/`cv2.dct`/`cv2.cvtColor` на каждый кроп (в т.ч. для perceptual-hash кэша),
   стоит попробовать временно снять это ограничение (`OPENCV_NUM_THREADS` не задавать, или
   поставить `os.cpu_count()`) и прогнать тот же бенчмарк — если даст прирост без побочных
   эффектов (эта переменная не связана с крашем 0xC0000409, который специфичен для
   libiomp5md.dll/PyTorch/MKL), оставить снятым.

**Файлы:** `configs/inference_threading.py`, `main.py`, (опционально)
`processing/detector_process_pool.py`.

---

## Как проверить каждую задачу (definition of done)

- **Task A:** открыть Settings в светлой и тёмной теме, раскрыть каждый комбобокс — попап
  читаем, фон соответствует текущей теме, позиционирование адекватное.
- **Task B:** визуально сравнить кнопки "Сохранить"/"Сбросить" в обычном и disabled состоянии в
  обеих темах — обе всегда явно читаемы; кнопка "Сохранить" гарантированно возвращается в
  активное состояние после сохранения (в том числе если сохранение упало с исключением).
- **Task C:** открыть Error Editor на реальном GeoJSON с как минимум двумя видео **разной**
  длины/fps в наборе — для знаков из второго видео кадр должен показывать реально
  соответствующий момент (сверить вручную по VLC/аналогично), а не чёрный экран/не тот кадр.
- **Task D:** кликнуть на знак на карте — видео должно начать грузиться и воспроизводиться в
  пределах ~20-30 секунд, с корректной перемоткой на момент знака.
- **Task E:** в Settings нет ни группы "Режим обработки", ни группы "Многопоточность
  (дополнительные параметры)". Обработка видео запускается и работает (через single_thread путь)
  без ошибок про отсутствующие атрибуты (`_processing_mode_combo` и т.д. нигде не
  используются).
- **Task F:** `scripts/benchmark_detector.py --force-cpu --backend onnx` и `--backend openvino`
  показывают FPS заметно выше, чем до изменений (запиши числа до/после в `docs/PROFILING_RESULTS.md`
  или аналогичный файл — в проекте уже есть традиция фиксировать такие бенчмарки).

## Чего НЕ делать

- Не пытайся повторно вводить батчинг CNN-классификации на CPU — это уже было опробовано и
  привело к регрессии на 30%, см. `docs/BATCHING_FAILURE_ANALYSIS.md`. Не наступай на те же грабли
  под видом "оптимизации потоков".
- Не удаляй `processing/detector_process_pool.py` / `ocr_pool.py` / `ocr_worker.py` в рамках этой
  задачи — только отключи их вызов (Task E, п.5).
- Не трогай `_cpu_backend_combo` (выбор PyTorch/ONNX/OpenVINO) — пользователь просил убрать
  только выбор *архитектуры обработки* (потоки/процессы), а не выбор *инференс-бэкенда*.
- Не меняй пороги confidence/dedup/IoU — это не относится к текущему заданию.
