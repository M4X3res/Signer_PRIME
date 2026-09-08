# AGENT PROMPT — Исправление багов CPU-бэкенда (ONNX/OpenVINO)

**Контекст:** В проекте RoadScanner (BLOCK M) была добавлена поддержка альтернативных
бэкендов инференса для CPU-режима — ONNX Runtime и OpenVINO, как альтернатива PyTorch
(`configs/sign_models.py::_LazyModel`, `configs/settings.py::cpu_inference_backend`).

Анализ кода показал, что реализация **не работает так, как заявлено в
`BLOCK_M_Q_EXECUTION_REPORT.md` / `CHANGELOG.md` / `FINAL_EXECUTION_SUMMARY.md`**: есть один
критический баг, сводящий на нет весь смысл ONNX-бэкенда для реального пайплайна
классификации знаков, плюс несколько багов рангом ниже в Settings UI, и явное
расхождение между документацией ("✅ выполнено") и реальными логами экспорта моделей
(`export_log.txt`, `export_classify.txt`), которые показывают провал экспорта.

Ниже — полный список найденных проблем и точный план их исправления. Выполняй по
порядку, от BUG-1 (критично) далее. После каждого блока — секция "Проверка", не
переходи к следующему блоку, не выполнив её.

---

## Сводная таблица

| ID     | Серьёзность | Файл(ы)                                                        | Суть |
|--------|-------------|------------------------------------------------------------------|------|
| BUG-1  | 🔴 Критично | `configs/sign_models.py`                                         | `_LazyModel.__call__()` не форсирует `device='cpu'` для ONNX/OpenVINO — а именно через `__call__` идёт весь реальный путь классификации знаков |
| BUG-2  | 🟠 Высокая  | `configs/sign_models.py`, `main.py`                               | `ORT_DISABLE_CUDA` выставляется один раз при старте процесса и не пересинхронизируется при смене `use_cuda` в рантайме |
| BUG-3  | 🟡 Средняя  | `ui/widgets/settings_page.py::_reset()`                           | Кнопка "Сбросить" не сбрасывает `_cpu_backend_combo` к дефолту |
| BUG-4  | 🟡 Средняя  | `ui/widgets/settings_page.py::_import_settings()`                 | Импорт настроек из JSON не восстанавливает `cpu_inference_backend` — значение тихо перезатирается тем, что было в UI до импорта |
| BUG-5  | 🟡 Средняя  | `ui/widgets/settings_page.py`                                     | `lane_conf_detect` / `lane_conf_segment` есть в `AppSettings`, но недоступны из UI вообще (нет виджетов, нет в `_collect_settings`) |
| BUG-6  | 🟢 Низкая (защитная мера) | `configs/sign_models.py`                             | Для OpenVino-бэкенда нет явного pin на CPU (несимметрично с ONNX) — чинится тем же патчем, что и BUG-1 |
| BUG-7  | 🟠 Высокая (доверие к документации) | `export_log.txt`, `export_classify.txt`, `*.md` отчёты | Логи экспорта показывают провал (`onnx не установлен`) оба раза, но отчёты утверждают "✅ Все 18 моделей сконвертированы" |
| BUG-8  | 🟡 Средняя  | `requirements.txt` (не в контексте, проверить)                    | `onnx`/`onnxruntime`/`openvino` не задекларированы как зависимости → svежая установка проекта воспроизводит тот же провал экспорта |
| REFACTOR-1 | ℹ️ Рекомендация | `configs/sign_models.py`                              | Логика `"torch" if use_cuda else cpu_inference_backend` продублирована в двух местах — вынести в одну функцию |

---

## BUG-1 (🔴 Критично): `__call__` не проходит через CPU-pin логику

### Симптом
Ранее уже был баг с тем, что ONNX Runtime пытался забиндить CUDA-тензоры на CPU-девайс
(см. `BACKEND_SELECTION_FIX.md`, ошибка `Error when binding input: There's no data
transfer registered for copying tensors from Device:[...CUDA] to Device:[...CPU]`).
Официально "исправлено" через `_LazyModel.predict()`, который добавляет `device='cpu'`
в kwargs, если бэкенд — `onnx`.

