# Промпт для AI-агента: восстановить проект после неудачной обфускации и починить сборку релиза

## Контекст (что произошло)

Один из предыдущих ИИ-агентов реализовывал ЗАДАЧУ 3 из `HARDEN_LICENSING` — обфускацию
модуля `licensing/` через PyArmor перед сборкой релиза (`scripts/build/prepare_release.bat`,
шаг `[3/7] Obfuscating licensing modules with PyArmor...`, вызывает
`scripts\build\obfuscate_licensing.py`, а после сборки —
`scripts\build\restore_originals.py`).

В процессе агент один раз прогнал обфускацию, потом откатывал файлы обратно
("восстанавливал оригиналы"), но откат прошёл не полностью и/или зафиксировал в git
промежуточное состояние. Результат:

1. **Приложение падает при старте** — `ui/widgets/settings_page.py` и
   `ui/widgets/license_dialog.py` делают
   `from licensing.license_manager import LicenseManager, LicenseStatus, PLAN_DISPLAY_NAMES`,
   но в текущем `licensing/license_manager.py` символ `PLAN_DISPLAY_NAMES` **не определён
   вообще**. Это `ImportError` при первом же открытии `SettingsPage` или диалога лицензии —
   то есть фактически при каждом запуске `main.py` (см. `main.py`, блок показа
   `LicenseDialog`).

2. **Логика защиты от dev-ключа в проде потеряна.** `tests/test_licensing.py`
   (`TestProductionKeyCheck`) и `tests/test_fixes_manual.py` ожидают в
   `licensing/public_key.py`:
   - константу `DEV_KEY_SHA256` — SHA-256 хэш текущего (тестового/dev) значения
     `LICENSE_PUBLIC_KEY_PEM`;
   - модуль-левел проверку (выполняется при **импорте/reload** модуля), которая при
     `getattr(sys, "frozen", False) is True` **и** совпадении хэша текущего
     `LICENSE_PUBLIC_KEY_PEM` с `DEV_KEY_SHA256` — кидает `RuntimeError` с текстом,
     содержащим подстроку «тестовый публичный ключ» (без учёта регистра).
   Сейчас в `licensing/public_key.py` этого кода нет — ни константы, ни проверки. Это значит,
   что **frozen-сборка теоретически может уехать в прод с dev-ключом Ed25519** и никто об
   этом не узнает, а заодно оба теста падают с `AttributeError`/`ImportError`.

3. **Скрипты обфускации отсутствуют в репозитории.** `scripts/build/prepare_release.bat`
   безусловно вызывает:
   - `.venv\Scripts\python.exe scripts\build\obfuscate_licensing.py` (шаг 3/7),
   - `.venv\Scripts\python.exe scripts\build\restore_originals.py` (после сборки, шаг 4/7,
     причём **в двух местах**: при ошибке сборки Signer.exe/Updater.exe и в штатном пути).
   Ни `scripts/build/obfuscate_licensing.py`, ни `scripts/build/restore_originals.py` не
   существуют (в дереве проекта их нет). Из-за этого `prepare_release.bat` либо падает на
   шаге 3, либо (если раньше существовал script, который потом удалили) молча продолжает
   работу без реальной обфускации, либо — в худшем случае — оставляет `licensing/*.py`
   перезаписанными обфусцированным кодом навсегда, если `restore_originals.py` не
   отработал. Судя по `signer.spec` (комментарии про
   `build/obfuscated/pyarmor_runtime_XXXXXX/` и `licensing/pyarmor_runtime_XXXXXX/`), схема
   обфускации задумывалась так:
   - PyArmor генерирует **два независимых runtime** — один для `main.py` (кладётся в корень
     сборки), второй для `licensing/*.py` (кладётся в `licensing/`);
   - результат обфускации должен оказаться в `build/obfuscated/...` с сохранением
     относительной структуры путей, чтобы `signer.spec` мог собрать оттуда
     `pyarmor_runtime_*` директории через `glob.glob(os.path.join(_obfuscated_root, '**',
     'pyarmor_runtime_*'), recursive=True)` и разложить их по `_internal/` (корень и
     `_internal/licensing/` соответственно);
   - но сам `Analysis(['main.py'], pathex=[ROOT], ...)` в `signer.spec` анализирует код
     **из корня репозитория**, а не из `build/obfuscated/` — значит, реальные обфусцированные
     `.py`-файлы должны на момент сборки PyInstaller **временно подменять** оригиналы прямо в
     `licensing/` (и, если нужно, `main.py`) в корне репозитория, а `build/obfuscated/` служит
     побочным местом, откуда PyArmor кладёт свои `pyarmor_runtime_*` для последующего сбора в
     `datas`. После сборки оригиналы должны быть восстановлены **гарантированно**, даже если
     сборка упала с ошибкой.

