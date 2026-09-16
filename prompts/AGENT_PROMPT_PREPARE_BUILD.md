# Промпт для ИИ-агента: подготовка RoadScanner (Signer PRIME) к релизному билду

Скопируй всё содержимое ниже целиком в задачу для агента (Claude Code / любой coding-agent с доступом к репозиторию и shell).

---

## РОЛЬ И ЦЕЛЬ

Ты — инженер, готовящий Python/PyQt6-проект **RoadScanner (Signer PRIME)** к продакшн-сборке PyInstaller. У тебя есть полный доступ к репозиторию и bash. Нужно сделать ДВЕ вещи, обе — обязательны, ни одну нельзя пропустить или сделать частично:

1. **Навести порядок в корне репозитория**, убрав в подпапки все файлы, которые не обязаны лежать в корне, — но **не сломав приложение**.
2. **Собрать CPU-бэкенды ONNX Runtime и OpenVINO** для всех моделей (экспорт `.pt` → `.onnx` и `.pt` → OpenVINO IR) и **доказать**, что они реально загружаются и работают.

Ты обязан закончить оба пункта. Если что-то не получается — не молчи и не пропускай, а чини причину (недостающая зависимость, путь и т.д.) и доводи до результата. В конце — обязательный отчёт с доказательствами (лог команд, diff, список файлов).

---

## КРИТИЧЕСКИ ВАЖНОЕ ОГРАНИЧЕНИЕ — прочитай, прежде чем что-либо двигать

Требование "оставить в корне только main.py" **буквально невыполнимо без риска сломать приложение**, и вот почему:

- `app/utils.py::resource_path()`:
  ```python
  def resource_path(relative_path):
      if hasattr(sys, '_MEIPASS'):
          return os.path.join(sys._MEIPASS, relative_path)
      return os.path.join(os.getcwd(), relative_path)
  ```
  В dev-режиме (не frozen) все пути к моделям и ресурсам резолвятся **относительно текущей рабочей директории процесса**, а не относительно расположения модуля. Это значит, что `small_models/`, `CNN_side/`, `lane_guidance_models/`, `templates/`, `static/`, `sings/`, `sings_text/`, `configs/data/signs.json`, `assets/` обязаны быть доступны по путям **как они сейчас записаны в коде** (`_p("small_models/blue.pt")` и т.п.) при запуске `python main.py` из корня репозитория.
- `signer.spec` мапит эти же папки 1:1 в `_MEIPASS` (`datas.append((full, dst))` с `dst` вида `"small_models"`), то есть структура ресурсов внутри собранного `.exe` тоже завязана на текущие относительные имена.
- Тесты (`tests/*.py`) и некоторые проверочные скрипты открывают файлы по путям вида `"core/sign_handler.py"`, `"configs/sign_models.py"` **относительно корня репозитория** (см. `tests/check_dashboard_page.py`, `tests/check_eager_loading.py`, `tests/test_no_eager_model_loading.py`).
- `licensing/`, `updater/`, `signer.spec`/`updater.spec`, обфускатор (`scripts/build/obfuscate_licensing.py`) знают точные пути `licensing/*.py`, `main.py` в корне и т.д.

**Вывод:** переносить сами Python-пакеты (`core/`, `ui/`, `configs/`, `processing/`, `server/`, `app/`, `updater/`, `licensing/`) и ресурсные директории (`small_models/`, `CNN_side/`, `lane_guidance_models/`, `templates/`, `static/`, `sings/`, `sings_text/`, `assets/`, `installer/`, `configs/data/`) в этой задаче **запрещено**. Вместо буквального "только main.py" цель — убрать из корня весь **не-функциональный мусор**: одноразовые батники, отчёты, дублирующиеся конфиги сборки, requirements-файлы, spec-файлы (если это не сломает PyInstaller) — и аккуратно всё остальное разложить по `scripts/`, `docs/`, `build/config/` и т.п., обновив все места, где на них ссылаются.

Если по ходу работы найдёшь файл, про который не уверен, можно ли его двигать, — **сначала грепни весь репозиторий на упоминания его имени/пути**, и только если ссылок нет или все они найдены и будут обновлены — переноси.

---

## ШАГ 0 — Безопасность

