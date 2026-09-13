# PROMPT: Усиление защиты системы лицензирования Signer PRIME

## Контекст

Signer PRIME — desktop-приложение на PyQt6, собираемое через PyInstaller
(`signer.spec`, режим `--onedir`). Система лицензирования уже реализована
(`licensing/`, `ui/widgets/license_dialog.py`, серверная часть в
`signer-license-server/`) и описана в `docs/LICENSING.md` /
`docs/LICENSE_SERVER.md`.

Проведён security-review, который выявил три проблемы:

1. **`LICENSE_MOCK_MODE = True` захардкожен как дефолт** в
   `licensing/license_client.py`. Если этот флаг случайно попадёт в
   релизную сборку — приложение примет ЛЮБОЙ лицензионный ключ без
   обращения к серверу и без проверки подписи.
2. **Grace period 10 дней + refresh раз в 3 дня, и оба параметра
   проверяются ТОЛЬКО при старте приложения** — после однократной
   активации пользователь может работать полностью офлайн 10 дней
   подряд, при этом отзыв лицензии на сервере не долетит до клиента,
   пока тот не перезапустится.
3. **Нет обфускации/компиляции байткода.** PyInstaller `--onedir`
   раскладывает `.pyc` файлы, которые тривиально декомпилируются
   (`pyinstxtractor` + `decompyle3`), после чего проверка лицензии в
   `main.py` патчится за минуты.

Ты — AI-агент, которому поручено закрыть все три проблемы. Ниже —
точный план, порядок выполнения, критерии приёмки и что **нельзя**
ломать.

---

## Жёсткие ограничения (не нарушать)

- **Не трогать** `core/`, `processing/`, `server/map_server.py`,
  `templates/map.html` — это независимый пайплайн обработки видео,
  лицензирование не должно иметь никаких side-эффектов на него.
- Приложение обязано продолжать нормально запускаться и работать в
  **dev-режиме без сервера лицензий** (для локальной разработки), но
  без единой мок-реализации внутри кода, который попадает в релизную
  сборку (см. Задачу 1 — решение через реальный локальный сервер, а не
  фиктивный клиент).
- Каждое изменение проверяется отдельным прогоном
  `python -m unittest tests.test_licensing` и ручным запуском
  `python main.py` ПЕРЕД тем, как переходить к следующей задаче.
  Если задача 3 (обфускация) сломает сборку — откатить именно её,
  не трогая задачи 1 и 2.
- Выполнять задачи **строго по порядку 1 → 2 → 3**: задача 3 самая
  рискованная для целостности сборки, её не начинать, пока 1 и 2 не
  зафиксированы рабочим коммитом.

---

## Задача 1 — Полностью убрать мок-режим из runtime-кода

### Проблема с текущим подходом
`LICENSE_MOCK_MODE: bool` — это runtime-флаг внутри модуля, который
попадает в каждую сборку (dev и prod идентичны по коду). Единственная
защита — не забыть переключить в `False`. Забывчивость = дыра в
проде. Нужно устранить сам класс проблемы, а не полагаться на
дисциплину.

### Решение: убрать mock полностью, для dev-режима использовать реальный локальный сервер

В репозитории уже есть полноценный сервер лицензий с docker-compose
стендом (`signer-license-server/docker-compose.dev.yml`). Вместо
фиктивного клиента разработчик должен поднимать этот стенд локально и
указывать на него через `license_server_url`. Так production-код
клиента никогда не содержит альтернативных путей выполнения.

### Пошагово

1. Открой `licensing/license_client.py`.
2. Удали:
   - константу `LICENSE_MOCK_MODE`
   - методы `_mock_activate()` и `_mock_refresh()`
   - все `if LICENSE_MOCK_MODE:` ветвления в `activate()`, `refresh()`,
     `deactivate()` — оставь только реальный HTTP-путь.