4. Тестовый набор `scripts/dev/run_all_tests.bat` тоже завязан на это: шаг 2/3 гоняет
   `tests/test_licensing.py`, который сейчас падает именно из-за пп. 1–2.

## Твоя задача

Работай итеративно, шаг за шагом, и после каждого шага прогоняй релевантные тесты
(`python -m pytest tests/test_licensing.py -v`, `python tests/test_fixes_manual.py`,
`python tests/test_main_import_manual.py`, `python tests/test_client_init_manual.py`).
Не переходи к следующему шагу, пока текущий не проходит тесты.

### Шаг 1. Восстановить `licensing/license_manager.py`: добавить `PLAN_DISPLAY_NAMES`

Добавь на уровне модуля словарь соответствия внутренних кодов плана человекочитаемым
названиям на русском. Ключи должны как минимум покрывать все значения `plan`, которые
реально встречаются в системе: `"monthly"`, `"quarterly"`, `"yearly"`, `"internal"` (см.
`signer-license-server/app/schemas.py::CreateLicenseRequest.plan` — паттерн
`^(monthly|quarterly|yearly|internal)$`, и `signer-license-server/app/services/email_service.py`,
где уже есть аналогичный маппинг `plan_names` — используй его как образец формулировок):

```python
PLAN_DISPLAY_NAMES: dict[str, str] = {
    "monthly":   "Месячная подписка",
    "quarterly": "Подписка на 3 месяца",
    "yearly":    "Годовая подписка",
    "internal":  "Внутренняя лицензия",
}
```

Экспортируй символ так, чтобы `from licensing.license_manager import LicenseManager,
LicenseStatus, PLAN_DISPLAY_NAMES` (уже используется в `ui/widgets/settings_page.py` и
`ui/widgets/license_dialog.py`) работал без изменений в этих двух файлах — то есть не
переименовывай и не переноси константу в другой модуль. При желании дополнительно
реэкспортируй её через `licensing/__init__.py` (`__all__ += ["PLAN_DISPLAY_NAMES"]`), но это
не обязательно, раз импорт идёт напрямую из подмодуля.

Проверка: `python tests/test_main_import_manual.py` должен пройти без `NameError`; ручной
запуск `main.py` должен доходить до `LicenseDialog`/`SettingsPage` без `ImportError`.

### Шаг 2. Восстановить проверку dev-ключа в `licensing/public_key.py`

Добавь:

1. Импорт `hashlib` и `sys`, если их ещё нет.
2. Константу `DEV_KEY_SHA256` — **вычисленный заранее** SHA-256 hex-дайджест текущего
   значения `LICENSE_PUBLIC_KEY_PEM` (того самого dev/test-ключа, который сейчас в файле).
   Вычисли его один раз (например, `hashlib.sha256(LICENSE_PUBLIC_KEY_PEM.encode()).hexdigest()`)
   и впиши как строковый литерал — не вычисляй хэш от самого себя динамически в рантайме
   (иначе проверка станет тавтологией и никогда не сработает для реального прод-ключа).
3. Функцию `_check_production_key()`, вызываемую **на уровне модуля** (то есть один раз при
   импорте/`importlib.reload`), которая:
   - вычисляет текущий хэш `LICENSE_PUBLIC_KEY_PEM`;
   - если `getattr(sys, "frozen", False)` истинно **и** вычисленный хэш совпадает с
     `DEV_KEY_SHA256` — кидает `RuntimeError` с понятным сообщением, содержащим (без учёта
     регистра) подстроку «тестовый публичный ключ», например:
     `"КРИТИЧЕСКАЯ ОШИБКА: в frozen-сборке используется тестовый публичный ключ Ed25519. "
     "Перед выпуском релиза сгенерируйте боевую пару ключей "
     "(scripts/generate_ed25519_keys.py) и замените LICENSE_PUBLIC_KEY_PEM."`
   - если условие не выполняется — ничего не делает (no-op), импорт проходит тихо.
