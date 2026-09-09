# PROMPT: Подготовка проекта RoadScanner (Signer PRIME) к билду

Ты — AI-агент с доступом к файловой системе и bash в этом репозитории. Твоя задача — привести проект в состояние, готовое к сборке (PyInstaller/аналог): убрать мусор, разложить файлы по папкам, оставить в корне только `main.py` и обязательные конфиг-файлы, и пересобрать `requirements.txt` так, чтобы в нём были только реально используемые зависимости.

Работай аккуратно и пошагово. Перед удалением любого `.py`-файла **обязательно** проверяй через `grep -rn` по всему репозиторию (кроме `.git`, `venv*`, `__pycache__`), не импортируется ли он откуда-то — если импортируется, файл нельзя удалять, только переносить с сохранением рабочих импортов (или чинить импорты после переноса).

Не удаляй и не трогай содержимое `.git/`. Не трогай сами модели (`*.pt`, `*.keras`, `*.onnx`, LFS-объекты) и их директории (`small_models/`, `lane_guidance_models/`, `CNN_side/`) — они нужны для работы приложения, даже если сейчас представлены LFS-заглушками.

---

## Шаг 0 — Инвентаризация

1. Построй полное дерево репозитория (`git ls-files` или `find . -not -path './.git/*'`).
2. Раздели все файлы в корне проекта на категории:
   - **Точка входа**: `main.py` — остаётся в корне, единственный `.py`-файл в корне после уборки.
   - **Обязательные корневые конфиги** (по конвенции остаются в корне): `requirements.txt`, `.gitignore`, `.gitattributes`, `README.md` (создать, если отсутствует — см. Шаг 5).
   - **IDE/tooling-мусор**: `.idea/`, `.kiro/` — это персональные настройки IDE/агента, не нужны для билда. `.idea/` полностью удалить из репозитория (и добавить в `.gitignore`, если ещё не добавлено). `.kiro/` — уточни, содержит ли что-то нужное runtime'у (например `.kiro/model_cache/openvino/` — это generated-кэш, тоже в `.gitignore`, не удалять физически если использовался как кэш, но из репозитория/сборки исключить); `.kiro/settings/lsp.json` — dev-tooling, в билд не нужен, можно удалить или оставить вне сборочного пакета.
   - **Отчёты и саммари прошлых агентских сессий в корне** (десятки файлов вида `BLOCK_*.md`, `PROMPT_*.md`, `FINAL_*.md`, `QUICK_*.md`, `CPU_*.md`, `ONNX_*.md`, `BACKEND_SELECTION_FIX.md`, `TASK_*.md`, `TODO_*.md`, `COMPLETION_*.md`, `STATUS_*.md`, `EXECUTION_REPORT.md`, `README_BLOCKS_M_S.md`, `NEXT_STEPS.md`, `QUICKSTART*.md`, `MAP_FIX_UNICODE.md`, `VIDEO_*.md`, `ВАЖНО_*.md`, `БЫСТРЫЙ_СТАРТ_ONNX.md`, `КРАТКАЯ_*.md`, `РЕЗЮМЕ_*.md`, `ФИНАЛЬН*.md`, `ПРОМПТ_*.md`, `OPENVINO_ГОТОВ.md`, `CHANGELOG_SIGN_LOSS_FIX.md`, `COMPLETION_STATUS.txt`, `CHANGES_LIST.md`, `BUGFIX_SUMMARY.md`, `TESTING_INSTRUCTIONS.md`, `COMPLETION_CHECKLIST.md`, и т.п.). Это исторические логи выполнения промптов ИИ-агентами, не нужны для билда и не нужны для чтения пользователем. Смотри Шаг 1.
   - **Живая/актуальная документация**: `CHANGELOG.md`, `WHY_SINGLE_THREAD_FASTER.md` — это единственные два md-файла в корне, которые описывают текущую архитектуру, а не отчёт о сессии. Их нужно переместить в `docs/`, не удалять.
   - **Разовые diagnostic/debug/reexport скрипты в корне** (не часть приложения, не импортируются ниоткуда): `test_backend_selection.py`, `test_bug1_simple.py`, `test_coordinates.py`, `test_debug_gap.py`, `test_import.py`, `test_onnx_loading.py`, `test_single_export.py`, `check_onnx_input_size.py`, `diagnostic_backend_check.py`, `reexport_detection_model.py`, `convert_models_silent.py`. См. Шаг 2.
   - **Случайный файл** `img.png` в корне — не используется кодом (проверь grep на `img.png`), удалить, если действительно не используется.
   - **Корневые директории приложения**, которые остаются на месте: `core/`, `configs/`, `processing/`, `server/`, `ui/`, `templates/`, `scripts/`, `tests/`, а также директории с весами моделей (`small_models/`, `lane_guidance_models/`, и, если присутствует, `CNN_side/`), `signs.json`, `utils.py`.

---

## Шаг 1 — Архивация исторических отчётов