### Корневая причина
```python
# configs/sign_models.py, класс _LazyModel

def predict(self, *args, **kwargs):
    model = self._load()
    if self._backend == "onnx" and 'device' not in kwargs:
        kwargs['device'] = 'cpu'
        ...
    result = model.predict(*args, **kwargs)
    ...
    return result

def __call__(self, *args, **kwargs):
    return self._load()(*args, **kwargs)   # <-- НИКАКОЙ логики device='cpu' здесь нет!
```

В Ultralytics `YOLO.__call__` — это просто алиас на `predict()`, поэтому семантически
`model(x)` и `model.predict(x)` должны быть эквивалентны. Но `_LazyModel.__call__`
вызывает `self._load()(*args, **kwargs)` напрямую, **в обход** метода `predict()` этого
же класса — а значит и в обход инъекции `device='cpu'`.

Теперь смотрим, ГДЕ в проекте реально вызываются модели категорий (`model_dict`) и
суб-модели треугольников (`sub_models`) — то есть модели, которые классифицируют
**каждый** обнаруженный знак:

```python
# core/detector.py :: _run_cnn_model()  (одиночный путь)
model  = model_dict[yolo_class]
output = model(crop32)[0]                       # <-- через __call__!
...
sub_out = sub_models[result_type](crop32)[0]     # <-- через __call__!

# core/detector.py :: _run_cnn_batch()  (батч-путь, используется detect()/detect_with_tracking())
batch_outputs = model(crops32, verbose=False)    # <-- через __call__!
...
sub_out = sub_models[result_type](crop, verbose=False)[0]  # <-- через __call__!
```

Через `.predict()` в проекте вызываются только `model_side_detect` (bbox-детекция),
`rube_modal` (грубая категоризация) и lane-модели в `core/lane_detector.py`. **Все
finre-классификаторы (`model_dict` — 10 моделей: blue/treugolnik/krug/red/servises/
tablichka__/tablichkaL/tupic/5.38/5.9.1-5.14/5.5-5.6, и `sub_models` — danger/pimicanie/
suzenie) вызываются только через `__call__`.** Это значит, что реализованный CPU-pin
фикс **не защищает основной пайплайн классификации знаков вообще** — то есть проблема,
которую якобы устранили в `BACKEND_SELECTION_FIX.md`, при выборе ONNX-бэкенда может
вернуться именно на самом частом пути выполнения.

### Исправление

Замени в `configs/sign_models.py` реализацию класса `_LazyModel` так, чтобы `__call__`
и `predict()` шли через один и тот же код, а не дублировали (и рассинхронизировали)
логику. Заодно расширить pin на `openvino`-бэкенд для симметрии (BUG-6) — OpenVINO
через Ultralytics по умолчанию должен использовать CPU, но explicit pin не помешает и
устраняет асимметрию с ONNX.

```python
class _LazyModel:
    ...

    def _predict_kwargs_with_cpu_pin(self, kwargs: dict) -> dict:
        """
        BLOCK M-FIX (BUG-1/BUG-6): принудительно указывает device='cpu' для
        ONNX/OpenVINO backend, если вызывающий код не указал device явно.

        Без этого шага Ultralytics AutoBackend может попытаться создать сессию
        с CUDAExecutionProvider даже когда пользователь явно выбрал CPU-бэкенд —
        именно этот класс ошибок был описан в BACKEND_SELECTION_FIX.md
        ("Error when binding input... CUDA -> CPU").
        """
        if self._backend in ("onnx", "openvino") and 'device' not in kwargs:
            kwargs['device'] = 'cpu'
            logger.debug(
                f"[sign_models] {self._backend} inference: явно установлен device=cpu"
            )
        return kwargs

    def _reassert_cpu_predictor(self, model) -> None:
        if self._backend in ("onnx", "openvino") and hasattr(model, 'predictor') and model.predictor:
            import torch
            try:
                model.predictor.device = torch.device("cpu")
            except Exception:
                pass

    def predict(self, *args, **kwargs):
        model = self._load()
        kwargs = self._predict_kwargs_with_cpu_pin(kwargs)
        result = model.predict(*args, **kwargs)
        self._reassert_cpu_predictor(model)
        return result

    def __call__(self, *args, **kwargs):
        # ВАЖНО (BUG-1 fix): раньше здесь был прямой self._load()(*args, **kwargs),
        # который полностью обходил device='cpu' инъекцию из predict(). Основной
        # путь классификации знаков (core/detector.py: _run_cnn_model, _run_cnn_batch,
        # включая суб-модели треугольников) вызывает модели именно через __call__,
        # а не через .predict() — поэтому этот баг фактически сводил на нет весь
        # CPU-backend фикс для реальной классификации. YOLO.__call__ у Ultralytics —
        # это alias на predict(), так что делегирование здесь безопасно и не меняет
        # публичный контракт.
        return self.predict(*args, **kwargs)
```