3. Убедись, что `requests` теперь обязательная зависимость (убери
   ветку `if not REQUESTS_AVAILABLE` как "мягкий" fallback — если
   `requests` не установлен, это должно быть фатальной ошибкой сборки,
   а не тихим отказом лицензирования; оставь понятное исключение при
   импорте).
4. В `configs/settings.py` добавь возможность переопределить
   `license_server_url` через переменную окружения на этапе
   **запуска**, а не только через сохранённые QSettings — это нужно,
   чтобы разработчик мог направить dev-сборку на локальный
   `docker-compose` стенд без правки кода:

   ```python
   # В AppSettings.load(), после чтения license_server_url из QSettings:
   env_override = os.environ.get("SIGNER_LICENSE_SERVER_URL")
   if env_override:
       data["license_server_url"] = env_override
   ```

   Переменную читать **только** если она задана; иначе поведение не
   меняется.
5. Обнови `licensing/license_client.py`, чтобы `REQUEST_TIMEOUT`
   и `base_url` брались из `settings.license_server_url` как сейчас —
   ничего дополнительно менять не нужно, эффект будет уже через п.4.
6. Удали/актуализируй файлы, которые ссылаются на мок-режим и вводят в
   заблуждение:
   - `example_licensing_mock.py` — удалить или переписать так, чтобы
     он поднимал реальный запрос к `http://localhost:8000` (адрес
     локального docker-compose стенда) вместо
     `licensing.license_client.LICENSE_MOCK_MODE = True`.
   - `QUICKSTART_LICENSING.md` — заменить раздел "Для разработчиков
     (без сервера)" на инструкцию:
     ```bash
     cd signer-license-server
     bash scripts/local_dev_up.sh
     # в отдельном терминале:
     export SIGNER_LICENSE_SERVER_URL=http://localhost:8000
     python main.py
     ```
   - Любые другие упоминания `LICENSE_MOCK_MODE` в `docs/`,
     `README.md`, `IMPLEMENTATION_SUMMARY.md` и т.п. — обнови текст,
     не оставляй противоречащей документации (это не критично для
     безопасности, но обязательно для консистентности).
7. Обнови `tests/test_licensing.py` — там не используется
   `LICENSE_MOCK_MODE` напрямую (там мокается `license_client` через
   `unittest.mock`), но проверь, что тест-сьют по-прежнему проходит
   после удаления констант (тесты не должны падать из-за
   `ImportError`).

### Критерий приёмки Задачи 1
- `grep -rn "LICENSE_MOCK_MODE" .` — **ноль совпадений** во всём
  репозитории (кроме, возможно, changelog/истории, если она есть).
- `python -m unittest tests.test_licensing` — зелёный.
- Запуск `python main.py` без переменной
  `SIGNER_LICENSE_SERVER_URL` и без поднятого сервера лицензий: должен
  честно показать `NOT_ACTIVATED` → диалог активации → ошибка
  `CONNECTION_ERROR` при попытке ввести ключ (а не тихая успешная
  фиктивная активация).
- Запуск с `SIGNER_LICENSE_SERVER_URL=http://localhost:8000` и
  поднятым `docker-compose.dev.yml`: активация реальным ключом,
  созданным через `create_license_manual.py`, проходит успешно.

---

## Задача 2 — Сократить окно офлайн-работы и добавить периодическую проверку в рантайме

### Что сейчас не так
- `license_refresh_interval_days = 3`, `license_grace_period_days = 10`
  в `configs/settings.py`.
- `check_local_status()` и опциональный `refresh_async()` вызываются
  **только один раз**, в `main.py`, до создания `MainWindow`. Если
  пользователь оставит приложение открытым на несколько дней (реальный
  сценарий для этого софта — длительная обработка видео), отзыв
  лицензии на сервере никогда не будет обнаружен, пока пользователь не
  перезапустит процесс.

### Изменения параметров

В `configs/settings.py`, класс `AppSettings`:

```python
license_refresh_interval_days: int = 1     # было 3
license_grace_period_days: int = 3         # было 10
```

Обоснование значений: 1 день — реалистичный компромисс (не требует
интернета ежечасно, но резко сокращает окно бесконтрольной офлайн-
работы). 3 дня grace period — достаточно для короткой командировки без
сети, но не 10 дней вседозволенности. Если бизнес-требования иные —
значения параметризуемы, оставь их полями настроек, не хардкодь.

### Периодическая проверка в рантейме (новый функционал)

Сейчас: 1 проверка при старте. Нужно: проверка каждые N часов, пока
приложение открыто, + немедленная реакция на REVOKED/EXPIRED.

1. В `licensing/license_manager.py` добавь константу и метод:

   ```python
   class LicenseManager:
       RUNTIME_CHECK_INTERVAL_HOURS = 6  # проверять каждые 6 часов работы

       def start_runtime_monitor(self, on_status_changed: Callable[[LicenseStatus], None]) -> "QTimer":
           """
           Запускает QTimer, который каждые RUNTIME_CHECK_INTERVAL_HOURS часов
           асинхронно обновляет токен (refresh_async) и уведомляет
           on_status_changed новым статусом. Таймер должен быть создан
           ПОСЛЕ QApplication и жить пока живо главное окно — вызывающий
           код отвечает за то, чтобы держать ссылку на QTimer (иначе
           Python GC его соберёт).
           """
           from PyQt6.QtCore import QTimer

           timer = QTimer()
           interval_ms = self.RUNTIME_CHECK_INTERVAL_HOURS * 60 * 60 * 1000
           timer.setInterval(interval_ms)

           def _tick():
               def _on_refresh_done(success: bool):
                   new_status = self.check_local_status()
                   on_status_changed(new_status)
               self.refresh_async(_on_refresh_done)

           timer.timeout.connect(_tick)
           timer.start()
           return timer
   ```

2. В `main.py`, после создания `window = MainWindow()` и **до**
   `sys.exit(app.exec())`, подключи монитор:

   ```python
   def _on_license_status_changed(status: LicenseStatus):
       if status in (LicenseStatus.EXPIRED, LicenseStatus.REVOKED):
           logger.warning(f"Лицензия стала недействительна во время работы: {status.value}")
           from PyQt6.QtWidgets import QMessageBox
           QMessageBox.critical(
               window,
               "Лицензия недействительна",
               "Ваша подписка истекла или была отозвана.\n"
               "Приложение будет закрыто. Пожалуйста, активируйте лицензию заново.",
           )
           app.quit()

   # ВАЖНО: сохранить ссылку на таймер на самом window/app, иначе Python
   # соберёт объект мусором и таймер перестанет тикать.
   window._license_monitor_timer = license_manager.start_runtime_monitor(
       _on_license_status_changed
   )
   ```

3. **Не прерывать обработку видео на середине.** Если в момент, когда
   лицензия оказалась недействительной, идёт активная обработка
   (`self._controller.is_running`), не убивай процесс мгновенно —
   сначала попробуй мягко остановить через
   `self._controller.finish_and_save()` (см. `_on_finish_requested` в
   `ui/main_window.py`), дождись сохранения результатов, и только
   потом закрой приложение. Это защищает пользователя от потери
   данных из-за истечения подписки в неудачный момент — не строгое
   требование безопасности, но обязательное требование UX, не
   нарушай его ради "жёсткости" защиты.

4. Обнови `docs/LICENSING.md`: добавь раздел "Runtime monitoring",
   опиши новый интервал проверки и поведение при обнаружении
   REVOKED/EXPIRED посреди сессии.

