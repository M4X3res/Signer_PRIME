# ЗАДАЧА: система автообновлений для Signer PRIME (уровня Discord/VS Code)

Ты работаешь в репозитории Signer PRIME (RoadScanner) — PyQt6-приложение, собираемое
через PyInstaller (`signer.spec`) и распространяемое через Inno Setup. У тебя есть
полный доступ к файловой системе проекта — читай существующие файлы, создавай новые,
редактируй существующие. Структура: `core/`, `configs/`, `processing/`, `server/`,
`ui/`, `templates/`, точка входа `main.py`.

Добавь в проект систему автообновлений, не ломая существующую архитектуру и не трогая
бизнес-логику детекции/обработки (`core/`, `processing/`, `configs/sign_*`). Доведи всё
до полностью рабочего состояния, включая сборку `Updater.exe`. Не останавливайся на
теории — реально создавай и правь файлы.

## Главное правило

Первая установка — только через существующий Inno Setup инсталлятор (его `.iss`-скрипт,
если найдёшь, не трогай). Все последующие обновления — БЕЗ повторного запуска
инсталлятора: скачивание архива с GitHub Releases + отдельный `Updater.exe`.

## Технологии

Python, PyQt6, `requests`, GitHub Releases REST API, 7-Zip (`7za.exe`), `hashlib`
(SHA-256), `subprocess`, `pathlib`. Никаких сторонних update-фреймворков (WinSparkle и т.п.).

## Источник обновлений

- Репозиторий: `M4X3res/Signer_PRIME`
- Endpoint: `https://api.github.com/repos/M4X3res/Signer_PRIME/releases/latest`
  (всегда latest, НЕ фиксированный тег)
- Ассеты релиза: многотомный архив `Signer.7z.001`, `Signer.7z.002`, `Signer.7z.003`, ...
  (маска `Signer.7z.*`, число томов может меняться от релиза к релизу) + файл
  `checksum.sha256`.

## Что нужно сделать — по порядку, создавая и редактируя файлы прямо сейчас

### 1. `version.py` (корень проекта)
Единственный источник версии:
```python
APP_VERSION = "2.0.0"
```
Подключи эту константу в `main.py` вместо любого захардкоженного значения версии
(например, `app.setApplicationVersion("2.0")` → `version.APP_VERSION`), и в заголовок
главного окна / стартовый лог, где это уместно, не переписывая остальную логику `main.py`.

### 2. `updater.py` (корень проекта) — логика проверки и загрузки
Изолированный модуль, не импортирующий `core/`, `processing/`, `ui/`. Содержит:
- `UpdateInfo` — dataclass: `version: str`, `release_notes: str`,
  `assets: list[tuple[str, str, int]]` (имя, url, size), `total_size_bytes: int`.
- `check_for_update() -> UpdateInfo | None` — GET к GitHub API, парсинг JSON
  (`tag_name`, `body`, `assets`), сравнение версии с `version.APP_VERSION` (простое
  semver-сравнение через `packaging.version` если доступно, иначе ручное сравнение
  кортежей чисел). Таймаут запроса, обработка отсутствия сети/404/rate-limit —
  тихо логировать через `logging.getLogger(__name__)` и вернуть `None`.
- `download_assets(assets, dest_dir: Path, progress_cb)` — скачивание всех
  `.7z.NNN`-файлов и `checksum.sha256` через `requests.get(url, stream=True)`,
  чанками по 1 MB, с вызовом `progress_cb(filename, downloaded, total, speed_bps)`
  после каждого чанка (throttled, не чаще раза в ~200мс).
- `verify_checksum(dest_dir: Path, checksum_filename="checksum.sha256") -> bool` —
  считает SHA-256 каждого скачанного `.7z.*` и сверяет со строками из файла
  чексумм; при несовпадении удаляет скачанные файлы, возвращает `False`.
- `launch_updater_and_exit(temp_dir: Path, install_dir: Path)` — определяет путь к
  `Updater.exe` рядом с текущим `sys.executable` (`Path(sys.executable).parent /
  "Updater.exe"`), запускает его через `subprocess.Popen([...])` с аргументами
  `--pid <текущий os.getpid()> --temp <temp_dir> --install <install_dir> --exe
  <путь к Signer.exe>`, затем инициирует закрытие текущего приложения (это
  вызывается из UI-слоя, здесь просто функция, которая делает Popen и возвращает
  управление вызывающему коду).
- Все функции — с docstring и обработкой исключений, ничего не должно ронять
  основное приложение при сбое сети.