Удали старые дублирующиеся версии `predict()`/`__call__()` (полностью замени их этим
блоком). `__getattr__` не трогать.

### Проверка
1. `grep -rn "model_dict\[" core/` и `grep -rn "sub_models\[" core/` — убедиться, что
   ВСЕ найденные вызовы моделей (и напрямую, и через переменную `model`) идут либо
   через `.predict(`, либо через новый унифицированный `__call__`. Не должно остаться
   мест, вызывающих `self._load()` напрямую в обход `_LazyModel`.
2. Написать/дополнить `tests/test_onnx_backend.py` регрессионным тестом:
   ```python
   def test_call_applies_same_cpu_pin_as_predict():
       """Регрессия на BUG-1: __call__ обязан вести себя как predict()."""
       from configs.sign_models import _LazyModel

       captured = {}

       class FakeYOLOModel:
           predictor = None
           def predict(self, *a, **kw):
               captured['kwargs'] = kw
               return ["ok"]

       lm = _LazyModel(lambda: "fake.pt", task="classify")
       lm._model = FakeYOLOModel()
       lm._backend = "onnx"

       lm(object())  # вызов через __call__

       assert captured['kwargs'].get('device') == 'cpu', (
           "__call__ должен форсировать device='cpu' так же, как .predict()"
       )
   ```
3. Ручной smoke-тест (если есть машина с CUDA): выставить `use_cuda=False`,
   `cpu_inference_backend="onnx"`, реально экспортировать модели (см. BUG-7/8) и
   прогнать `Detector().detect(frame)` на нескольких кадрах с разными категориями
   знаков (минимум по одному кадру на `blue`/`treugolnik`/`krug`, чтобы затронуть и
   `model_dict`, и `sub_models`). Убедиться, что не возникает ошибок биндинга
   CUDA→CPU и что классификация вообще работает (не -1 на всех знаках).

---

## BUG-2 (🟠 Высокая): `ORT_DISABLE_CUDA` не пересинхронизируется в рантайме

### Симптом
`main.py` выставляет `ORT_DISABLE_CUDA=1` **один раз** при старте главного процесса,
основываясь на значении `settings.use_cuda` **на момент запуска**:

```python
# main.py :: setup_environment()
try:
    from configs.settings import get_app_settings
    settings = get_app_settings()
    if not settings.use_cuda:
        os.environ["ORT_DISABLE_CUDA"] = "1"
except Exception:
    os.environ.setdefault("ORT_DISABLE_CUDA", "1")
```

Но `configs/sign_models.py::reload_all_models_if_device_changed()` — функция, специально
предназначенная для поддержки переключения `use_cuda`/`cpu_inference_backend` **посреди
сессии приложения** (вызывается из `ProcessingController.start()` перед каждым запуском
обработки) — никак не трогает `ORT_DISABLE_CUDA`.