### Критерий приёмки Задачи 2
- `configs/settings.py` содержит новые значения по умолчанию
  (`refresh_interval=1`, `grace_period=3`); тесты в
  `tests/test_licensing.py::TestLicenseManager`, которые используют
  дни (`test_grace_period`, `test_grace_period_exceeded`), нужно
  **пересчитать под новые границы** (например, тест grace period
  теперь должен использовать `issued_at = now - 2*86400`, а тест
  превышения — `issued_at = now - 4*86400`). Обнови числа в тестах
  соответственно новым константам — не оставляй тесты, которые
  проверяют старые (уже неверные) границы.
- Ручной тест: запусти приложение с активной лицензией, через БД
  сервера (`signer-license-server`, Adminer на `localhost:8081`)
  вручную поставь `licenses.status = 'canceled'` для активной
  лицензии, дождись (или искусственно сократи
  `RUNTIME_CHECK_INTERVAL_HOURS` до `0.01` для теста) срабатывания
  таймера — приложение должно показать диалог и закрыться, не потеряв
  результаты текущей обработки, если она шла.
- Убедись, что `QTimer` не создаётся до `QApplication` (иначе краш) и
  что ссылка на таймер не даёт ему быть собранным GC раньше времени.

---

## Задача 3 — Обфускация кода перед упаковкой (PyArmor + PyInstaller)

### Важное предупреждение перед началом
**НЕ пытайся мигрировать на Nuitka в рамках этой задачи.** Проект
тянет PyQt6 + PyQt6-WebEngine, torch, ultralytics, onnxruntime,
openvino, easyocr — полная компиляция такого стека через Nuitka имеет
высокий шанс сломать рефлексию/динамическую загрузку плагинов внутри
этих библиотек (особенно PyQt6 WebEngine и ultralytics'а автозагрузку
моделей), и потребует многодневной стабилизации сборки без гарантии
успеха. Правильный, проверенный и на порядок более безопасный путь для
этого стека — **PyArmor поверх существующего PyInstaller-пайплайна**
(это официально поддерживаемая связка). Nuitka зафиксируй как
задокументированную идею на будущее (см. раздел "Что дальше", ниже),
но не реализуй её сейчас.

### Стратегия обфускации: точечно, не всё подряд

Обфускация усложняет декомпиляцию, но обфусцировать `core/` и
`processing/` (тяжёлый numpy/torch/opencv код) — лишний риск сломать
производительность и совместимость без ощутимого прироста защиты
(конкурента интересует не алгоритм детекции знаков, а обход
лицензии). Обфусцируй только модули, отвечающие за проверку
лицензии и точку входа:

```
main.py
licensing/license_manager.py
licensing/license_client.py
licensing/device_fingerprint.py
licensing/public_key.py
licensing/__init__.py
ui/widgets/license_dialog.py
```

Всё остальное (`core/`, `processing/`, `ui/widgets/*` кроме
`license_dialog.py`, `server/`) оставь как есть — не трогай.

### Пошагово

1. Установи PyArmor как dev-зависимость:

   ```bash
   pip install pyarmor
   ```

   Добавь в `requirements-dev.txt`:
   ```
   pyarmor>=9.0.0
   ```

   **Внимание**: у PyArmor есть Free (Community) и Pro редакции.
   Free-редакция накладывает ограничения (обфусцированный код
   привязывается к определённому числу устройств для *разработки*,
   плюс более слабая защита раннтайма). Для реального продакшн-релиза
   уточни у владельца проекта, куплена ли Pro-лицензия PyArmor —
   если нет, работай с Free-редакцией, но зафиксируй это ограничение
   в `docs/BUILD_AUTOUPDATE.md` как техдолг.

