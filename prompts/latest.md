# Промпт для AI-агента: подготовка релиза Signer PRIME v2.0.1 (фикс CPU ONNX/OpenVINO в сборке)

## Контекст
Приложение поддерживает три инференс-бэкенда: PyTorch (дефолт), ONNX Runtime и OpenVINO
(см. `configs/sign_models.py`, `configs/inference_threading.py`, `configs/hardware_recommend.py`).
Сейчас в собранном .exe (PyInstaller, `signer.spec`) ONNX/OpenVINO бэкенды **не гарантированно
работают**, потому что:

1. `requirements.txt` НЕ включает `onnxruntime`/`openvino` — они лежат отдельно в
   `requirements-cpu-backends.txt`, и `scripts\build\prepare_release.bat` их не ставит.
2. `.onnx` и `*_openvino_model/` файлы моделей в `.gitignore` и никогда не генерируются
   автоматически перед сборкой — их создаёт только `scripts/export_models_onnx.py`, который
   тоже не вызывается в build-процессе.
3. `signer.spec` собирает `collect_dynamic_libs('onnxruntime')` / `collect_dynamic_libs('openvino')`
   и `collect_data_files(...)` для них "опционально": если пакет не установлен в венве сборки —
   просто тихо возвращает пустой список, без ошибки и без предупреждения в консоли, кроме одного
   print. В итоге либо бэкенд отсутствует физически в собранном exe, либо есть runtime библиотеки,
   но нет самих экспортированных моделей — и `_LazyModel._load()` в `configs/sign_models.py`
   молча откатывается на PyTorch (см. `logger.warning(... "Откат на PyTorch.")`), пользователь
   выбрал в настройках ONNX/OpenVINO, но реально работает PyTorch (см. `BLOCK CPU-6 /
   verify_backend_active` — эта диагностика уже существует, но выполняется только во время
   работы, а не на этапе сборки).
4. Собранные `.onnx` / `*_openvino_model` файлы не прописаны явно как обязательные `datas` в
   `signer.spec` — их подхват зависит от того, что они физически оказались на диске рядом с
   исходными `.pt` в момент сборки.

## Задача
Подготовь и зафиксируй релиз **v2.0.1**, при этом сделай так, чтобы **CPU-бэкенды ONNX Runtime
и OpenVINO гарантированно работали в собранном приложении** после `prepare_release.bat`, а не
только опционально откатывались на PyTorch.

## Что нужно сделать