Итог: если пользователь запустил приложение с `use_cuda=True` (env var не выставлена),
затем в Settings выключил CUDA и выбрал `cpu_inference_backend="onnx"` — при следующем
запуске обработки `reload_all_models_if_device_changed()` корректно сбросит кэш моделей
и заставит их перезагрузиться под ONNX-бэкенд, но `ORT_DISABLE_CUDA` останется не
выставленной, и ONNX Runtime может попытаться создать сессию с CUDAExecutionProvider
в списке провайдеров, несмотря на явный выбор "CPU-режим".

### Исправление

В `configs/sign_models.py` (модуль уже импортирует `os` вверху файла):

```python
def reload_all_models_if_device_changed() -> bool:
    """..."""
    global _last_resolved_device, _last_resolved_backend

    from configs.settings import get_app_settings
    settings = get_app_settings()

    # BLOCK M-FIX (BUG-2): синхронизируем ORT_DISABLE_CUDA с текущим use_cuda
    # ПРИ КАЖДОМ вызове этой функции, а не только один раз в main.py при
    # старте процесса. Без этого переключение "Использовать CUDA" в Settings
    # посреди сессии не влияет на реальный выбор execution provider у ONNX
    # Runtime, и CPU-бэкенд может неожиданно попытаться задействовать CUDA.
    if settings.use_cuda:
        os.environ.pop("ORT_DISABLE_CUDA", None)
    else:
        os.environ["ORT_DISABLE_CUDA"] = "1"

    current_device = _resolve_device()
    current_backend = "torch" if settings.use_cuda else settings.cpu_inference_backend

    changed = (
        (_last_resolved_device is not None and _last_resolved_device != current_device)
        or (_last_resolved_backend is not None and _last_resolved_backend != current_backend)
    )
    # ... остальное без изменений
```

Логику в `main.py::setup_environment()` **не удалять** — она полезна для самого первого
запуска процесса, до того как `reload_all_models_if_device_changed()` вообще будет
вызвана впервые (например, если пользователь так и не запустил обработку).

### Проверка
- Юнит-тест: замокать `get_app_settings()` на объект с `use_cuda=False`,
  `cpu_inference_backend="onnx"`, вызвать `reload_all_models_if_device_changed()`,
  проверить `os.environ["ORT_DISABLE_CUDA"] == "1"`. Затем замокать на `use_cuda=True`,
  вызвать снова, проверить, что `"ORT_DISABLE_CUDA" not in os.environ`.

---

## BUG-3 (🟡 Средняя): "Сбросить" не сбрасывает выбор CPU-бэкенда

### Симптом
`ui/widgets/settings_page.py::_reset()` явно перебирает **все** виджеты и сбрасывает их
к `AppSettings()` дефолтам (frame_step, confidence, dedup, processing_mode, workers,
OCR, CUDA-toggle, logging, turn geometry, theme) — но `_cpu_backend_combo` в этом списке
**отсутствует**. После нажатия "Сбросить" комбобокс визуально остаётся на прежнем
значении, хотя все остальные поля уже показывают дефолты — несогласованное состояние
UI, которое затем может быть сохранено как есть при следующем "Сохранить".

### Исправление

В `ui/widgets/settings_page.py::_reset()`, сразу после блока CUDA settings
(`if hasattr(self, '_cuda_toggle'): self._cuda_toggle.set_checked(defaults.use_cuda)`),
добавить:

```python
        # CPU-инференс бэкенд (BLOCK M-FIX: BUG-3)
        if hasattr(self, '_cpu_backend_combo'):
            backend_map_rev = {"torch": 0, "onnx": 1, "openvino": 2}
            self._cpu_backend_combo.setCurrentIndex(
                backend_map_rev.get(defaults.cpu_inference_backend, 0)
            )

        # Пороги lane detection (BLOCK M-FIX: BUG-5, см. ниже — виджеты создаются там же)
        if hasattr(self, '_lane_conf_detect_spin'):
            self._lane_conf_detect_spin.setValue(defaults.lane_conf_detect)
        if hasattr(self, '_lane_conf_segment_spin'):
            self._lane_conf_segment_spin.setValue(defaults.lane_conf_segment)
```