### 3. `ui/widgets/update_worker.py` — асинхронная проверка
По образцу существующих `VideoScanWorker` (`ui/widgets/dashboard_page.py`) и
`BackendVerifyThread` (`processing/backend_verify_thread.py`): класс
`UpdateCheckWorker(QThread)` с сигналами `finished_check(object)` (несёт
`UpdateInfo | None`) и `error(str)`, в `run()` вызывает `updater.check_for_update()`.

Отдельный класс `UpdateDownloadWorker(QThread)` с сигналами
`progress(str, int, int, float)` (filename, downloaded, total, speed_bps),
`finished_ok()`, `checksum_failed()`, `error(str)` — оборачивает
`download_assets` + `verify_checksum`.

### 4. `ui/widgets/update_dialog.py` — PyQt6-диалог
`UpdateDialog(QDialog)`, стилизован по образцу `ui/widgets/settings_page.py` /
`ui/themes/theme_manager.py` (`theme_manager.tokens`, подписка на
`theme_manager.theme_changed`). Два состояния в одном диалоге (переключение через
`QStackedWidget` или просто показ/скрытие блоков):

**Состояние "предложение обновиться":**
- текст: текущая версия → новая версия (`APP_VERSION` → `update_info.version`);
- `QPlainTextEdit` read-only с release notes;
- суммарный размер загрузки, человекочитаемо (`_format_size()` helper: B/KB/MB/GB);
- кнопки `[Обновить]` (`BtnPrimary`) и `[Позже]` (`BtnSecondary`), как в остальных
  диалогах проекта.

**Состояние "прогресс":**
- имя текущего файла (`Signer.7z.002`);
- `X.X / Y.Y GB`;
- скорость `NN MB/s`;
- `Осталось MM:SS` (пересчитывается по среднему speed_bps за последние секунды);
- после успеха: текст `Применение обновления...`, вызов
  `updater.launch_updater_and_exit(...)`, затем `QApplication.quit()`;
- при `checksum_failed` или `error`: показать ошибку и кнопку "Повторить",
  вернуться в состояние предложения.

При "Позже" — просто `self.reject()`, приложение продолжает работать как обычно,
никаких файлов не трогать.

### 5. Интеграция в `main.py`
В `main()`, после `window.show()`, если приложение запущено из frozen-сборки
(`getattr(sys, "frozen", False)` — не проверять обновления в dev-режиме без явного
флага окружения `SIGNER_FORCE_UPDATE_CHECK=1`), запусти `UpdateCheckWorker` в фоне.
По `finished_check` с непустым `UpdateInfo` — показать `UpdateDialog` поверх
`MainWindow`. Не блокировать инициализацию UI ожиданием сети.

Дополнительно: при старте сравнить сохранённую в `QSettings("Signer", "RoadScanner")`
запись `last_known_version` с `version.APP_VERSION`; если версия выросла — один раз
показать в статус-баре/тостом `Signer обновлён до версии {APP_VERSION}`, затем
обновить `last_known_version` в `QSettings`. Перед вызовом `launch_updater_and_exit`
из `UpdateDialog` также записывать текущую (предыдущую) версию в `QSettings`, чтобы
это сработало после перезапуска.

### 6. `updater_main.py` (корень проекта) — исходник Updater.exe
Отдельный маленький скрипт БЕЗ импорта `core/`, `processing/`, `ui/` — он должен быть
максимально независим от основного приложения. Логика:
1. Парсинг аргументов через `argparse`: `--pid`, `--temp`, `--install`, `--exe`.
2. Логирование в файл `updater.log` рядом с самим `Updater.exe` (через стандартный
   `logging` в `try/except`, чтобы сбой логирования не ронял процесс).
3. Ожидание завершения процесса Signer: цикл `while psutil.pid_exists(pid)` (если
   `psutil` недоступен в этом изолированном билде — использовать
   `ctypes`-проверку через `OpenProcess`/`WaitForSingleObject` на Windows, либо
   простой поллинг через попытку эксклюзивного открытия `Signer.exe` на запись).
   Таймаут ожидания — например 30 секунд, затем продолжать в любом случае.
4. Небольшая пауза (0.5–1 сек) для гарантированного освобождения файлов Windows.
5. Запуск `7za.exe x "<temp>\Signer.7z.001" -o"<install>" -y` через
   `subprocess.run(..., capture_output=True)`; `7za.exe` ищется рядом с
   `Updater.exe` (тот же каталог) — путь к нему передавай явно, не полагаясь на PATH.
6. Проверка кода возврата: при ошибке — `ctypes.windll.user32.MessageBoxW(0, текст,
   "Signer — ошибка обновления", 0x10)` (не тащить PyQt6 в Updater.exe ради размера
   и независимости) и `sys.exit(1)` без запуска Signer.