1. Убедись, что репозиторий — git-репозиторий с чистым `git status`. Если есть незакоммиченные изменения — останови работу и попроси закоммитить их отдельно.
2. Создай отдельную ветку: `git checkout -b chore/prepare-release-build`.
3. Перед каждым крупным блоком изменений делай `git add -A && git commit -m "..."` — атомарными коммитами, чтобы можно было откатить любой шаг.
4. Работай итеративно: перенёс группу файлов → обновил ссылки → прогнал проверку (шаг 4) → закоммитил. Не делай все перемещения одним махом.

---

## ШАГ 1 — Инвентаризация корня

Выполни и вставь результат в свой рабочий лог:

```bash
ls -la .
```

Раздели всё, что лежит в корне, на три категории:

### Категория A — НЕ ТРОГАТЬ (обязаны остаться в корне)
- `main.py` — точка входа.
- `requirements.txt`, `requirements-dev.txt`, `requirements-cpu-backends.txt` — pip по конвенции ищет их в корне; если решишь их всё же перенести (например, в `requirements/`), см. правило ниже "если переносишь — обнови всё".
- `version.json` — читается и в dev, и в frozen-режиме через `Path(__file__).parent.parent / "version.json"` и `Path(sys.executable).parent / "version.json"` (`app/version.py`). Также копируется в `dist/Signer/version.json` в `prepare_release.bat`.
- `build_config.json` / `build_config.json.example` — `configs/settings.py::AppSettings.load()` ищет `build_config.json` рядом с `main.py` в dev-режиме и рядом с `.exe` во frozen-режиме. Не переносить.
- `signer.spec`, `updater.spec` — PyInstaller их обычно запускают из корня (`ROOT = os.path.dirname(os.path.abspath(SPEC))`), внутри есть множество относительных путей (`os.path.join(ROOT, 'assets', ...)` и т.п.). Переносить можно ТОЛЬКО если параллельно поправишь все относительные пути внутри и команду запуска (`pyinstaller build/spec/signer.spec --noconfirm`) в `prepare_release.bat`. Если не уверен — оставь в корне.
- `.gitignore`, `.gitattributes` — по конвенции git ищет их в корне (для `.gitattributes` можно класть в подпапки, но глобальный — в корне).
- Пакеты: `app/`, `core/`, `configs/`, `processing/`, `server/`, `ui/`, `updater/`, `licensing/`.
- Ресурсы, используемые через `resource_path()`/PyInstaller `datas`: `templates/`, `static/`, `assets/`, `small_models/`, `CNN_side/`, `lane_guidance_models/`, `sings/`, `sings_text/`, `installer/`.
- `tests/` — не переносить (или переносить только вместе с правкой всех относительных путей внутри тестов — не рекомендуется в рамках этой задачи).