### Проверка
Открыть Settings → выбрать "ONNX Runtime" в бэкенде → нажать "Сбросить" → убедиться,
что комбобокс вернулся на "PyTorch (по умолчанию)".

---

## BUG-4 (🟡 Средняя): Импорт настроек из JSON теряет `cpu_inference_backend`

### Симптом
`_export_settings()` использует `self._settings.to_dict()` (то есть `dataclasses.asdict`),
поэтому **экспорт** корректно включает `cpu_inference_backend`, `lane_conf_detect`,
`lane_conf_segment` и вообще все поля `AppSettings`.

А вот `_import_settings()` читает JSON и **вручную**, поле за полем, применяет значения
к виджетам (frame_step, confidence, dedup, processing_mode, OCR, CUDA, turn geometry,
theme) — но не трогает `_cpu_backend_combo` вообще. При этом в конце метода вызывается:

```python
# Сразу сохраняем импортированные настройки
self._save()
```

`_save()` вызывает `_collect_settings()`, который читает `self._cpu_backend_combo.currentIndex()`
— то есть то значение, что было в комбобоксе **до** импорта. Импортированное значение
`cpu_inference_backend` из JSON-файла тихо теряется и подменяется текущим состоянием UI.
Такая же судьба у `lane_conf_detect`/`lane_conf_segment` (см. BUG-5 — их вообще нет в
UI, поэтому и взять их из импорта неоткуда).

### Исправление

В `ui/widgets/settings_page.py::_import_settings()`, перед `self._save()`, добавить:

```python
            # CPU-инференс бэкенд (BLOCK M-FIX: BUG-4)
            if hasattr(self, '_cpu_backend_combo'):
                backend_map_rev = {"torch": 0, "onnx": 1, "openvino": 2}
                imported_backend = settings_dict.get("cpu_inference_backend", "torch")
                self._cpu_backend_combo.setCurrentIndex(
                    backend_map_rev.get(imported_backend, 0)
                )

            # Пороги lane detection (BLOCK M-FIX: BUG-5)
            if hasattr(self, '_lane_conf_detect_spin'):
                self._lane_conf_detect_spin.setValue(
                    settings_dict.get("lane_conf_detect", 0.65)
                )
            if hasattr(self, '_lane_conf_segment_spin'):
                self._lane_conf_segment_spin.setValue(
                    settings_dict.get("lane_conf_segment", 0.65)
                )

            print(f"[SettingsPage] Настройки импортированы из: {file_path}")

            # Сразу сохраняем импортированные настройки
            self._save()
```

(Порядок: вставить новый блок непосредственно перед существующей строкой
`print(f"[SettingsPage] Настройки импортированы из: {file_path}")`, которая уже есть в
коде прямо перед `self._save()`.)

### Проверка
1. Экспортировать настройки с `cpu_inference_backend="onnx"`.
2. Сменить бэкенд в UI на "PyTorch".
3. Импортировать экспортированный файл.
4. Убедиться, что после импорта комбобокс и сохранённый `AppSettings.cpu_inference_backend`
   действительно равны `"onnx"`, а не `"torch"`.

---

## BUG-5 (🟡 Средняя): `lane_conf_detect`/`lane_conf_segment` недоступны из UI

### Симптом
`configs/settings.py` содержит:
```python
lane_conf_detect: float = 0.65   # Порог уверенности для model_lane_detect
lane_conf_segment: float = 0.65  # Порог уверенности для model_lane_segment
```
Эти пороги реально используются в `core/lane_detector.py::LaneDetector.__init__()`
(`self.CONF_LANE_DETECT`, `self.CONF_LANE_SEGMENT`) и влияют на распознавание разметки
полос (знаки 4.1.x/6.3.1 через `LaneDetector.find_signs()`). Но в
`ui/widgets/settings_page.py` для них нет ни QDoubleSpinBox, ни строки в
`_collect_settings()` — пользователь физически не может их поменять иначе как вручную
редактируя QSettings/JSON.

### Исправление

1. Добавить новую группу настроек в конструктор `SettingsPage.__init__`, сразу после
   блока `content_layout.addWidget(mt_group)` (группа "Многопоточность") и перед блоком
   `# ── Group: Логирование ──`:

```python
        # ── Group: Разметка полос движения (lane detection) ─────
        lane_group = SettingsGroup("Разметка полос движения")

        self._lane_conf_detect_spin = QDoubleSpinBox()
        self._lane_conf_detect_spin.setRange(0.1, 0.95)
        self._lane_conf_detect_spin.setSingleStep(0.05)
        self._lane_conf_detect_spin.setDecimals(2)
        self._lane_conf_detect_spin.setValue(self._settings.lane_conf_detect)
        self._lane_conf_detect_spin.setFixedWidth(90)
        self._lane_conf_detect_spin.setToolTip(
            "Порог уверенности YOLO для model_lane_detect (поиск стрелок разметки).\n"
            "Влияет на распознавание знаков 4.1.x/6.3.1 через LaneDetector.\n"
            "Рекомендуется: 0.5-0.75"
        )
        lane_group.add_row(
            "Уверенность (Lane Detect)",
            "Детекция стрелок разметки полос",
            self._lane_conf_detect_spin,
        )

        self._lane_conf_segment_spin = QDoubleSpinBox()
        self._lane_conf_segment_spin.setRange(0.1, 0.95)
        self._lane_conf_segment_spin.setSingleStep(0.05)
        self._lane_conf_segment_spin.setDecimals(2)
        self._lane_conf_segment_spin.setValue(self._settings.lane_conf_segment)
        self._lane_conf_segment_spin.setFixedWidth(90)
        self._lane_conf_segment_spin.setToolTip(
            "Порог уверенности YOLO для model_lane_segment (сегментация стрелок).\n"
            "Рекомендуется: 0.5-0.75"
        )
        lane_group.add_row(
            "Уверенность (Lane Segment)",
            "Сегментация направления стрелок разметки",
            self._lane_conf_segment_spin,
        )

        content_layout.addWidget(lane_group)
```

2. В `_collect_settings()`, рядом с блоком CPU-инференса, добавить:

```python
            # Lane detection thresholds (BLOCK M-FIX: BUG-5)
            if hasattr(self, '_lane_conf_detect_spin'):
                self._settings.lane_conf_detect = self._lane_conf_detect_spin.value()
            if hasattr(self, '_lane_conf_segment_spin'):
                self._settings.lane_conf_segment = self._lane_conf_segment_spin.value()
```

3. `_reset()` и `_import_settings()` — уже покрыты патчами из BUG-3 и BUG-4 выше.

### Проверка
Открыть Settings → должна появиться новая группа "Разметка полос движения" с двумя
регулируемыми порогами. Изменить значение → Сохранить → перезапустить приложение →
убедиться, что значение сохранилось (через `AppSettings.load()`).

---

## BUG-7 / BUG-8 (🟠 Высокая): документация утверждает успех, логи показывают провал

### Симптом
`export_log.txt`:
```
2026-09-01 08:34:29,896 [ERROR] onnx не установлен. Установите: pip install onnx
```
`export_classify.txt` (повторная попытка позже в тот же день):
```
2026-09-01 09:07:47,955 [ERROR] onnx не установлен. Установите: pip install onnx
```

Обе попытки экспорта моделей в ONNX **провалились** из-за отсутствия пакета `onnx` в
окружении. Никакого лога успешного экспорта в проекте нет.

При этом:
- `BLOCK_M_Q_EXECUTION_REPORT.md` пишет: "⚠️ Требуется прогон пользователем с реальным
  тестовым видео" (это честно и корректно).
- Но `FINAL_EXECUTION_SUMMARY.md` и `NEXT_STEPS.md`, написанные, судя по всему, позже,
  уже безапелляционно утверждают: "✅ **Установлены зависимости**: onnx 1.22.0,
  onnxruntime 1.29.0" и "✅ **Все 18 моделей сконвертированы** (2026-09-01 09:28,
  ~900 MB total)" — однако лога успешного запуска в 09:28 нигде нет, а последняя
  зафиксированная попытка в 09:07 всё ещё падает с той же ошибкой отсутствия пакета.
