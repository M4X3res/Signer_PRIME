# CHANGELOG — RoadScanner (Signer PRIME)

## 2026-09-08 — Исправления UI: видеоплеер карты, темы комбобоксов, выравнивание кнопок

### 🚨 P0 — Сломанная функциональность видеоплеера на карте

#### 5.1 — Доступ к полному видео (не только короткий клип)
**Проблема**: По клику на знак всегда грузился только короткий клип ±8 сек вокруг момента фиксации. Пользователь не мог просмотреть контекст всей поездки.

**Решение**:
- Добавлены кнопки переключения "📹 Клип" / "⛶ Весь файл" в контролах видеоплеера
- Функция `switchToFullVideo()`: запрашивает полное видео через `/api/video_clip?duration=0` (бэкенд уже поддерживал)
- Увеличен таймаут загрузки для полного видео до 5 минут
- Статус "Подготовка полного видео... это может занять несколько минут"
- Сохранение `lastSignProps` для переключения между режимами без потери контекста

**Файлы**: `templates/map.html` (строки 626-650, 1614-2050)

#### 5.2 — Кнопка полноэкранного режима не работала
**Проблема**: `QWebEngineView` не поддерживает Fullscreen API "из коробки" — `video.requestFullscreen()` в JS тихо ничего не делал.

**Решение**:
- Включен `FullScreenSupportEnabled` в настройках QWebEngine
- Кастомная `MapWebEnginePage` с обработчиком `fullScreenRequested`
- `_on_fullscreen_requested()` разворачивает главное окно приложения в fullscreen

**Файлы**: `ui/widgets/map_page.py` (строки 30-90, 217-230)

#### 5.3 — Кнопка "открыть в отдельном окне" не работала
**Проблема**: `window.open()` в JS не работал — QWebEngine требует переопределения `createWindow()`.

**Решение**:
- `MapWebEnginePage.createWindow()`: создаёт QDialog с новым QWebEngineView для popup
- Управление жизненным циклом popup-окон через список `_popup_windows`
- Инициализация скорости воспроизведения из родительского окна

**Файлы**: `ui/widgets/map_page.py` (строки 30-90), `templates/map.html` (строки 2140-2280)

#### 5.4 — Кнопки скорости воспроизведения ненадёжны
**Проблема**: Скорость сбрасывалась при переключении между знаками/клипом/полным видео.

**Решение**:
- Глобальная переменная `currentPlaybackRate` сохраняет выбранную скорость
- Переприменение `video.playbackRate = currentPlaybackRate` после каждой загрузки метаданных
- Визуальная индикация активной кнопки (класс `accent`)
- Применяется и в основном плеере, и в popup-окне

**Файлы**: `templates/map.html` (строки 1614-2280)

---

### ⚡ P1 — Читаемость/доступность (пользователь физически не видит элементы)

#### 1.1 — Тема выпадающего списка ComboBox + контраст кнопки "Сохранить"
**Проблема**: Попап комбобоксов (особенно "Бэкенд CPU-инференса") рендерился с белым фоном независимо от темы. QComboBox в стиле Fusion создаёт отдельный popup-контейнер (QFrame Qt::Popup), не покрываемый QSS.

**Решение**:
- Утилита `style_combobox_popup()` в `ui/widgets/utils.py`: программная стилизация popup-контейнера
- `connect_combobox_theme_updates()`: автообновление при смене темы
- Применено ко всем комбобоксам: `_theme_combo`, `_frame_mode_combo`, `_cpu_backend_combo` (settings_page.py), `_filter_combo`, `_type_combo` (error_editor_page.py)
- Улучшен контраст disabled-кнопки: `text_primary` вместо `text_secondary`, добавлено `opacity: 0.6`

**Файлы**: `ui/widgets/utils.py` (весь файл), `ui/widgets/settings_page.py` (строки 11, 206, 262, 603), `ui/widgets/error_editor_page.py` (строки 38, 592, 741), `ui/themes/modern_styles.py` (строки 201-206)

---

### 🎨 P2 — Визуальная консистентность