2. Создай новый скрипт `scripts/build/obfuscate_licensing.py`:

   ```python
   """
   scripts/build/obfuscate_licensing.py
   Обфусцирует license-критичные модули через PyArmor ПЕРЕД PyInstaller.
   Результат кладётся в build/obfuscated/, откуда PyInstaller дальше
   собирает финальный exe (см. изменения в signer.spec).

   Использование:
       python scripts/build/obfuscate_licensing.py
   """
   import shutil
   import subprocess
   import sys
   from pathlib import Path

   ROOT = Path(__file__).resolve().parents[2]
   OUT_DIR = ROOT / "build" / "obfuscated"

   # Модули/пакеты, которые обфусцируются целиком.
   # Пути указаны относительно корня репозитория.
   TARGETS = [
       "main.py",
       "licensing",
       "ui/widgets/license_dialog.py",
   ]

   def main():
       if OUT_DIR.exists():
           shutil.rmtree(OUT_DIR)
       OUT_DIR.mkdir(parents=True)

       # Копируем ВЕСЬ репозиторий в OUT_DIR, затем поверх заменяем
       # только TARGETS обфусцированными версиями. Так относительные
       # импорты (core.*, configs.*, ui.*) продолжают резолвиться.
       print(f"[obfuscate] Копирование проекта в {OUT_DIR}...")
       shutil.copytree(
           ROOT, OUT_DIR, dirs_exist_ok=True,
           ignore=shutil.ignore_patterns(
               "build", "dist", ".git", "__pycache__", "*.pyc",
               "venv", "venv_new", ".venv", "signer-license-server",
           ),
       )

       for target in TARGETS:
           src = ROOT / target
           dst = OUT_DIR / target
           print(f"[obfuscate] PyArmor gen: {target}")
           if src.is_dir():
               subprocess.run(
                   ["pyarmor", "gen", "-O", str(dst.parent), "-r", str(src)],
                   check=True, cwd=ROOT,
               )
           else:
               subprocess.run(
                   ["pyarmor", "gen", "-O", str(dst.parent), str(src)],
                   check=True, cwd=ROOT,
               )

       print(f"[obfuscate] Готово. Обфусцированный проект: {OUT_DIR}")
       print("[obfuscate] Теперь собирайте PyInstaller из этой директории:")
       print(f"    cd {OUT_DIR} && pyinstaller signer.spec --noconfirm")


   if __name__ == "__main__":
       main()
   ```

   Точную команду `pyarmor gen` (аргументы могут отличаться между
   версиями 8.x/9.x) сверь с `pyarmor --help` в установленной версии —
   если синтаксис отличается, адаптируй, сохранив принцип: обфусцируем
   только `TARGETS`, остальной код копируем как есть.

3. Обнови `scripts/build/prepare_release.bat`, добавив шаг обфускации
   **перед** вызовом `pyinstaller signer.spec`:

   ```bat
   echo [2.5/5] Obfuscating licensing modules...
   python scripts\build\obfuscate_licensing.py
   if errorlevel 1 (
       echo ERROR: Obfuscation failed
       pause
       exit /b 1
   )
   ```

   И далее в шаге сборки замени рабочую директорию на
   `build\obfuscated` для вызова `pyinstaller signer.spec`, либо
   скопируй актуальный `signer.spec` в `build/obfuscated/` перед
   вызовом (PyArmor gen не трогает `.spec`-файлы, только `.py`).

4. **Обязательно проверь после сборки**, что PyArmor runtime-файлы
   (`pyarmor_runtime_XXXXXX/` — генерируется рядом с обфусцированными
   модулями) реально попали в итоговый `dist/Signer/`. Если PyInstaller
   их не подхватил автоматически через анализ импортов — добавь их
   вручную в `datas` в `signer.spec`:

   ```python
   # В signer.spec, рядом с остальными datas:
   pyarmor_runtime_dirs = list((ROOT / "build" / "obfuscated").glob("pyarmor_runtime_*"))
   for rt_dir in pyarmor_runtime_dirs:
       datas.append((str(rt_dir), rt_dir.name))
   ```

