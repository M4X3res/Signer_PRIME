Промпт для агента: реорганизация структуры проекта RoadScanner (Signer PRIME)

Цель: привести структуру репозитория в порядок — разложить файлы по логическим папкам, в корне оставить только main.py и минимально необходимые файлы конфигурации/сборки, при этом приложение должно продолжать работать без единой сломанной ссылки: все импорты, resource_path()-пути, пути в .spec-файлах, батниках и скриптах сборки должны быть исправлены.

0. Подготовка
Перед началом сделай git status — рабочая копия должна быть чистой. Если нет, останови работу и попроси закоммитить/застэшить изменения.
Все перемещения файлов делай через git mv, чтобы сохранить историю.
После каждого крупного шага (перенос группы файлов) — коммить отдельно с понятным сообщением (refactor: move updater files to updater/), чтобы изменения было легко проверить и откатить при необходимости.
Не трогай папки, которые уже являются пакетами и логически на своём месте: core/, configs/, processing/, server/, ui/, scripts/, installer/, templates/, а также каталоги с бинарными моделями (small_models/, lane_guidance_models/, CNN_side/) и static//sings*/ (они в .gitignore, их пути жёстко используются через resource_path, лучше не двигать без крайней необходимости).
1. Целевая структура корня

После рефакторинга в корне должны остаться только:

main.py
requirements.txt
requirements-dev.txt
requirements-cpu-backends.txt
README.md
.gitignore
.gitattributes
version.json
signer.spec
updater.spec

Всё остальное, что сейчас лежит в корне как отдельный .py/.md/.bat/.ps1 файл, нужно разложить по папкам ниже.

2. Куда что переносить

app/ (новый пакет для модулей, обслуживающих сам процесс запуска, не относящихся к конкретному core-домену):

utils.py → app/utils.py
version.py → app/version.py

updater/ (новый пакет, изолированная система автообновлений):

updater.py → updater/updater.py
updater_main.py → updater/updater_main.py
добавь updater/__init__.py (пустой, чтобы не ломать import updater — либо сохрани публичный API через реэкспорт, см. п.4)

scripts/build/ (всё, что связано со сборкой/релизом, но не с dev-отладкой — scripts/dev/ уже существует и не трогается):

build.bat
test_update.bat
upload_release.ps1
scripts/build_release_manifest.py (уже в scripts/, просто перенести на уровень ниже в scripts/build/)
scripts/export_models_onnx.py можно оставить как есть в scripts/, если не мешает — на усмотрение, главное единообразие.

docs/ (вся документация и отчёты, кроме README.md):

BUILD_INSTRUCTIONS.md
BUILD_AUTOUPDATE.md
AUTOUPDATE_IMPLEMENTATION_REPORT.md
CHANGES_7Z.md
release_notes.txt
(если в проекте уже есть каталог docs/ — слить с ним, не создавать дублирующий).

assets/data/ или configs/data/ (статические данные, не код):

signs.json → configs/data/signs.json (согласуй с тем, как он сейчас читается через resource_path("signs.json") в коде — найди все обращения).

Не переносить, но проверить:

assets/7ZA_README.md — оставить в assets/, это уже правильное место.
installer/SignerInstaller.iss — уже на месте.
3. Обязательный поиск и правка всех ссылок

Для КАЖДОГО перенесённого файла выполни:

grep -rn "import utils\|from utils\|import version\|from version\|import updater\|from updater\|updater_main\|signs\.json\|build\.bat\|export_models_onnx" . (и аналогично для каждого перенесённого имени) по всему репозиторию, включая:
Python-импорты (import X, from X import Y)
resource_path(...) вызовы (utils.py::resource_path)
пути в signer.spec / updater.spec (datas=[...], hiddenimports=[...])
пути в .bat/.ps1/.iss скриптах
пути в markdown-документации (BUILD_INSTRUCTIONS.md и т.п. — обнови команды типа pyinstaller signer.spec если расположение файлов сборки изменилось)
sys.path.insert(...) конструкции в dev-скриптах (scripts/dev/*.py часто добавляют sys.path.insert(0, os.path.dirname(...)) — проверь, что относительные вычисления Path(__file__).parent всё ещё указывают куда нужно после переноса)
Обнови импорты на новые пути пакетов, например:
import utils → from app import utils (или import app.utils as utils, сохраняя обратную совместимость через from app.utils import resource_path везде, где раньше было from utils import resource_path)
from version import APP_VERSION → from app.version import APP_VERSION
import updater → from updater import updater либо переименуй модуль внутри пакета — главное, чтобы updater.check_for_update(), updater.launch_updater_and_exit(), updater.UpdateInfo, updater.cleanup_stale_update_temp() продолжали резолвиться так же, как раньше (эти имена используются в main.py, ui/widgets/update_worker.py, ui/widgets/update_dialog.py, ui/widgets/settings_page.py).
Особое внимание: version.py::_get_version_file_path() вычисляет путь к version.json через Path(__file__).parent (для dev-режима) — после переноса version.py в app/ это сломает путь к version.json, который остаётся в корне. Исправь на Path(__file__).parent.parent / "version.json" (или аналогичную корректную навигацию).
updater.py использует Path(__file__).parent / "installer" / SEVEN_ZIP_EXE и Path(__file__).parent / "dist" / "Signer" / "Signer.exe" в dev-режиме — после переноса в updater/ поправь на Path(__file__).parent.parent / "installer" / ... и т.д.
4. Обратная совместимость импортов (важно для минимизации диффа)

Вместо правки каждого места использования import utils, import version, import updater по всему проекту, можно (и это предпочтительнее там, где вызовов много):

Создать app/__init__.py, который ничего не делает.
В корне создать тонкие shim-модули только если это реально уменьшает риск, например updater.py в корне как from updater.updater import * — но это плохо согласуется с требованием "в корне только main.py". Поэтому лучше явно обновить все места использования, а не городить shim-модули в корне. Приоритет — чистота корня, а не минимальный дифф.

Сделай явную правку импортов везде, где это находится через grep, включая:

main.py
ui/widgets/update_worker.py
ui/widgets/update_dialog.py
ui/widgets/settings_page.py
processing/ocr_worker.py, processing/ocr_pool.py, core/detector.py (используют from utils import resource_path)
configs/sign_models.py (from utils import resource_path)
server/map_server.py (from utils import resource_path)
любые файлы в scripts/dev/, использующие from utils import resource_path или from version import APP_VERSION.
5. Правка signer.spec и updater.spec
Найди все datas=[...], hiddenimports=[...], Analysis(['main.py'], ...) записи, которые ссылаются на перенесённые файлы (version.json, updater.py, updater_main.py, utils.py, signs.json).
Обнови hiddenimports на новые пути модулей (app.utils, app.version, updater.updater, updater.updater_main).
Проверь, что version.json по-прежнему копируется в datas рядом с exe (он остаётся в корне репозитория — не переносится).
6. Правка build-скриптов и документации
В build.bat, BUILD_INSTRUCTIONS.md, BUILD_AUTOUPDATE.md замени любые относительные пути к перенесённым .bat/.ps1/.py файлам (например, если сам build.bat теперь лежит в scripts/build/build.bat, но должен запускаться из корня — либо добавь cd /d "%~dp0..\.." в начало скрипта, либо обнови инструкции запускать его как scripts\build\build.bat).
Обнови upload_release.ps1 аналогично, если он ссылается на относительные пути к архивам.
7. Проверка после переноса

Выполни последовательно и покажи вывод:

python -c "import main" — не должно быть ImportError/ModuleNotFoundError на этапе импорта верхнего уровня (сам main.py — точка входа, но проверь хотя бы синтаксис через python -m py_compile main.py app/*.py updater/*.py).
grep -rn "^import utils\|^from utils\|^import version\|^from version\|^import updater\b" . — результат должен быть пуст или содержать только новые корректные импорты (from app.utils import ... и т.п.), не должно остаться битых ссылок на старые пути.
grep -rln "utils.py\|version.py\|updater.py\|updater_main.py" -- '*.spec' '*.bat' '*.ps1' '*.md' — вручную пройдись по найденным упоминаниям и убедись, что пути обновлены.
Собери дерево каталогов (tree -L 2 или аналог) и приложи в итоговом отчёте — это финальный чек, что корень содержит только перечисленный в п.1 набор файлов.
8. Отчёт

В конце выведи:

Полный список выполненных git mv (откуда → куда).
Список всех файлов, где были изменены импорты/пути (с указанием, что именно поменялось).
Итоговое дерево корня проекта.
Если что-то не удалось перенести безопасно (например, скрипт использует хардкод пути, который сложно вычислить программно) — явно перечисли это как TODO, а не тихо пропускай.

Критично: ничего не удаляй безвозвратно, не меняй бизнес-логику файлов — только их расположение и импорт-пути. Если сомневаешься, переносить ли конкретный файл (например, если неясно, ссылается ли на него внешний CI/инсталлятор) — сначала найди все ссылки на него через grep и покажи их, прежде чем переносить.