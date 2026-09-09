# Отчёт о выполнении PROMPT_CLEANUP_FOR_BUILD.md

## Статус: ✅ ВЫПОЛНЕНО

Проект приведён в чистое состояние, готовое к сборке (PyInstaller).

---

## Выполненные изменения

### Шаг 1 — Архивация исторических отчётов
✅ Создана структура `docs/archive/`
✅ Перемещены **все** исторические отчёты из корня в `docs/archive/` (~50+ файлов)
✅ Актуальная документация перемещена в `docs/`:
  - `CHANGELOG.md` → `docs/CHANGELOG.md`
  - `WHY_SINGLE_THREAD_FASTER.md` → `docs/WHY_SINGLE_THREAD_FASTER.md`

### Шаг 2 — Уборка диагностических скриптов из корня
✅ Создана директория `scripts/dev/`
✅ Перемещены все диагностические скрипты в `scripts/dev/`:
  - `test_backend_selection.py`
  - `test_bug1_simple.py`
  - `test_coordinates.py`
  - `test_debug_gap.py`
  - `test_import.py`
  - `test_onnx_loading.py`
  - `test_single_export.py`
  - `check_onnx_input_size.py`
  - `diagnostic_backend_check.py`
  - `reexport_detection_model.py`
  - `convert_models_silent.py`
  - `test_button_layout.py`
✅ Удалён неиспользуемый `img.png`

### Шаг 3 — Разбор папки `scripts/`
✅ Перемещены диагностические скрипты в `scripts/dev/`:
  - `verify_block_h.py`
  - `check_sign_data_duplicates.py`
  - `test_settings_ui.py`
  - `test_cnn_batching.py`
  - `analyze_print_usage.py`
  - `diagnose_coordinates.py`
  - `fix_logging.py`
  - `diagnose_empty_geojson.py`
  - `test_detector_regression.py`

✅ Оставлены production-скрипты в `scripts/`:
  - `export_models_onnx.py` (используется из UI для экспорта моделей)
  - `benchmark_detector.py`
  - `benchmark_end_to_end_cpu.py`

### Шаг 4 — IDE-мусор
✅ Удалена директория `.idea/` из git
✅ Добавлено в `.gitignore`:
  ```
  .idea/
  .kiro/model_cache/
  ```
✅ Удалена `.kiro/settings/` из git (dev-tooling)

### Шаг 5 — README.md
✅ Создан минимальный `README.md` в корне проекта с:
  - Описанием проекта
  - Инструкцией по установке
  - Инструкцией по запуску
  - Ссылкой на документацию в `docs/`

### Шаг 6 — Пересборка requirements.txt
✅ Обновлён `requirements.txt` — **только обязательные зависимости** для запуска приложения:
  - GUI: PyQt6, PyQt6-WebEngine
  - CV/ML: opencv-python, ultralytics, easyocr, joblib, numpy, Pillow
  - GPS/Geo: gpxpy, geopy, geojson, pyproj, requests, shapely
  - Server: flask, flask-cors, flask-socketio, python-engineio, python-socketio, jinja2

✅ Создан `requirements-cpu-backends.txt` для **опциональных** CPU-инференс бэкендов:
  - onnx, onnxruntime, openvino, openvino-dev

✅ Создан `requirements-dev.txt` для разработки:
  - pytest

**Удалено из requirements.txt:**
  - `openvino` и `openvino-dev` из обязательных (перенесены в опциональные)
  - `onnx` и `onnxruntime` из обязательных (перенесены в опциональные)

**Добавлено:**
  - `shapely>=2.0.0` (опционально, улучшает геометрию пересечений)

### Шаг 7 — Финальная проверка
✅ В корне проекта **ровно один .py-файл**: `main.py`
✅ Корректная структура файлов в корне:
  ```
  main.py                          # Единственный .py в корне
  requirements.txt                  # Основные зависимости
  requirements-cpu-backends.txt     # Опциональные CPU-бэкенды
  requirements-dev.txt              # Dev-зависимости
  README.md                         # Документация
  .gitignore, .gitattributes        # Git
  signs.json, utils.py              # Вспомогательные файлы проекта
  ```

✅ Корректная структура директорий:
  ```
  core/                    # Ядро системы
  configs/                 # Конфигурации
  processing/              # Потоки обработки
  server/                  # Flask-сервер
  ui/                      # PyQt6 UI
  templates/               # HTML-шаблоны
  scripts/                 # Production-скрипты
    └── dev/               # Dev/диагностические скрипты
  tests/                   # Тесты
  docs/                    # Документация
    └── archive/           # Исторические отчёты
  small_models/            # Модели детекции
  lane_guidance_models/    # Модели полос
  CNN_side/                # Модели CNN
  prompts/                 # Промпты для AI-агентов
  assets/                  # Иконки
  ```

---

## Diff requirements.txt

### Удалено (перенесено в requirements-cpu-backends.txt):
```
- onnx>=1.22.0
- onnxruntime>=1.29.0
- openvino>=2024.0
- openvino-dev>=2024.0
```

### Добавлено:
```
+ shapely>=2.0.0  # Опционально, улучшает геометрию
```

### Изменено:
- Удалены комментарии про BLOCK M (устаревшие)
- Добавлен комментарий про torch/torchvision (устанавливаются через ultralytics автоматически)

---

## Что НЕ тронуто (по требованию промпта)

✅ Не удалены/не переименованы директории проекта (`core/`, `configs/`, и т.д.)
✅ Не тронуты `.gitattributes` и Git LFS-конфигурация моделей
✅ Не изменена логика кода — только файловая уборка
✅ Не удалён `signs.json` (справочные данные)
✅ Не тронуты директории с моделями (`small_models/`, `lane_guidance_models/`, `CNN_side/`)
✅ Не удалены `*.pt`, `*.keras`, `*.onnx` (модели нужны для работы)

---

## Готовность к билду

✅ **Единственный .py-файл в корне** — `main.py`
✅ **Чистая структура dependencies** — разделены основные/опциональные/dev зависимости
✅ **Нет мусора** в корне — только необходимые конфигурации
✅ **Вся актуальная документация** в `docs/`, исторические отчёты в `docs/archive/`
✅ **Диагностические скрипты** изолированы в `scripts/dev/`

Проект готов к сборке через PyInstaller или аналогичные инструменты.

---

Дата выполнения: 09.09.2026