7. При успехе — рекурсивно удалить `--temp` папку (`shutil.rmtree`, игнорируя ошибки
   отдельных файлов).
8. Запуск `Signer.exe` из `--install` через `subprocess.Popen([...],
   cwd=install_dir)`.
9. `sys.exit(0)`.

Всё тело обернуть в общий `try/except Exception` с записью traceback в `updater.log`
и показом `MessageBoxW` при неожиданном сбое.

### 7. `updater.spec` (новый файл, корень проекта) — сборка Updater.exe
PyInstaller spec для `updater_main.py`, `--onefile`-эквивалент (один `EXE` без
отдельного `COLLECT`, чтобы получить единый `Updater.exe` без папки `_internal`,
максимально независимый файл), `console=False` (оставь комментарий, что для отладки
можно временно переключить на `True`), имя выходного файла `Updater`. Учти, что
`7za.exe` не обязательно паковать внутрь Updater — вместо этого он лежит рядом в
`dist/Signer/` (см. следующий пункт), Updater ищет его по относительному пути
`Path(sys.executable).parent / "7za.exe"`.

### 8. Правки `signer.spec`
Не ломая существующую конфигурацию:
- Добавь в `datas` включение бинарника `7za.exe` (положи его исходник в
  `assets/7za.exe`, если такого файла нет в репозитории — создай директорию
  `assets/` при необходимости и оставь явный комментарий/TODO в spec-файле, что
  реальный `7za.exe` нужно поместить в `assets/` перед сборкой, т.к. бинарник
  нельзя сгенерировать кодом).
- Убедись, что `version.py` попадает в сборку (обычно PyInstaller подхватывает его
  автоматически как обычный модуль через анализ импортов `main.py`, но явно
  проверь `hiddenimports`).
- В конце покажи точную последовательность команд сборки, при которой
  `Updater.exe` и `7za.exe` в итоге оказываются в `dist/Signer/` рядом с
  `Signer.exe`:
  ```
  pyinstaller signer.spec --noconfirm
  pyinstaller updater.spec --noconfirm
  copy dist\Updater\Updater.exe dist\Signer\Updater.exe
  copy assets\7za.exe dist\Signer\7za.exe
  ```

### 9. Временная папка обновлений
Везде используй:
```
%LOCALAPPDATA%\Signer\UpdateTemp
```
через `Path(os.environ["LOCALAPPDATA"]) / "Signer" / "UpdateTemp"`,
`mkdir(parents=True, exist_ok=True)`. Очищай её перед каждой новой попыткой
скачивания (`shutil.rmtree` + пересоздание) и после успешного применения
обновления (это делает `updater_main.py` на шаге 7 выше).

### 10. UX-тексты — строго такие
- фоновая проверка при старте (не блокирует UI): `Проверка обновлений...`
  (можно в статус-бар через существующий `StatusBar.set_status` в `ui/main_window.py`)
- если найдено: `Доступно обновление 2.1.0`
- прогресс загрузки: как в Этапе 4
- перед закрытием на применение: `Применение обновления...`
- после перезапуска (см. Этап 5, сравнение версий через `QSettings`):
  `Signer обновлён до версии 2.1.0`

## Ограничения — соблюдай строго

- Не трогай `core/`, `processing/`, `configs/sign_*`, детектор, GPS-логику, серверную
  часть карты (`server/`).
- Не изменяй `.iss`-скрипт Inno Setup, если найдёшь его в репозитории.
- Никаких сторонних update-фреймворков.
- Отсутствие сети / недоступность GitHub НЕ должны влиять на запуск и работу
  основного приложения — весь путь проверки обновлений оборачивай в try/except
  с логированием, без падений.
- Следуй существующим паттернам проекта: `QThread` + `pyqtSignal` воркеры (как
  `VideoScanWorker`, `BackendVerifyThread`), стилизация через `theme_manager`,
  `logger = logging.getLogger(__name__)` в каждом модуле, `QSettings("Signer",
  "RoadScanner")` для персистентных настроек (как в `configs/settings.py`).

## Порядок действий

Иди по пунктам 1→10 последовательно. Для каждого пункта: создай/отредактируй
соответствующие файлы прямо в репозитории, кратко прокомментируй что сделано,
и переходи к следующему пункту без лишних пауз на подтверждение. В конце дай
итоговую сводку изменённых/созданных файлов и полную последовательность команд
для сборки и локальной проверки (включая то, как сэмулировать наличие "новой
версии" на GitHub для теста диалога без реального релиза — например, через
временную подмену `version.APP_VERSION` на более старое значение).