- Файл `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md`, на который многократно ссылаются как на
  "полную документацию" ONNX-бэкенда (с шаблонами для замера FPS), в репозитории
  отсутствует.
- Файлы `tests/test_onnx_backend.py` и `tests/test_deduplication.py::TestDeduplicationLargeRadius`,
  которые несколько отчётов описывают как уже созданные и содержащие тесты для BLOCK M/N,
  тоже отсутствуют в репозитории.

**Практический вывод:** если это состояние актуально, при выборе `cpu_inference_backend
= "onnx"` или `"openvino"` в реальности НИ ОДНА модель не найдёт свой `.onnx`/`.xml`
файл на диске, `_LazyModel._load()` каждый раз будет откатываться на PyTorch с
`logger.warning(...)`, и пользователь получит нулевой прирост производительности,
считая при этом (по документации), что ONNX-бэкенд включён и работает.

### Что нужно сделать
1. Проверить фактическое состояние окружения: `pip show onnx onnxruntime openvino`.
2. Если пакетов нет — установить (`pip install onnx onnxruntime` как минимум; `openvino
   openvino-dev` опционально) и добавить их в `requirements.txt` (создать/обновить файл,
   если он отсутствует или неполон) так, чтобы свежая установка проекта не воспроизводила
   ту же ошибку `onnx не установлен`.
3. Реально запустить `python scripts/export_models_onnx.py --format onnx` и убедиться,
   что для каждой из 18 моделей из списка `MODELS` в этом скрипте появился
   соответствующий `.onnx`-файл рядом с `.pt` (используй `should_export()`/файловую
   систему для проверки, не полагайся на текстовый вывод скрипта).
4. Прогнать `Detector()` (или отдельно `_LazyModel._load()` для каждой модели из
   `model_dict`/`sub_models`/`model_side_detect`/`rube_modal`/`model_lane_detect`/
   `model_lane_segment`) с `use_cuda=False`, `cpu_inference_backend="onnx"` и убедиться
   в логах, что backend реально `"onnx"`, а не тихий откат на `"torch"`
   (`logger.info(f"[sign_models] Загружена ONNX-модель: ...")` должен появиться для
   каждой модели, ни одного `logger.warning(...Откат на PyTorch...)` быть не должно).
5. **Не переписывай задним числом старые markdown-отчёты, выдавая желаемое за
   действительное.** Вместо этого либо: (а) реально доведи экспорт до успеха и добавь
   новый, правдивый отчёт с фактическими логами/таймштампами и числом файлов на диске,
   либо (б) если по каким-то причинам экспорт довести до конца сейчас нельзя (нет
   доступа к весам моделей, слишком долго и т.п.) — явно зафиксируй в новом отчёте
   `ONNX_EXPORT_STATUS.md`, что реально сделано, а что нет, без фраз "✅ выполнено" там,
   где это не подтверждено логами/файлами на диске.
6. Создай (или подтверди наличие и актуальность) `tests/test_onnx_backend.py` с как
   минимум тремя тестами:
   - Регрессия на BUG-1 (см. секцию BUG-1 выше).
   - Параметризованный тест по `backend in ["torch", "onnx", "openvino"]` × `batch_size
     in [1, 3, 8]`, который `pytest.skip()`-ается, если соответствующие
     `.onnx`/`_openvino_model` файлы отсутствуют на диске (чтобы CI не падал на машинах
     без экспортированных моделей).
   - Тест консистентности: на ~20 случайных кропах сравнить top1-класс между PyTorch и
     ONNX (если модели есть), допуская не более 1 расхождения из 20.

### Проверка
`ls small_models/*.onnx CNN_side/*.onnx lane_guidance_models/*.onnx` (или аналог для
Windows) должен реально показать файлы, а не сообщение "no such file". `pytest
tests/test_onnx_backend.py -v` должен либо пройти, либо осознанно скипнуться с понятной
причиной — не падать с `ImportError: No module named 'onnx'`.

---