1. Создай папку `docs/archive/` (если ещё не существует).
2. Перемести туда **все** markdown/txt-файлы из корня, которые являются отчётами о выполнении прошлых промптов/сессий (список категорий — см. Шаг 0, пункт "Отчёты и саммари"). Практический критерий: если файл в корне — это `.md` или `.txt`, и это не `README.md`, не `CHANGELOG.md`, не `WHY_SINGLE_THREAD_FASTER.md`, не `requirements.txt` — он идёт в `docs/archive/`.
3. `CHANGELOG.md` и `WHY_SINGLE_THREAD_FASTER.md` перемести в `docs/` (не в архив — это актуальная документация).
4. Ничего из перемещённого не редактируй по содержимому — просто `git mv`.
5. После переноса убедись, что ни один `.py`-файл нигде не ссылается на эти `.md`-файлы по пути (обычно не ссылается, но проверь `grep -rn "\.md" --include=*.py`).

---

## Шаг 2 — Уборка разовых diagnostic/debug скриптов из корня

Эти файлы в корне — одноразовые скрипты, написанные агентами для диагностики ONNX/OpenVINO/бэкендов в конкретный момент времени. Они не являются частью рантайма приложения и не импортируются из `main.py` или пакетов `core/`, `processing/`, `ui/`, `server/`.

1. Для каждого из: `test_backend_selection.py`, `test_bug1_simple.py`, `test_coordinates.py`, `test_debug_gap.py`, `test_import.py`, `test_onnx_loading.py`, `test_single_export.py`, `check_onnx_input_size.py`, `diagnostic_backend_check.py`, `reexport_detection_model.py`, `convert_models_silent.py` — проверь через `grep -rn "<имя_файла_без_.py>" --include=*.py .`, что на него никто не ссылается (импортом или вызовом через subprocess).
2. Если файл действительно мёртвый/одноразовый диагностический — перемести в `scripts/dev/` (создай эту папку) вместо удаления, если существует шанс, что он ещё пригодится для будущей диагностики ONNX/OpenVINO. Если файл дублирует функциональность, которая уже есть в `scripts/export_models_onnx.py` или `scripts/benchmark_detector.py` — удали его.
3. `img.png` — удали, если не используется кодом.

---

## Шаг 3 — Разбор папки `scripts/`

В `scripts/` сейчас смешаны production-скрипты (нужны пользователю/CI) и одноразовые скрипты, которые писались агентами для конкретной задачи и больше не нужны. Раздели так:

- **Оставить в `scripts/` как есть** (нужны в проекте): `scripts/export_models_onnx.py` (экспорт моделей в ONNX/OpenVINO — используется из UI), `scripts/benchmark_detector.py`, `scripts/benchmark_end_to_end_cpu.py` (если реально используются для регулярных замеров — проверь, упоминаются ли в README/докe как рабочий инструмент).
- **Переместить в `scripts/dev/`** (разовая диагностика, не часть обычного пайплайна): `scripts/diagnose_coordinates.py`, `scripts/diagnose_empty_geojson.py`, `scripts/verify_block_h.py`, `scripts/test_cnn_batching.py`, `scripts/test_detector_regression.py`, `scripts/check_sign_data_duplicates.py`, `scripts/analyze_print_usage.py`, `scripts/fix_logging.py`.
- Перед переносом каждого — так же проверь grep на использование извне (например, вызывается ли из `tests/` или из CI-конфигурации, если она появится).

---

## Шаг 4 — `.idea/` и прочий IDE-мусор