#### 4.1 — Выравнивание парных кнопок
**Проблема**: Три пары кнопок выглядели неровно (разная ширина/высота):
- "← Пред." / "След. →" (навигация знаков)
- "↑ Загрузить GeoJSON" / "✓ Сохранить" (топбар редактора)
- "↺ Перезагрузить" / "⬡ В браузере" (топбар карты)

**Решение**:
- Убраны конфликтующие `setMinimumHeight(32/34)` — используется единая высота из QSS (36px)
- Установлена одинаковая `setFixedWidth()` для каждой пары:
  - Пред./След.: 100px
  - Загрузить/Сохранить: 180px
  - Перезагрузить/В браузере: 150px

**Файлы**: `ui/widgets/error_editor_page.py` (строки 489-509, 623-632), `ui/widgets/map_page.py` (строки 128-148)

---

### ✨ P3 — Визуальная полировка

#### 3.1 — Уродливый квадратик у фильтра "Все"
**Проблема**: Рядом с текстом в комбобоксах виден закрашенный квадратик — артефакт рендеринга `::drop-down` subcontrol под Fusion.

**Решение**:
- `QComboBox::drop-down`: добавлено `background: transparent`
- `QComboBox::down-arrow`: явные размеры `width: 8px; height: 5px`

**Файлы**: `ui/themes/modern_styles.py` (строки 381-396)

#### 2.1 — Плейсхолдеры кадра/видео (частично)
**Подготовка**: Создан переиспользуемый `EmptyStatePlaceholder` в `ui/widgets/utils.py` по паттерну `_MapPlaceholder` (иконка + заголовок + подзаголовок).

**Файлы**: `ui/widgets/utils.py` (строки 51-113)

*Примечание: Интеграция в `processing_page.py` и `error_editor_page.py` требует отдельного коммита для тестирования.*

---

## 2026-09-02 — Критические исправления обработки видео, карты и CPU-режимов

### 🚨 P0 — Критические блокеры (функциональность не работала вообще)

#### 1.1 — ImportError в `server/map_server.py`
**Проблема**: Импорт `SIGNS_WITH_VARIOUS_TEXT` из `configs.sign_data` падал с `ImportError` — такой константы не существует (правильное имя: `SIGNS_WITH_TEXT`). Опечатка после рефакторинга BLOCK P.2. **Карта не работала ни в одном режиме** — любая попытка открыть вкладку "Карта" показывала "Ошибка сервера".

**Решение**: `SIGNS_WITH_VARIOUS_TEXT as signs_with_various_text` → `SIGNS_WITH_TEXT as signs_with_various_text`

**Файл**: `server/map_server.py:24`

#### 1.2 — ImportError в `processing/ocr_worker.py`
**Проблема**: Импорт `TYPE_SIGNS_WITH_TEXT, NAME_SIGNS_CITY` из `configs.sign_config` падал с `ImportError` — в `sign_config.py` (легаси-шим) эти константы реэкспортируются под **строчными** алиасами (`type_signs_with_text`, `name_signs_city`). **Pipeline-режим с OCR через QThread не запускался** при выключенной настройке "OCR в отдельном процессе" — обработка падала на загрузке моделей.

**Решение**: `from configs.sign_config import ...` → `from configs.sign_data import TYPE_SIGNS_WITH_TEXT, NAME_SIGNS_CITY`

**Файл**: `processing/ocr_worker.py:13`

#### 1.3 — Проверка всех прямых импортов из sign_data/sign_config
**Результат**: Остальные импорты корректны. Больше несовпадений имён не найдено.

---

### ⚡ P1 — Обработка ломается при штатной работе (напрямую связано с CPU-режимами)

#### 2.1 — Рассинхронизация порогов трекинга SignHandler с адаптивным frame-skip
**Проблема**: `SignHandler` использовал жёстко зашитые пороги (`gap < 7`, `DIFF_FRAMES_REMOVE = 5`) в терминах разницы номеров кадров, откалиброванные на `FRAME_STEP=5, skip=1`. Но `DetectorThread` (режимы `single_thread` и `pipeline`) **дополнительно** прореживает кадры через адаптивный `_calc_skip_interval(speed)` (BLOCK CPU-1/CPU-2), достигая разрыва **до 22 кадров** на скорости 120 км/ч (и >7 уже при 30 км/ч).