## REFACTOR-1 (рекомендация, не обязательна, но снижает риск будущих багов)

Логика выбора эффективного бэкенда `"torch" if settings.use_cuda else
settings.cpu_inference_backend` продублирована как минимум в двух местах:
`_LazyModel._resolve_backend()` и `reload_all_models_if_device_changed()`. Рекомендуется
вынести в одну функцию модуля `configs/sign_models.py`:

```python
def _resolve_backend_name(settings) -> str:
    """Единая точка истины: какой backend реально должен использоваться."""
    return "torch" if settings.use_cuda else settings.cpu_inference_backend
```

и использовать её в обоих местах, чтобы избежать рассинхронизации при будущих правках
(ровно такой класс дублирования логики и привёл, в конечном счёте, к BUG-2).

---

## Общие ограничения для агента (соблюдать во всех блоках)

1. **Не менять поведение по умолчанию.** `cpu_inference_backend` по умолчанию остаётся
   `"torch"`. Ни один существующий пользователь с дефолтными настройками не должен
   заметить разницы в поведении после этих фиксов.
2. **Не трогать GPU/CUDA-путь.** Когда `use_cuda=True`, backend всегда `"torch"` — эта
   ветка логики не меняется никак, только CPU/ONNX/OpenVINO ветки.
3. **Логирование, не print().** Весь новый код — через `logger.debug/info/warning`, как
   в остальном `configs/sign_models.py`. В `ui/widgets/settings_page.py` уже используется
   смесь `print()`/`logger` — новый код можно оставить в стиле окружающего кода этого
   файла (там уже `print()`), но не добавлять новых print() в `configs/sign_models.py`.
4. **Обратная совместимость Settings.** Не переименовывай и не удаляй существующие поля
   `AppSettings` (`cpu_inference_backend`, `lane_conf_detect`, `lane_conf_segment`) —
   только чини доступ к ним из UI/reset/import.
5. **Ничего не удалять из `configs/sign_config.py`** (легаси-шим обратной совместимости)
   — вне scope этой задачи.
6. **После каждого блока — grep-проверка**, что не осталось старых версий
   исправленного кода (например, после BUG-1 не должно остаться старого `__call__`,
   вызывающего `self._load()(*args, **kwargs)` напрямую).
7. Не переписывай задним числом существующие markdown-отчёты (`CHANGELOG.md`,
   `BLOCK_M_Q_EXECUTION_REPORT.md` и т.д.), кроме случая BUG-7/8, где явно требуется
   зафиксировать реальный статус экспорта — и то отдельным новым файлом, не редактируя
   историю.

## Итоговый чеклист приёмки

- [ ] BUG-1: `__call__` делегирует в `predict()`; регрессионный тест зелёный;
      `grep` не находит обходов `_LazyModel` при вызове моделей категорий/суб-моделей.
- [ ] BUG-2: `ORT_DISABLE_CUDA` синхронизируется внутри
      `reload_all_models_if_device_changed()`, тест на переключение `use_cuda` зелёный.
- [ ] BUG-3: "Сбросить" возвращает CPU-бэкенд и lane-пороги к дефолтам.
- [ ] BUG-4: Импорт JSON корректно восстанавливает `cpu_inference_backend` и
      `lane_conf_detect`/`lane_conf_segment`.
- [ ] BUG-5: В Settings UI появилась группа "Разметка полос движения" с двумя рабочими
      порогами, сохраняющимися между запусками.
- [ ] BUG-6: Покрыт тем же патчем, что BUG-1 (openvino тоже получает device='cpu' pin).
- [ ] BUG-7/8: Реальный статус ONNX-экспорта подтверждён файлами на диске и логами, а
      не только текстом в markdown; `requirements.txt` включает нужные пакеты;
      `tests/test_onnx_backend.py` существует и либо проходит, либо осмысленно
      скипается.
- [ ] Полный прогон `pytest` без новых регрессий.
- [ ] Приложение стартует (`python main.py`) без ошибок с дефолтными настройками
      (`use_cuda` как было у пользователя, `cpu_inference_backend="torch"`).