1. Удали директорию `.idea/` полностью из репозитория (`git rm -r --cached .idea` при необходимости, плюс физическое удаление).
2. Убедись, что `.idea/` добавлена в `.gitignore` (если нет — добавь строку `.idea/`).
3. Если `.kiro/` не содержит ничего, читаемого рантаймом приложения (проверь: `configs/inference_threading.py` пишет кэш в `.kiro/model_cache/openvino/` — это generated-директория, создаётся автоматически при первом запуске с OpenVINO backend'ом), то саму директорию `.kiro/settings/` можно удалить из репозитория, а `.kiro/model_cache/` добавить в `.gitignore` (не коммитить сгенерированный кэш).

---

## Шаг 5 — Минимальный `README.md` в корне

Если в корне нет `README.md` — создай короткий (не отчёт, а обычный README): название проекта, краткое описание (RoadScanner / Signer PRIME — детекция и геопривязка дорожных знаков по видео с GPS-треком), как установить зависимости (`pip install -r requirements.txt`), как запустить (`python main.py`), упоминание, что документация по архитектуре — в `docs/`.

---

## Шаг 6 — Пересборка `requirements.txt`

Текущий `requirements.txt` собирался инкрементально разными агентскими сессиями и может содержать лишнее (например, `openvino`/`openvino-dev` как жёсткую зависимость, хотя это optional CPU-backend) или неполное (например, `shapely`, которую `core/intersection_geometry.py` импортирует в `try/except ImportError` — то есть она opt-in, но раз используется — должна быть в зависимостях, если её отсутствие ухудшает качество работы).

Выполни:

1. Собери полный список внешних (не stdlib) импортов по всему коду, который реально исполняется в собранном приложении (`main.py` + всё, что он транзитивно импортирует: `core/`, `configs/`, `processing/`, `server/`, `ui/`, `utils.py`). Используй `grep -rhoE "^\s*(import|from)\s+[a-zA-Z0-9_\.]+" --include=*.py core configs processing server ui main.py utils.py` и вручную сведи к именам pip-пакетов (например `cv2` → `opencv-python`, `PIL` → `Pillow`, `PyQt6.*` → `PyQt6` / `PyQt6-WebEngine`, `flask_socketio` → `flask-socketio`, `flask_cors` → `flask-cors`, `sklearn` и т.д.).
2. Отдельно определи, какие зависимости используются только в `scripts/`, `scripts/dev/`, `tests/` (dev/test-only), и вынеси их в отдельный файл `requirements-dev.txt` (например `pytest`, если используется — проверь `tests/conftest.py` и наличие `import pytest`), а не смешивай с основным `requirements.txt`, который должен содержать только то, что нужно для запуска `main.py` в собранном виде.
3. Для optional CPU-инференс бэкендов (`onnx`, `onnxruntime`, `openvino`, `openvino-dev`) — реши, входят ли они в обязательный `requirements.txt` или в отдельный `requirements-cpu-backends.txt` (или отдельную секцию с комментарием "опционально"). Дефолтный backend в `configs/settings.py` — `torch`/PyTorch, поэтому `onnx`/`onnxruntime`/`openvino`/`openvino-dev` не обязательны для базовой работы приложения; вынеси их в опциональный файл или явно закомментированный блок с пояснением, а не в обязательные зависимости. Проверь по факту (grep), не ломает ли это импорт где-то в основном пути (`configs/sign_models.py` импортирует `onnxruntime`/`openvino` только лениво внутри `try/except`, то есть отсутствие пакета не должно ронять приложение).
4. Убедись, что `onnxruntime-gpu` НЕ упоминается нигде как обязательная зависимость (в документации отмечено, что она конфликтует с CPU-инференсом) — не добавляй её.
5. Проверь версии в текущем `requirements.txt` на актуальность синтаксиса (`>=`), не занижай и не завышай версии без причины — если пакет используется, но версия не была явно протестирована, оставь как есть или без указания версии, если это не критично.
6. Итоговый `requirements.txt` должен содержать только: GUI (`PyQt6`, `PyQt6-WebEngine`), CV/ML (`opencv-python`, `ultralytics`, `easyocr`, `joblib`, `numpy`, `Pillow`, `torch`/`torchvision` — если не устанавливаются как зависимость `ultralytics` автоматически, добавь явно), GPS/Geo (`gpxpy`, `geopy`, `geojson`, `pyproj`, `requests`), Server (`flask`, `flask-cors`, `flask-socketio`, `python-engineio`, `python-socketio`, `jinja2`), и любые другие пакеты, которые реально импортируются в исполняемом пути приложения и не входят в стандартную библиотеку Python. Убери пустые секции-комментарии, которые ссылаются на уже несуществующий код.
7. Приложи короткий diff-комментарий (в чате, не в файле) — что убрано и что добавлено и почему.

---

## Шаг 7 — Финальная проверка

1. В корне репозитория после уборки должны остаться: `main.py`, `requirements.txt`, `.gitignore`, `.gitattributes`, `README.md`, и папки: `core/`, `configs/`, `processing/`, `server/`, `ui/`, `templates/`, `scripts/`, `tests/`, `docs/`, директории с весами моделей (`small_models/`, `lane_guidance_models/`, и т.п.), `signs.json`, `utils.py`. Никаких других файлов `.py`/`.md`/`.txt` в корне быть не должно (кроме явно перечисленных).
2. Прогони `python -c "import ast; ast.parse(open('main.py').read())"` и аналогично попытайся импортировать ключевые модули (`python -c "from configs import config"`, `python -c "from core import detector"` и т.п.), чтобы убедиться, что перенос файлов не сломал относительные импорты.
3. Прогони существующий набор тестов из `tests/` (`pytest tests/` или ручной запуск `test_*.py` файлов, где нет pytest-зависимости) и убедись, что после переноса файлов пути в тестах (если они читают файлы по относительному пути, например `ui/widgets/dashboard_page.py` в `tests/check_dashboard_page.py`) по-прежнему корректны.
4. Если что-то не запускается из-за сломанного импорта после переноса — не откатывай перенос, а исправь импорт (укажи корректный путь), потому что цель — чистая структура, а не сохранение status quo.
5. В конце выведи финальное дерево корня проекта (`ls -la .` без учёта `.git`) и подтверди, что в корне ровно один `.py`-файл — `main.py`.

---

## Что НЕ трогать

- Не удаляй и не переименовывай `core/`, `configs/`, `processing/`, `server/`, `ui/`, `templates/`, `tests/` как директории и их внутреннюю структуру — переноса требуют только файлы из корня и часть `scripts/`.
- Не трогай `.gitattributes` и Git LFS-конфигурацию моделей.
- Не меняй логику кода — это чисто файловая уборка и правка `requirements.txt`, никакого рефакторинга функциональности.
- Не удаляй `signs.json`, даже если он "не используется в коде напрямую" — он используется как справочные данные / упомянут как оставленный для обратной совместимости, оставь на месте.