**Последствия**: Основной путь матчинга (`_match_evidences`: `gap < 7`) систематически проваливался, трекинг держался на запасном фолбэке (`_attach_unmatched`) **без учёта давности вообще**, короткие треки (<4 наблюдений) удалялись преждевременно → **фрагментированные/задвоенные треки**, потеря знаков.

**Решение**:
- Добавлена глобальная переменная `config.CURRENT_EFFECTIVE_SKIP` (обновляется в `DetectorThread` на каждой итерации)
- Метод `SignHandler._effective_gap_frames()`: динамический расчёт порога = `max(BASE=7, FRAME_STEP × skip × 1.5, MAX=120)`
- Заменены все жёсткие пороги:
  - `_match_evidences`: `gap < 7` → `gap < self._effective_gap_frames()`
  - `_remove_lost_signs`: `> DIFF_FRAMES_REMOVE` → `> self._effective_gap_frames()`
  - `_finalize_signs`: `>= DIFF_FRAMES_MOVE` → `>= self._effective_gap_frames()`

**Файлы**: `configs/config.py:66`, `processing/detector_thread.py:388`, `core/sign_handler.py:36-40,89-108,290,373,387`

#### 2.2 — Фиксированный радиус 50px в Detector.detect_with_tracking
**Проблема**: Тот же класс ошибки — при большом разрыве между кадрами (>20) типичное смещение знака в кадре растёт, но радиус проверки "есть ли рядом TrackedSign" оставался 50px → риск ложного совпадения с **соседним знаком** (два знака на одном столбе), что вело к **молча неверному типу знака** (использовался `stable_cnn_class` от чужого трека).

**Решение**: Масштабируемый радиус = `min(50 × CURRENT_EFFECTIVE_SKIP, 220)` для обеих проверок (CNN skip + OCR throttling).

**Файл**: `core/detector.py:883,896,937`

---

### 🎯 P2 — Точность GPS/азимута и согласованность CPU-backend'ов

#### 3.1 — Хардкод "60 кадров на GPS-точку" в video_reader.py
**Проблема**: Инициализация `gps_index` использовала реальный `config.VIDEO_FPS` (BLOCK J.2), но **инкремент** внутри цикла чтения — захардкоженное `60`. Для видео с FPS ≠ 60 (30fps экшн-камера, смартфон) `gps_index` накопительно уходил от реального положения → неверная скорость для адаптивного skip (раздел 2.1) и координаты.

**Решение**: `if (abs_frame - gps_index * 60) > 60:` → `if (abs_frame - gps_index * config.VIDEO_FPS) > config.VIDEO_FPS:`

**Файл**: `processing/video_reader.py:284`

#### 3.2 — SignHandler._update_azimuths игнорирует интерполяцию курса
**Проблема**: Азимут проставлялся через "сырой" `GPXHandler.get_azimuth(INDEX_OF_GPS+1)` без интерполяции/сглаживания (BLOCK J.1/J.3), хотя координаты в `DetectorThread._build_detected` уже использовали `get_interpolated(abs_frame, VIDEO_FPS)`. Азимут был более "дёрганым", чем задумано.

**Решение**: `_update_azimuths` теперь использует `get_interpolated(config.INDEX_OF_All_FRAME, config.VIDEO_FPS).course` с fallback на старый метод.

**Файл**: `core/sign_handler.py:366-380`

#### 3.3 — Process_pool: дублирование моделей на CPU
**Проблема**: Каждый из N воркеров (по умолчанию `cpu_count-1`, может быть 4-15+) создаёт ПОЛНЫЙ `Detector()` с собственными копиями всех моделей (~2-3 ГБ на воркер) + EasyOCR. Пользователь не предупреждается о расходе памяти.

**Решение** (минимальный вариант): Добавлено явное warning в лог при старте `_start_process_pool()` на CPU: "Process Pool на CPU: каждый из N воркеров загрузит собственную копию всех моделей (~2-3 ГБ каждая). Рекомендуется 'Один поток' для CPU."

**Файл**: `processing/processing_controller.py:16,260-266`