4. Вызови `_check_production_key()` сразу после определения константы `LICENSE_PUBLIC_KEY_PEM`
   и `DEV_KEY_SHA256`, на уровне модуля (не внутри `if __name__ == "__main__":`).

Ограничение: это ДОЛЖНО быть согласовано с `tests/test_licensing.py::TestProductionKeyCheck`,
который патчит `sys.frozen` и `pk_module.LICENSE_PUBLIC_KEY_PEM`, а затем делает
`importlib.reload(pk_module)` — то есть твоя проверка обязана выполняться именно при
повторном выполнении тела модуля (обычный код на уровне модуля этому условию
удовлетворяет, не прячь её внутрь функции, которую никто не вызывает).

Проверка: `python -m pytest tests/test_licensing.py::TestProductionKeyCheck -v` — оба теста
зелёные; `python tests/test_fixes_manual.py` — ЗАДАЧА 1 печатает
«✅ ЗАДАЧА 1: DEV_KEY_SHA256 совпадает с реальным хэшем!».

### Шаг 3. Прогнать полный licensing-тест-сьют

```
python -m pytest tests/test_licensing.py -v
python tests/test_main_import_manual.py
python tests/test_client_init_manual.py
python tests/test_fixes_manual.py
```

Все должны быть зелёными. Если `test_client_init_manual.py` или
`licensing/license_client.py` всё ещё содержат следы старого бага с `REQUESTS_AVAILABLE`
(`NameError` при создании `LicenseClient()`), почини по аналогии — в текущей версии файла
баг уже похоже исправлен, но перепроверь на всякий случай.

### Шаг 4. Написать `scripts/build/obfuscate_licensing.py` (с нуля, аккуратно)

Требования к поведению скрипта:

1. **Идемпотентность и безопасность.** Перед стартом скрипт обязан убедиться, что
   предыдущий прогон не оставил проект в грязном состоянии (например, проверить наличие
   файла-маркера/бэкапа от незавершённого прошлого запуска и явно предупредить/отказаться
   работать, а не тихо перезаписать бэкап).
2. **Что обфусцируем.** Как минимум: все `.py` файлы в `licensing/` (`__init__.py`,
   `license_manager.py`, `license_client.py`, `device_fingerprint.py`, `public_key.py`) и,
   если такова задумка (`signer.spec` явно ожидает **отдельный** runtime для `main.py` в
   корне), также `main.py`. НЕ обфусцируй ничего лишнего — не трогай `ui/`, `core/`,
   `processing/`, `configs/` и т.д.
3. **Бэкап оригиналов перед обфускацией.** Перед тем как перезаписать `licensing/*.py` (и,
   если применимо, `main.py`) обфусцированным кодом, скопируй ВСЕ оригинальные файлы в
   заранее известное безопасное место, например `build/obfuscated_backup/` (сохраняя
   относительные пути), и запиши манифест (JSON со списком файлов + их исходным содержимым
   или просто списком путей — этого достаточно, раз есть копии). Это единственный источник
   истины для `restore_originals.py`.