### 1. Версия
- Обнови `version.json`: `"version": "2.0.1"`, актуализируй `"build_date"`.
- Проверь `app/version.py` — версия должна читаться именно из `version.json` (уже так, просто
  убедись, что ничего не хардкодит старую версию в другом месте, например в `ui/main_window.py`
  (`"v2.0"` в сайдбаре/заголовках — это просто текстовые лейблы UI, не связаны с версией сборки,
  но проверь и их, чтобы не путать пользователя).

### 2. requirements
- В `requirements.txt` добавь `onnxruntime>=1.29.0` и `openvino>=2024.0` как **обязательные**
  зависимости (не опциональные), либо явно объедини `requirements-cpu-backends.txt` в основной
  установочный шаг сборки (см. п.4). Не используй `onnxruntime-gpu` — только CPU-версия
  (см. комментарий в `requirements-cpu-backends.txt`).
- `openvino-dev` можно оставить опциональным (нужен только для экспорта моделей на этапе сборки,
  не должен попадать в конечный дистрибутив) — его следует ставить в build-окружение отдельно,
  но не тащить рантайм-зависимости dev-пакета в `signer.spec`.

### 3. Экспорт моделей перед сборкой
- В `scripts\build\prepare_release.bat` добавь шаг **до** вызова `pyinstaller signer.spec`,
  который:
  - проверяет наличие `.venv\Scripts\python.exe`;
  - запускает `python scripts/export_models_onnx.py --format onnx` и
    `python scripts/export_models_onnx.py --format openvino` (проверь реальный CLI-интерфейс
    скрипта — если он поддерживает `--format all`, используй один вызов);
  - если экспорт упал или не создал ожидаемых файлов — **прерывает сборку с понятной ошибкой**
    (`exit /b 1`), а не продолжает молча.
- После экспорта должны существовать:
  - `small_models/*.onnx`, `CNN_side/*.onnx`, `lane_guidance_models/*.onnx`
  - `small_models/*_openvino_model/`, `CNN_side/*_openvino_model/`, `lane_guidance_models/*_openvino_model/`
  Сверься с логикой `_p_onnx()` / `_p_openvino()` в `configs/sign_models.py`, чтобы имена файлов
  совпадали 1-в-1 с тем, что ищет `_LazyModel._load()`.

### 4. Фикс `signer.spec`
- Замени "тихий" сбор `collect_dynamic_libs('onnxruntime')`/`collect_dynamic_libs('openvino')`
  и соответствующие `collect_data_files(...)` на явную проверку: если после `pip show onnxruntime`
  / `pip show openvino` пакет не найден в текущем окружении сборки — **упасть с понятным
  сообщением** ("ONNX Runtime/OpenVINO не установлены в venv сборки — CPU-бэкенды будут
  недоступны в собранном приложении, добавьте зависимости или явно подтвердите сборку без них"),
  а не просто print-предупреждение, которое легко пропустить.
- Явно добавь в `datas` каталоги экспортированных моделей (`*.onnx`, `*_openvino_model/`) из
  `small_models/`, `CNN_side/`, `lane_guidance_models/` — по аналогии с уже существующим блоком
  `_project_dirs`, но с проверкой, что хотя бы один `.onnx`/`*_openvino_model` реально найден
  (`glob`), иначе — явный ERROR в консоли сборки (`print` + опционально `sys.exit(1)` через
  raise, если это приемлемо для PyInstaller build hook).
- Убедись, что `hiddenimports` для `onnxruntime`/`openvino` остаются (`collect_submodules`), это
  ок оставить опциональным по импорту, но логировать явно, если пусто.

### 5. Верификация backend'а как часть релизного пайплайна
- В `prepare_release.bat` после сборки добавь smoke-check шаг: используя собранный
  `dist\Signer\Signer.exe` с флагом (или отдельный тестовый скрипт), вызвать эквивалент
  `configs.sign_models.verify_backend_active()` для `cpu_inference_backend="onnx"` и
  `="openvino"` — и если для хотя бы одной модели реальный `_backend` не совпадает с ожидаемым
  (т.е. произошёл тихий откат на `"torch"`), останавливать процесс подготовки релиза с явной
  ошибкой. Можно переиспользовать существующую логику `processing/backend_verify_thread.py`,
  но запускать её headless (без Qt event loop) в отдельном CLI-скрипте
  `scripts/build/verify_cpu_backends.py`.
- Этот скрипт должен по очереди временно выставлять `cpu_inference_backend` в
  `configs/settings.py` (или через переменные окружения/monkeypatch, не трогая сохранённые
  QSettings пользователя) в `"onnx"` и `"openvino"`, вызывать `verify_backend_active()` и
  печатать итоговую таблицу model → backend. Любая строка `ERROR:` или несовпадение с ожидаемым
  backend'ом — код возврата ≠ 0.

### 6. Документация/чеклист
- Обнови (или создай, если нет) `docs/BUILD_AUTOUPDATE.md` / `CHECKLIST.md` — добавь пункт
  "CPU ONNX/OpenVINO бэкенды проверены и включены в сборку" в чеклист перед релизом.
- Если есть `docs/RELEASE.md` — добавь туда упоминание нового обязательного шага экспорта
  моделей и verify-скрипта.

### 7. Тесты
- Посмотри `tests/test_onnx_backend.py` и `tests/test_cpu_thread_parity.py` — они уже тестируют
  часть этой логики (CPU pin для onnx/openvino, потоки). Добавь недостающий unit/integration
  тест, который проверяет, что `signer.spec`/`prepare_release.bat` формируют список datas с
  непустыми `.onnx`/`*_openvino_model` путями при наличии экспортированных файлов на диске
  (можно тестировать логику отдельной вынесенной функцией, а не весь `.spec`, чтобы не тянуть
  PyInstaller в юнит-тесты).

## Ограничения и что НЕ трогать
- Не меняй логику fallback на PyTorch внутри `configs/sign_models.py` в рантайме — она должна
  остаться (graceful degradation на машине пользователя, где моделей/пакетов реально нет). Меняй
  только то, что происходит **на этапе сборки релиза**, чтобы такой fallback никогда не
  срабатывал непреднамеренно в official-сборке.
- Не удаляй `requirements-cpu-backends.txt` — можно оставить его как справочный файл, но сборка
  не должна на него полагаться как на единственный источник зависимостей.
- Не трогай `signer-license-server/` — это отдельный поддиректорий сервера лицензий, к релизу
  клиента 2.0.1 отношения не имеет.
- Не меняй формат/протокол лицензирования, версия относится только к билду клиента.

## Приёмочные критерии
1. `version.json` → `2.0.1`.
2. Чистый запуск `scripts\build\prepare_release.bat` на машине с пустым venv **падает с понятной
   ошибкой**, если `onnxruntime`/`openvino` не установлены или модели не экспортированы —
   вместо того чтобы тихо собрать релиз без рабочих CPU-бэкендов.
3. При корректно настроенном venv (все зависимости есть) `prepare_release.bat` успешно:
   - экспортирует модели в ONNX и OpenVINO,
   - собирает `Signer.exe` с этими моделями и рантаймами внутри `dist\Signer\`,
   - прогоняет verify-скрипт, подтверждающий, что `cpu_inference_backend=onnx` и
     `cpu_inference_backend=openvino` реально используют соответствующий backend, а не
     откатываются на torch.
4. Существующие тесты (`tests/test_onnx_backend.py`, `tests/test_cpu_thread_parity.py`,
   `tests/test_performance_optimizations.py`) продолжают проходить.