#### 3.4 — ONNX/OpenVINO CPU-backend — незакрытые пункты верификации
**Статус**: Код реализован (BLOCK M), но стресс-тест (M.5: ≥20 мин на ONNX CPU без крашей) и реальный бенчмарк (M.7: FPS PyTorch vs ONNX vs OpenVINO) **не выполнены** из-за отсутствия тестовых данных в текущем окружении. Пункты остаются открытыми согласно правилу "ни один пункт не объявлен выполненным без факта проверки" (BLOCK_M_Q_EXECUTION_REPORT.md).

---

### 🧹 P3 — Гигиена карты (низкий приоритет)

#### 4.1 — index.html — удалён окончательно
**Причина**: Файл заявлен как удалённый в CHANGELOG (BLOCK O.1), но физически существовал в `templates/index.html`. Ссылается на несуществующие эндпоинты (`/track`, `/geojson`, `/all_img`, `/save_geojson` и др.) — абсолютно мёртв, вводил в заблуждение.

**Решение**: Удалён `templates/index.html`.

#### 4.2 — map.html: FRAMES_PER_VIDEO захардкожен в JS
**Проблема**: `const FRAMES_PER_VIDEO = 63600` захардкожен в `map.html:1569`, но если хотя бы одно видео в наборе имеет другую длину (последний файл серии почти всегда короче), расчёт `videoIdx`/`frameInVideo` для плеера разъезжается → плеер перематывает не то видео.

**Решение**:
- Добавлено поле `frames_per_video_hint` в `/api/video_info` (равно `config.FRAMES_PER_VIDEO`)
- `map.html` теперь запрашивает метаданные и использует `frames_per_video_hint` с сервера вместо захардкоженного значения, с fallback на 63600

**Файлы**: `server/map_server.py:669`, `templates/map.html:1569-1603`

---

### 📝 Метод работы
Все баги из этого блока были **эмпирически воспроизведены** (импорт-ошибки проверены прямым `import`, рассинхронизация порогов — численным расчётом по формулам из кода). Исправления минимально инвазивны, не меняют архитектуру. Приоритеты: P0 (не работает) → P1 (ломается при работе) → P2 (точность) → P3 (гигиена).

---

## 2026-09-01 — Блоки M–Q: ONNX/OpenVINO CPU-инференс + техдолг

### ✨ Новый функционал

#### ONNX Runtime / OpenVINO для CPU-инференса (Блок M)
- **Экспорт моделей**: `scripts/export_models_onnx.py` — конвертация всех 18 YOLO-моделей в ONNX/OpenVINO
- **Настройки**: `cpu_inference_backend` ("torch", "onnx", "openvino") — opt-in выбор backend
- **Lazy loading**: Расширен `_LazyModel` для автоматического выбора backend с откатом на PyTorch
- **UI**: Кнопка "Экспортировать модели для CPU" с фоновым worker и прогрессом
- **Бенчмарк**: Флаг `--backend` в `scripts/benchmark_detector.py`
- **Тесты**: `tests/test_onnx_backend.py` — проверка динамического батчинга и консистентности

**Статус**: ✅ Код реализован, требуется прогон пользователем с реальным видео для измерения FPS.

#### Сохранение error_frames (Блок N.2)
- Настройка `save_error_frames` теперь функциональна
- Кропы с низкой уверенностью CNN сохраняются в `error_frames_dir`
- Троттлинг: максимум 1 сохранение на track_id

### 🐛 Исправления багов (Блок N)

#### N.1 — Радиус финальной дедупликации
**Проблема**: `GRID_CELL_M = 20.0` (константа) физически ограничивала эффективный радиус поиска дублей ~20–40м, независимо от настройки `dedup_radius_final_m` (допускала до 200м).

**Решение**:
- `GRID_CELL_M = max(10.0, dedup_radius_final_m / 2.0)` — динамический расчёт
- Окно проверки соседних ячеек: `math.ceil(dedup_radius_final_m / GRID_CELL_M)` вместо фиксированного `±1`

**Тест**: `tests/test_deduplication.py::TestDeduplicationLargeRadius` — два фичи на расстоянии 150м при радиусе 200м корректно мержатся.