4. **Вызов PyArmor.** Используй PyArmor 9.x API (`pyarmor gen` через `subprocess`, либо
   Python API если такой используется в проекте — сверься, что реально установлено через
   `requirements-dev.txt`, где зафиксировано `pyarmor>=9.0.0`). Сгенерируй обфусцированные
   версии:
   - `licensing/*.py` → обфусцируй КАК ПАКЕТ (`pyarmor gen -O licensing --recursive
     licensing`, либо построчно для каждого файла, но так, чтобы получившийся
     `pyarmor_runtime_*` лёг **внутрь `licensing/`** — именно это подразумевает
     `signer.spec` комментарием `"licensing/pyarmor_runtime_XXXXXX (для licensing/*.py)"`, и
     флаг `-i` (in-place / "pack into obfuscated output alongside package"), который
     упоминается в `scripts/dev/commit_and_push.bat`/`quick_commit.bat` в коммит-месседжах
     ("Use -i flag for packages to place runtime inside") — используй именно этот флаг,
     чтобы результат был **предсказуемым и фиксированным путём**
     (`licensing/pyarmor_runtime_000000/`), а не рос новыми папками `pyarmor_runtime_*` при
     каждой пересборке (это явно описано как отдельный баг, который уже когда-то чинили —
     не наступи на те же грабли снова);
   - `main.py` → обфусцируй отдельно (без `-i` внутрь пакета, т.к. это одиночный модуль в
     корне), так, чтобы runtime лёг рядом с ним в корне (`pyarmor_runtime_000000/` в корне
     проекта).
5. **Перезапись оригиналов** обфусцированными файлами — ТОЛЬКО после успешного шага 4 и
   ТОЛЬКО после того, как бэкап (шаг 3) подтверждённо на диске.
6. **Копия результата в `build/obfuscated/`** — дублируй итоговую структуру
   (`build/obfuscated/main.py` + `build/obfuscated/pyarmor_runtime_*/`,
   `build/obfuscated/licensing/...` + `build/obfuscated/licensing/pyarmor_runtime_*/`), чтобы
   `signer.spec` мог найти `pyarmor_runtime_*` через свой `glob` (см. код в `signer.spec`,
   секция "PyArmor runtime"). Не обязательно, чтобы `build/obfuscated/` содержал реально
   рабочий код — `signer.spec` использует его только как источник `datas` для
   `pyarmor_runtime_*` директорий, реальный код PyInstaller возьмёт напрямую из корня
   (уже обфусцированный на этот момент).
7. **Коды возврата.** `exit(1)` при любой ошибке PyArmor/копирования, чтобы
   `prepare_release.bat` (который проверяет `errorlevel 1` после вызова) корректно прервал
   сборку и НЕ продолжил с наполовину обфусцированным деревом.
8. **Логирование** каждого шага в stdout в том же стиле, что и остальные `build`-скрипты
   (эмодзи-маркеры уже используются в `prepare_release.bat` и `upload_release.ps1` — не
   обязательно повторять, но полезно для консистентности; главное — понятные сообщения об
   ошибках).

### Шаг 5. Написать `scripts/build/restore_originals.py`

1. Прочитать манифест/бэкап из `build/obfuscated_backup/`, созданный на шаге 4.
2. Восстановить КАЖДЫЙ оригинальный файл на его исходное место, побайтово идентично
   исходнику (используй `shutil.copy2`, не полагайся на перегенерацию).
3. **Обязательно должен отрабатывать даже если сборка PyInstaller упала** —
   `prepare_release.bat` уже вызывает его в обеих ветках (успех/ошибка сборки), поэтому сам
   скрипт должен быть устойчив к состоянию "файлы уже частично не обфусцированы"
   (например, если его случайно запустили дважды) — в этом случае просто идемпотентно
   восстановить то, что есть в бэкапе, и не упасть.
4. После успешного восстановления — верификация: сравнить хэш каждого восстановленного
   файла с хэшем из бэкапа; если не совпало — `exit(1)` с явной диагностикой (какой файл не
   восстановился), чтобы CI/релиз-инженер сразу увидел проблему, а не закоммитил обфусцированный
   код по ошибке (именно это, судя по всему, и произошло в прошлый раз).
5. **НЕ удаляй `build/obfuscated_backup/` автоматически** сразу после восстановления —
   оставь эту очистку `prepare_release.bat` (шаг `[2/7] Cleaning old builds` в следующем
   прогоне и так удаляет `build\` целиком) либо сделай отдельным явным флагом
   `--cleanup`, чтобы не потерять единственную копию оригиналов, если верификация из п. 4
   найдёт расхождение.
6. Тот же код возврата: `0` — успех и полное совпадение хэшей, `1` — что-то не так.

### Шаг 6. Регресс-тест на сам пайплайн обфускации/восстановления

Добавь `tests/test_obfuscation_roundtrip.py` (или расширь существующий
`tests/test_licensing.py`), который:

1. Делает временную копию `licensing/` (или мокает вызов PyArmor, если он недоступен в
   тестовом окружении — оберни реальный вызов `pyarmor` в `pytest.importorskip("pyarmor")`
   / проверку наличия бинаря в PATH, чтобы тест не падал там, где PyArmor не установлен, как
   уже сделано для `onnxruntime`/`openvino` в `tests/test_cpu_thread_parity.py`).
2. Прогоняет `obfuscate_licensing.py` → проверяет, что `licensing/*.py` реально изменились
   (не совпадают побайтово с оригиналами) и что появился `licensing/pyarmor_runtime_*/`.
3. Прогоняет `restore_originals.py` → проверяет, что `licensing/*.py` **побайтово** совпали
   с оригиналами (сравнение по хэшам сохранённого до теста снапшота), и что
   `licensing/pyarmor_runtime_*/` больше нет в рабочем дереве (не должна оставаться после
   restore — иначе следующий импорт `licensing` может случайно подхватить чужой runtime).
4. Явно проверяет регрессию из этого прогона: `from licensing.license_manager import
   LicenseManager, LicenseStatus, PLAN_DISPLAY_NAMES` и `from licensing.public_key import
   DEV_KEY_SHA256` успешно импортируются и до, и после restore.

### Шаг 7. Обновить `scripts/build/prepare_release.bat`, если нужно

Файл уже содержит корректную последовательность вызовов (`[3/7]` → obfuscate,
`[4/7]` → build → restore в обеих ветках). Изменения нужны только если:
- поменялись имена аргументов/флагов твоих новых скриптов (`obfuscate_licensing.py`,
  `restore_originals.py`) — синхронизируй вызовы;
- нужно добавить дополнительную явную проверку `errorlevel 1` после `restore_originals.py`
  в "успешной" ветке (сейчас там нет проверки кода возврата restore — добавь её: если
  восстановление не удалось, релиз собирать дальше нельзя, т.к. `dist\Signer\` может быть
  единственной валидной копией и её нужно тут же скопировать в `release\` вручную/остановить
  пайплайн с явной ошибкой, а не тихо продолжать на шаге `[5/7] Creating archive`).
- добавь после шага `[4/7]` явную проверку: `git status --porcelain licensing/ main.py`
  (или сравнение хэшей) должно быть пустым — если restore не полностью откатил изменения,
  падать с понятным сообщением, а не позволять `[5/7]` заархивировать не тот код.

### Шаг 8. Финальная сквозная проверка

1. `scripts\dev\run_all_tests.bat` — все три этапа (`test_fixes_manual.py`,
   `pytest tests/test_licensing.py`, серверные тесты `signer-license-server/tests/`) зелёные.
2. Ручной прогон `python main.py` (или headless-эквивалент, если GUI недоступен в среде
   агента) не падает на `ImportError`/`NameError` при инициализации лицензирования.
3. Сухой прогон `scripts\build\prepare_release.bat` в тестовом окружении (можно с заглушкой
   PyArmor/PyInstaller, если реальные инструменты недоступны агенту) должен пройти шаги
   0–4 без падения и оставить `licensing/*.py`/`main.py` в рабочем дереве побайтово равными
   тому, что было до запуска (проверь `git diff --stat` — должен быть пустым для этих путей
   после полного прогона, кроме случая, когда сборка реально успешна и `dist/`/`release/`
   заполнены).

## Важные ограничения (не нарушать)

- Не трогай бизнес-логику лицензирования (`activate`/`refresh`/`deactivate`,
  `check_local_status`) — баг только в отсутствующих символах и утерянных скриптах, менять
  алгоритмику `LicenseManager` не нужно.
- Не меняй формат токена, Ed25519-подпись или API `signer-license-server` — это только
  клиентская сторона и build-тулинг.
- Любые новые файлы (`obfuscate_licensing.py`, `restore_originals.py`,
  `test_obfuscation_roundtrip.py`) должны быть кроссплатформенно написаны на Python (проект
  уже требует `pyarmor>=9.0.0` в `requirements-dev.txt` — используй его), даже если
  вызываются из `.bat`.
- Не удаляй и не коммить `build/`, `dist/`, `release/` — они и так в `.gitignore`.
- Каждое изменение подкрепляй тестом или ручной проверкой из соответствующего шага — не
  считай задачу выполненной по факту написания кода, только по факту прохождения проверок.