5. **Прогони полный ручной regression-тест собранного exe**, не
   только импорт:
   - Запусти `dist/Signer/Signer.exe`
   - Пройди активацию лицензии с реальным ключом с сервера
   - Проверь grace period (выключи Wi-Fi, перезапусти — должно
     работать в пределах `license_grace_period_days`)
   - Запусти полный цикл обработки тестового видео + GPX, убедись что
     GeoJSON сохраняется (это гарантия, что обфускация
     `license_dialog.py`/`main.py` не сломала остальной пайплайн,
     который их импортирует).

### Критерий приёмки Задачи 3
- `dist/Signer/Signer.exe` запускается без исключений при импорте
  обфусцированных модулей (нет `ModuleNotFoundError` /
  `RuntimeError: pyarmor runtime not found`).
- Полный сценарий активации/refresh/деактивации лицензии проходит на
  собранном exe так же, как проходил на dev-запуске через
  `python main.py`.
- Попытка открыть `dist/Signer/_internal/main.pyc` (или как он теперь
  называется после PyArmor) стандартным `uncompyle3`/`decompyle3`
  **не должна давать читаемый Python-код** — либо инструмент
  падает с ошибкой, либо выдаёт мусор вместо логики проверки
  лицензии. Это ручная проверка "как атакующий" — выполни её сам после
  сборки, приложив короткий отчёт (успех/неудача) в PR.
- Обычный (не обфусцированный) код в `core/`/`processing/` собирается
  и работает **бок о бок** без изменений — если что-то в
  `signer.spec` пришлось поменять для datas/hiddenimports обфусцированных
  модулей, убедись, что старые datas/hiddenimports для torch/opencv/
  ultralytics не задеты.

### Что дальше (не реализовывать сейчас, только зафиксировать в докe)
Добавь в `docs/BUILD_AUTOUPDATE.md` раздел "Возможные будущие
улучшения защиты":
- Nuitka — полная компиляция в C, кандидат на отдельный
  research-спайк с выделенным временем на стабилизацию (оценка: 3-5
  дней с учётом текущего стека зависимостей), не блокирует текущий
  релиз.
- PyArmor Pro (если сейчас используется Free) — снимает ограничения
  на runtime-защиту и антиотладку.
- Вынесение части бизнес-логики (например, финальной пост-обработки
  GeoJSON) на сервер как облачный сервис — тогда пиратство теряет
  смысл, т.к. без сервера продукт неполнофункционален. Это архитектурно
  большое изменение, не в рамках текущего промпта.

---

## Итоговый чек-лист для агента (в порядке выполнения)

- [ ] Задача 1: `LICENSE_MOCK_MODE` полностью удалён из кодовой базы
- [ ] Задача 1: `SIGNER_LICENSE_SERVER_URL` работает как override для dev
- [ ] Задача 1: `tests/test_licensing.py` зелёный
- [ ] Задача 1: ручная проверка — dev без сервера получает честный `CONNECTION_ERROR`, а не тихую активацию
- [ ] Коммит задачи 1 отдельно от задачи 2
- [ ] Задача 2: `refresh_interval_days=1`, `grace_period_days=3` в `configs/settings.py`
- [ ] Задача 2: тесты `test_grace_period*` пересчитаны под новые границы
- [ ] Задача 2: `LicenseManager.start_runtime_monitor()` реализован и подключён в `main.py`
- [ ] Задача 2: обработка REVOKED/EXPIRED в рантайме не рвёт активную обработку видео "на живую" — сначала мягкое завершение
- [ ] Коммит задачи 2 отдельно от задачи 3
- [ ] Задача 3: `scripts/build/obfuscate_licensing.py` создан и работает
- [ ] Задача 3: `prepare_release.bat` обновлён, обфускация — шаг перед PyInstaller
- [ ] Задача 3: собранный `Signer.exe` проходит полный regression (лицензия + обработка видео)
- [ ] Задача 3: ручная попытка декомпиляции обфусцированных модулей задокументирована (успех/неудача)
- [ ] `docs/LICENSING.md`, `QUICKSTART_LICENSING.md`, `docs/BUILD_AUTOUPDATE.md` обновлены под новую реальность