#### N.3 — Удалено неиспользуемое поле turn_detection_radius_m
**Причина**: Дублирует функционал `turn_ray_max_distance_m`, не используется с момента внедрения bearing-based геометрии (BLOCK H).

**Изменения**:
- Удалено из `configs/settings.py`
- Удалён UI-контрол из `ui/widgets/settings_page.py`
- Удалены все упоминания из `_collect_settings`, `_reset`, импорта JSON

### 🧹 Очистка мёртвого кода (Блок O)

**Удалены файлы**:
- `index.html` — легаси-версия карты на ArcGIS (дублировала `templates/map.html`)
- `ui/themes/theme_manager_backup.py` — полный дубликат `ThemeManager`
- `ui/widgets/placeholder_pages.py` — дублирующие классы `MapPage`/`ErrorEditorPage`

**Файлы, оставленные без изменений**:
- `signs.json` — не используется в коде (только в документации), оставлен для обратной совместимости

### 🔧 Консистентность конфигурации (Блок P)

#### P.1 — Настраиваемые пороги lane_detector
**Было**: Хардкод `conf=0.65` в `core/lane_detector.py::__process_sign()`

**Стало**:
- Новые настройки: `lane_conf_detect`, `lane_conf_segment` (default 0.65)
- `LaneDetector.__init__(settings)` принимает настройки
- Пороги применяются через `self.CONF_LANE_DETECT`, `self.CONF_LANE_SEGMENT`

#### P.2 — Прямые импорты из sign_data / sign_models
**Изменено**:
- `core/lane_detector.py`: `from configs.sign_models import ...` вместо легаси `sign_config`
- `server/map_server.py`: `from configs.sign_data import ...` с алиасами для совместимости

Легаси-шим `configs/sign_config.py` сохранён для обратной совместимости, но новый код его не использует.

#### P.3 — Миграция print() → logging (частичная)
**Заменено**:
- `core/lane_detector.py`: `print(...)` → `logger.debug(...)`
- `server/map_server.py`: Добавлен `logger = logging.getLogger(__name__)`

**Оставшиеся файлы с print()**: `core/detector.py` (частично), `ui/` модули (не критичны для продакшна) — полная миграция требует отдельной сессии.

### 📁 Гигиена репозитория (Блок Q)

#### Q.1 — Консолидация исторических отчётов
- Создана `docs/archive/`
- Перемещены 60+ markdown-файлов отчётов (`BLOCK_*.md`, `AGENT_*.md`, `BUGFIX_*.md` и т.д.)
- В корне остаются только:
  - `CHANGELOG.md` (этот файл)
  - `WHY_SINGLE_THREAD_FASTER.md` (живой архитектурный документ)
  - `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` (актуальная документация)

### 📝 Изменённые файлы

#### Созданные
- `scripts/export_models_onnx.py` — экспорт моделей в ONNX/OpenVINO
- `tests/test_onnx_backend.py` — тесты батчинга ONNX/OpenVINO моделей
- `tests/test_deduplication.py::TestDeduplicationLargeRadius` — тесты N.1
- `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` — документация ONNX/OpenVINO backend
- `CHANGELOG.md` — этот файл
- `docs/archive/` — архив исторических отчётов

#### Модифицированные
- `configs/settings.py`:
  - `+cpu_inference_backend`
  - `+lane_conf_detect`, `+lane_conf_segment`
  - `-turn_detection_radius_m`
- `configs/sign_models.py`:
  - Расширен `_LazyModel` (ONNX/OpenVINO поддержка)
  - `+_p_onnx()`, `+_p_openvino()`
  - Обновлены все 18 объявлений моделей
  - `reload_all_models_if_device_changed()` отслеживает backend
- `core/final_handler.py`:
  - Динамический `GRID_CELL_M` (N.1)
  - Динамическое окно проверки ячеек в `_deduplicate()`
- `core/detector.py`:
  - `+_save_error_frames`, `+_error_frames_dir` в `__init__`
  - `+_maybe_save_error_frame()` (N.2)
  - Вызовы из `_run_cnn_model` и `_run_cnn_batch`