### Категория B — можно и нужно перенести
Типичные кандидаты (сверь с реальным содержимым репозитория и подтверди grep'ом, что путь больше нигде не хардкожен):
- Разрозненные `.md`-отчёты в корне (кроме `README.md`) → `docs/`.
- `CHECKLIST.md` и подобные рабочие чек-листы → `docs/`.
- `signer-license-server/` — это отдельный поддиректорий-подпроект (свой `requirements.txt`, свои тесты, свой Dockerfile). Если он торчит прямо в корне репозитория верхнего уровня — оставь как есть (это самостоятельный сервис, README прямо говорит "не трогать при клиентской разработке"), просто зафиксируй это явно в отчёте, не перемещай.
- Любые случайно оставленные в корне лог-файлы, `*.log`, временные файлы, `checkpoint.pkl` — удалить (они и так в `.gitignore`), не архивировать.
- `scripts/` уже существует и уже используется как место для батников/PowerShell/Python-скриптов сборки — если найдёшь скрипты сборки/дева, лежащие прямо в корне (не в `scripts/`), перенеси их в `scripts/build/` или `scripts/dev/` по аналогии с уже существующей структурой.

### Категория C — сомнительные, требуют grep перед переносом
- `README.md` — обычно остаётся в корне (GitHub его показывает только оттуда). Не переносить.
- `requirements*.txt` — можно оставить в корне (стандарт), либо создать `requirements/` и положить туда, обновив все места, где их читают: `requirements-dev.txt`/`prepare_release.bat`/CI, если есть. По умолчанию — оставь в корне, это не мусор, а стандартная конвенция.

---

## ШАГ 2 — Правило "если переносишь — обнови всё"

Для КАЖДОГО файла, который решишь перенести:

1. `grep -rn "<точное_имя_файла>" --include="*.py" --include="*.bat" --include="*.ps1" --include="*.spec" --include="*.md" --include="*.json" --include="*.ini" --include="*.cfg" .`
2. Найди все места, где путь к файлу зашит как строка (импорт, `open(...)`, `resource_path(...)`, аргумент CLI в `.bat`/`.ps1`, `datas`/`hiddenimports` в `.spec`, `pathex` и т.п.).
3. Обнови каждое найденное место на новый путь.
4. Прогони соответствующий скрипт/тест, чтобы убедиться, что путь резолвится.

Не переноси файл "на будущее исправить потом" — либо переносишь и чинишь ссылки сразу, либо не переносишь вообще.

---

## ШАГ 3 — Итоговая структура (ориентир)

После наведения порядка корень должен выглядеть примерно так (то, что не в списке — уже было в подпапках и не трогается):

```
main.py
requirements.txt
requirements-dev.txt
requirements-cpu-backends.txt
version.json
build_config.json.example
signer.spec
updater.spec
.gitignore
.gitattributes
README.md
app/
core/
configs/
processing/
server/
ui/
updater/
licensing/
templates/
static/
assets/
small_models/
CNN_side/
lane_guidance_models/
sings/
sings_text/
installer/
tests/
scripts/            <- все батники/ps1/py-скрипты сборки и разработки, включая перенесённые
docs/               <- все разрозненные .md отчёты, чек-листы
signer-license-server/   <- отдельный поддиректорий, не трогать
```

Если в текущем репозитории корень уже примерно такой — значит, реорганизация минимальна: просто убери случайный мусор (логи, отчёты) и подтверди структуру в отчёте. Не выдумывай лишних перемещений там, где всё уже аккуратно.

---

## ШАГ 4 — Проверка после реорганизации (обязательно перед коммитом)

После каждого блока перемещений прогони:

```bash
# 1. Синтаксис и импорты не сломаны
python -c "import ast, pathlib
for p in pathlib.Path('.').rglob('*.py'):
    if 'venv' in p.parts or '.git' in p.parts: continue
    ast.parse(p.read_text(encoding='utf-8', errors='ignore'))
print('OK: все .py файлы синтаксически валидны')"

# 2. Приложение стартует достаточно далеко, чтобы понять, что пути к ресурсам не сломаны
#    (не обязательно поднимать GUI полностью, но импорт основных модулей должен пройти)
python -c "
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
from app.utils import resource_path
import configs.config, configs.settings, configs.sign_data
print('resource_path(\"small_models/blue.pt\") ->', resource_path('small_models/blue.pt'))
assert os.path.exists(resource_path('small_models/blue.pt')), 'ПУТЬ К МОДЕЛИ СЛОМАН'
print('OK: базовые импорты и путь к ресурсам работают')
"

# 3. Существующие regression-тесты, которые читают файлы по относительным путям
python tests/check_eager_loading.py
python tests/check_dashboard_page.py
python tests/check_socketio_config.py

# 4. Полный прогон pytest там, где он есть
python -m pytest tests/ -v --tb=short || true   # изучи вывод, не игнорируй новые падения
```

Если что-то из этого падает **из-за твоих перемещений** — откати последний коммит и почини путь, прежде чем двигаться дальше.

---

## ШАГ 5 — ОБЯЗАТЕЛЬНО: экспорт CPU-бэкендов ONNX и OpenVINO

Это не опционально. `signer.spec` при сборке явно **прерывает билд с `RuntimeError`**, если:
- не установлены пакеты `onnxruntime` и/или `openvino`;
- не найдено ни одного экспортированного `.onnx` файла в `CNN_side/`, `lane_guidance_models/`, `small_models/`;
- не найдено ни одной директории `*_openvino_model` там же.

### 5.1. Установить зависимости

```bash
pip install -r requirements-cpu-backends.txt
# либо явно:
pip install "onnx>=1.22.0" "onnxruntime>=1.29.0" "openvino>=2024.0" "openvino-dev>=2024.0"
```

Проверь, что НЕ установлен конфликтующий `onnxruntime-gpu` (в requirements-cpu-backends.txt есть явное предупреждение об этом):

```bash
pip show onnxruntime-gpu 2>/dev/null && echo "УДАЛИ onnxruntime-gpu: pip uninstall -y onnxruntime-gpu" || echo "OK: onnxruntime-gpu не установлен"
```

### 5.2. Найти и прочитать существующий скрипт экспорта

В проекте уже должен быть `scripts/export_models_onnx.py` (на него ссылаются `signer.spec`, `prepare_release.bat`, `ui/widgets/settings_page.py::_export_models`). Найди его:

```bash
find . -iname "export_models_onnx.py" -not -path "*/venv/*"
```

- **Если файл существует** — прочитай его, пойми, какие модели он обходит (должно быть минимум: `CNN_side/best.pt`, `small_models/rude.pt`, все модели из `configs/sign_models.py::model_dict` и `sub_models`, `lane_guidance_models/arrow_detect.pt`, `lane_guidance_models/arrow_segment.pt`), и просто запусти:

  ```bash
  python scripts/export_models_onnx.py --format all
  ```

- **Если файла нет** — создай его сам в `scripts/export_models_onnx.py`. Он обязан:
  1. Принимать `--format {onnx,openvino,all}`.
  2. Обойти ВСЕ модели, перечисленные в `configs/sign_models.py`:
     - `model_side_detect` → `CNN_side/best.pt` (task="detect")
     - `rube_modal` → `small_models/rude.pt` (task="classify")
     - все ключи `model_dict`: `blue`, `treugolnik`, `krug`, `red`, `servises`, `tablichkaL` (файл `small_models/tabl l.pt`), `tablichka__` (файл `small_models/tabl.pt`), `tupic`, `5.38`, `5.9.1-5.14`, `5.5-5.6` (файл `small_models/one_side.pt`)
     - все ключи `sub_models`: `danger`, `pimicanie`, `suzenie`
     - `model_lane_detect` → `lane_guidance_models/arrow_detect.pt` (task="detect")
     - `model_lane_segment` → `lane_guidance_models/arrow_segment.pt` (task="segment")
  3. Для каждой модели использовать `ultralytics.YOLO(pt_path)` и вызвать `.export(format="onnx", ...)` и `.export(format="openvino", ...)` (Ultralytics поддерживает оба формата "из коробки").
  4. Результат ONNX должен лечь **рядом с исходным `.pt`**, с тем же именем и расширением `.onnx` (см. `configs/sign_models.py::_p_onnx`, который просто заменяет расширение `.pt` → `.onnx` в том же пути).
  5. Результат OpenVINO должен лечь **рядом с исходным `.pt`**, в директорию `<basename>_openvino_model/` (см. `configs/sign_models.py::_p_openvino`, который берёт `basename без .pt + "_openvino_model"`).
  6. Обязательно предусмотреть обработку файлов с пробелами в имени (`small_models/tabl l.pt`) — экранировать/использовать `pathlib.Path`, не `shlex`-разбивать вручную.
  7. Логировать прогресс по каждой модели (успех/ошибка), но не падать на первой ошибке — собрать всё, что получится, и вывести сводку в конце.
  8. Вернуть ненулевой exit code, если хотя бы одна модель не экспортировалась хотя бы в один из форматов.

### 5.3. Проверить результат экспорта руками

```bash
echo "=== ONNX модели ==="
find CNN_side small_models lane_guidance_models -iname "*.onnx" 2>/dev/null

echo "=== OpenVINO модели ==="
find CNN_side small_models lane_guidance_models -type d -iname "*_openvino_model" 2>/dev/null
```

Сопоставь список с полным списком моделей из `configs/sign_models.py` (см. п. 5.2.2 выше). Если чего-то не хватает — разберись почему (обычно: опечатка в имени файла с пробелом, отсутствующий класс, ошибка версии ultralytics) и доэкспортируй руками для конкретной модели:

```bash
python -c "
from ultralytics import YOLO
m = YOLO('small_models/tabl l.pt')
m.export(format='onnx')
m.export(format='openvino')
"
```

### 5.4. Прогнать/создать верификатор бэкендов

`prepare_release.bat` вызывает `scripts/build/verify_cpu_backends.py`. Найди его:

```bash
find . -iname "verify_cpu_backends.py" -not -path "*/venv/*"
```

- **Если есть** — запусти:
  ```bash
  python scripts/build/verify_cpu_backends.py
  ```
  Он должен явно для каждой модели напечатать, какой backend реально загрузился (`torch`/`onnx`/`openvino`), опираясь на `configs.sign_models._LazyModel._backend` после принудительной загрузки (`verify_backend_active()` из `configs/sign_models.py` уже есть в проекте и делает именно это — можно и нужно на неё опереться).

- **Если файла нет** — создай его в `scripts/build/verify_cpu_backends.py`. Он должен:
  1. Временно выставить в `configs.settings.get_app_settings()`: `use_cuda = False`, по очереди `cpu_inference_backend = "onnx"`, затем `"openvino"`.
  2. После каждой установки сбросить кэш моделей (`_model = None`, `_device = None`, `_backend = None` для всех `_LazyModel` из `configs/sign_models.py`, как это уже делает `reload_all_models_if_device_changed()`).
  3. Вызвать `configs.sign_models.verify_backend_active()` и получить `{имя_модели: backend}`.
  4. Проверить, что для КАЖДОЙ модели `backend == cpu_inference_backend`, который был запрошен (никакого тихого отката на `torch`).
  5. Пропустить через модель тестовое изображение (`numpy.zeros((32,32,3), dtype=uint8)` для классификаторов, побольше — для detect/segment) и убедиться, что вызов не бросает исключение и возвращает результат.
  6. Напечатать финальную таблицу `модель | запрошенный backend | реальный backend | статус`.
  7. Вернуть exit code 1, если хоть одна модель не на нужном backend или упала при инференсе.

Прогони его дважды (ты уже должен был это включить в сам скрипт, но продублируй здесь при необходимости отдельными запусками с явной проверкой):

```bash
python -c "
from configs.settings import get_app_settings
s = get_app_settings(); s.use_cuda = False; s.cpu_inference_backend = 'onnx'; s.save()
"
python scripts/build/verify_cpu_backends.py

python -c "
from configs.settings import get_app_settings
s = get_app_settings(); s.use_cuda = False; s.cpu_inference_backend = 'openvino'; s.save()
"
python scripts/build/verify_cpu_backends.py
```

Не считай задачу выполненной, пока таблица не покажет **все** модели на запрошенном backend без ошибок.

---

## ШАГ 6 — Финальная сверка перед коммитом

```bash
git status
git diff --stat
```

Проверь:
- [ ] Ничего из Категории A (пакеты, ресурсы, `main.py`, spec-файлы, `version.json`, `build_config.json*`) не переместилось.
- [ ] Всё, что переместилось из Категории B/C, имеет обновлённые ссылки (grep подтверждает отсутствие старых путей).
- [ ] `python -m pytest tests/ -v` не показывает новых падений по сравнению с состоянием до твоих изменений (сравни явно, прогнав тесты и на исходной ветке).
- [ ] `find . -iname "*.onnx"` и `find . -type d -iname "*_openvino_model"` покрывают ВСЕ модели из `configs/sign_models.py`.
- [ ] `scripts/build/verify_cpu_backends.py` проходит и для `onnx`, и для `openvino` без единого отката на `torch`.
- [ ] `git log --oneline` показывает атомарные, понятные коммиты (не один гигантский коммит "reorganize everything").

---

## ШАГ 7 — Отчёт

В конце работы предоставь:

1. Таблицу "было → стало" для каждого перемещённого файла.
2. Список файлов Категории A, которые ты **сознательно не трогал**, с однострочным обоснованием (можно взять формулировки из раздела "КРИТИЧЕСКИ ВАЖНОЕ ОГРАНИЧЕНИЕ" выше).
3. Полный список экспортированных `.onnx` файлов и `*_openvino_model` директорий.
4. Вывод `scripts/build/verify_cpu_backends.py` для обоих backend'ов (лог, не пересказ).
5. Результат `python -m pytest tests/ -v` до и после изменений.
6. Явное предупреждение, если что-то из требуемого не удалось выполнить, — с указанием причины и что нужно от человека (например, отсутствующая системная зависимость, недоступный `.pt` файл и т.п.). **Не приукрашивай и не замалчивай частичный результат.**