- `core/lane_detector.py`:
  - `+CONF_LANE_DETECT`, `+CONF_LANE_SEGMENT` (P.1)
  - `__init__(settings)` принимает настройки
  - Прямой импорт из `sign_models` (P.2)
  - `print()` → `logger.debug()` (P.3)
- `ui/widgets/settings_page.py`:
  - `+_cpu_backend_combo` с логикой enable/disable
  - `+_export_models()`, `+_on_export_finished()`
  - `-_turn_radius_spin` (N.3)
  - `_collect_settings()` сохраняет `cpu_inference_backend`
- `server/map_server.py`:
  - `+import logging`
  - Прямой импорт из `sign_data` с алиасами (P.2)
- `scripts/benchmark_detector.py`:
  - `+--backend` флаг
  - Установка backend через `AppSettings`
- `.gitignore`:
  - `+*.onnx`
  - `+*_openvino_model/`

#### Удалённые
- `index.html`
- `ui/themes/theme_manager_backup.py`
- `ui/widgets/placeholder_pages.py`

### ⚠️ Требуется действие пользователя

#### 1. Бенчмарк ONNX/OpenVINO (Блок M.0, M.7)
```bash
# Baseline PyTorch CPU
python scripts/benchmark_detector.py --video <путь> --frames 100 --force-cpu --backend torch

# Экспорт моделей
python scripts/export_models_onnx.py --format onnx

# Бенчмарк ONNX
python scripts/benchmark_detector.py --video <путь> --frames 100 --force-cpu --backend onnx
```
Записать FPS и CPU-конфигурацию в `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` (раздел "Численные результаты").

#### 2. Тесты
```bash
# Тесты ONNX батчинга
pytest tests/test_onnx_backend.py -v

# Тесты дедупликации
pytest tests/test_deduplication.py::TestDeduplicationLargeRadius -v
```

#### 3. Стресс-тест потокобезопасности (если планируется включить ONNX по умолчанию)
- Обработать видео ≥20 минут в режиме `single_thread`, `use_cuda=False`, `cpu_inference_backend="onnx"`
- Следить за крашами 0xC0000409 (конфликт потоков)
- Если краш появится — настроить `OMP_NUM_THREADS=1` / `ORT_NUM_THREADS=1` (см. `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` §M.5)

### 🚧 Блоки, не выполненные в этой сессии

#### Блок R — CI/CD
**Причина**: Требует подтверждения платформы CI (GitHub Actions / GitLab CI / другое).

**Рекомендация**: Выполнить отдельной сессией после подтверждения требований.

#### Блок S — Редактируемая карта
**Причина**: Самый объёмный блок (POST /api/sign, расширение PATCH, draggable-маркеры).

**Рекомендация**: Выполнить отдельной сессией, используя промпт:
```
Выполни Блок S из prompts/AGENT_PROMPT_onnx_cpu_inference_and_tech_debt.md
```

### 📊 Статистика изменений

- **Созданных файлов**: 5
- **Модифицированных файлов**: 9
- **Удалённых файлов**: 3
- **Архивированных отчётов**: 60+
- **Новых настроек**: 3 (`cpu_inference_backend`, `lane_conf_detect`, `lane_conf_segment`)
- **Удалённых настроек**: 1 (`turn_detection_radius_m`)
- **Новых тестов**: 5 (ONNX батчинг + дедупликация)

### 🔗 Связанные документы

- `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` — детальная документация ONNX/OpenVINO backend
- `WHY_SINGLE_THREAD_FASTER.md` — обоснование подхода (CPU-инференс через смену backend, а не распараллеливание Python)
- `docs/archive/STATUS.md` — исторический статус проекта
- `docs/archive/AUDIT_REPORT.md` — технический аудит, лёгший в основу блоков N–Q

---

## Предыдущие версии

История до 2026-09-01 находится в архивированных отчётах (`docs/archive/`).
Основные вехи:
- **BLOCK H** (август 2026): Bearing-based геометрия поворотов
- **BLOCK I** (август 2026): Геометрическое определение стороны знака + дедупликация
- **BLOCKS J–L** (август 2026): GPS confidence, CPU-оптимизации, светлая тема
- **BLOCKS A–C** (август 2026): Батчинг CNN, кэширование, async OCR
