# AGENT PROMPT — ONNX/OpenVINO для CPU-инференса + технический долг

**Контекст:** RoadScanner (Signer PRIME) — приложение на PyQt6, детектирующее дорожные знаки
на видео с видеорегистратора, трекающее их и сохраняющее в GeoJSON с привязкой к OSM.
Инференс сейчас всегда идёт через `ultralytics.YOLO` (PyTorch backend), включая CPU-режим.
Собственный анализ проекта (`WHY_SINGLE_THREAD_FASTER.md`) показывает, что параллельные
режимы (`pipeline`, `process_pool`) на CPU медленнее однопоточного из-за GIL и overhead
сериализации — то есть единственный реальный путь ускорения CPU-инференса сейчас: заменить
бэкенд исполнения моделей, а не пытаться распараллелить Python-код вокруг него.

**Главная задача сессии (Блок M) — высокий приоритет, делать первым.**
Остальные блоки (N–S) — накопленный технический долг из отдельного аудита; выполнять
после Блока M, в указанном порядке, но не блокируя ими Блок M.

---

## Общие правила для агента (обязательно прочитать перед началом)

Эти правила сформулированы по опыту предыдущих сессий работы над этим проектом
(см. `STATUS.md`, `BLOCK_H_*`, `BLOCK_B3_*`) — в прошлом уже случались ситуации, когда
следующая сессия объявляла что-то «полностью реализовано», хотя по факту это было не так
(пример: миграция `print()` → `logging` несколько раз объявлялась завершённой, но в
реальности осталась незакончена в 15 файлах). Не повторяй эту ошибку:

1. **Не объявляй пункт выполненным без факта проверки.** Прогони код/тест/grep и убедись
   лично, прежде чем писать «✅ Done» в отчёте.
2. **Не удаляй файл/метод, не подтвердив через `grep -rn` в ТЕКУЩЕЙ версии репозитория**
   (не по этому промпту, не по старым отчётам), что на него больше нигде нет ссылок.
3. **Не меняй поведение по умолчанию для существующих пользователей без явной причины.**
   Новый функционал (ONNX/OpenVINO backend) — строго opt-in через настройку, выключен
   по умолчанию, пока не пройдёт собственный regression-тест и бенчмарк.
4. **GPU/CUDA-путь не трогать.** Вся работа Блока M — только про CPU-инференс. Если
   `use_cuda=True`, поведение должно быть побитово идентично текущему (PyTorch/CUDA).
5. **Не плоди новые STATUS/AUDIT файлы поверх старых.** Обновляй по факту один документ
   (см. Блок Q) вместо создания десятого `SESSION_SUMMARY_*.md`.
6. **Если бенчмарк показывает, что оптимизация не работает или работает хуже** — честно
   напиши это в отчёте (прецедент: `STATUS.md` §2.5 про Process Pool на CPU), а не
   подгоняй вывод под ожидаемый результат.
7. **Учитывай историю крашей 0xC0000409** (STATUS.md, множество BUGFIX_*.md) — это был
   конфликт OpenMP/MKL потоков torch с Qt WebEngine на Windows. Любая новая библиотека
   с собственным threading-рантаймом (в данном случае — ONNX Runtime) потенциально
   реинтроduцирует ту же категорию краша, если не сконфигурирована так же осторожно,
   как это уже сделано для torch (`OMP_NUM_THREADS=1`, `torch.set_num_threads(1)` и т.д.
   в `processing/detector_thread.py`, `processing/detector_process_pool.py`).

Порядок выполнения: **M → N → O → P → Q → R → S**. Блок S — самый крупный и наименее
формализованный (доработка карты); если не хватает бюджета сессии — оставь его на
отдельную сессию, но не начинай его, не закончив M–R.

---

# БЛОК M — ONNX Runtime / OpenVINO для CPU-инференса

## M.0 — Профилирование и бейзлайн (обязательно перед любым кодом)

1. Запусти `scripts/benchmark_detector.py --video <тестовое видео> --frames 100 --force-cpu`
   на реальном тестовом видео. Зафиксируй: FPS, распределение времени по стадиям через
   `core/profiler.py` (`yolo_bbox_detection`, `batch_classify_rube`, `batch_classify_fine`,
   `ocr_read_text` — последнее не в фокусе этого блока, EasyOCR уже вынесен в отдельный
   `ProcessPool`, трогать его тут не нужно).
2. Зафиксируй CPU, на котором проводился замер (модель, число ядер, поддержка AVX2/AVX512) —
   выигрыш ONNX Runtime сильно зависит от набора инструкций.
3. Результат сохранить как часть отчёта `BLOCK_M_ONNX_CPU_RESULTS.md` (см. M.8), секция
   «Baseline».

## M.1 — Экспорт моделей в ONNX / OpenVINO IR

Модели, которые нужно поддержать (все объявлены в `configs/sign_models.py`):

| Переменная | Путь (.pt) | Задача (task) |
|---|---|---|
| `model_side_detect` | `CNN_side/best.pt` | detect |
| `rube_modal` | `small_models/rude.pt` | classify |
| `model_dict["blue"]` | `small_models/blue.pt` | classify |
| `model_dict["treugolnik"]` | `small_models/treugolnik.pt` | classify |
| `model_dict["krug"]` | `small_models/krug.pt` | classify |
| `model_dict["red"]` | `small_models/red.pt` | classify |
| `model_dict["servises"]` | `small_models/servises.pt` | classify |
| `model_dict["tablichkaL"]` | `small_models/tabl l.pt` | classify |
| `model_dict["tablichka__"]` | `small_models/tabl.pt` | classify |
| `model_dict["tupic"]` | `small_models/tupic.pt` | classify |
| `model_dict["5.38"]` | `small_models/5.38.pt` | classify |
| `model_dict["5.9.1-5.14"]` | `small_models/5.9.1-5.14.pt` | classify |
| `model_dict["5.5-5.6"]` | `small_models/one_side.pt` | classify |
| `sub_models["danger"]` | `small_models/danger.pt` | classify |
| `sub_models["pimicanie"]` | `small_models/pimicanie.pt` | classify |
| `sub_models["suzenie"]` | `small_models/suzenie.pt` | classify |
| `model_lane_detect` | `lane_guidance_models/arrow_detect.pt` | detect |
| `model_lane_segment` | `lane_guidance_models/arrow_segment.pt` | segment |

Создай `scripts/export_models_onnx.py`:

```python
import argparse, logging, os, time
from ultralytics import YOLO

# Список (путь_pt, task) собрать из таблицы выше — не хардкодить дважды,
# по возможности импортировать пути из configs/sign_models.py через utils.resource_path,
# чтобы список моделей не могли рассинхронизировать с реальным кодом.

def export_one(pt_path: str, task: str, fmt: str, dynamic: bool = True) -> str:
    """
    fmt: "onnx" | "openvino"
    Возвращает путь к результату. Идемпотентно — пропускает, если результат
    новее исходного .pt.
    """
    ...

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--format", choices=["onnx", "openvino"], default="onnx")
    parser.add_argument("--models", choices=["all", "detect", "classify", "segment"], default="all")
    parser.add_argument("--force", action="store_true", help="Переэкспортировать, даже если файл свежий")
    args = parser.parse_args()
    ...

if __name__ == "__main__":
    main()
```

Требования к реализации:
- Экспорт классификационных моделей — **обязательно с `dynamic=True`** (см. M.4, почему).
- `opset` зафиксировать явно (например 12) для воспроизводимости между машинами.
- Для `format="onnx"` использовать `YOLO(pt_path).export(format="onnx", dynamic=True, simplify=True, opset=12)`.
- Для `format="openvino"` — `YOLO(pt_path).export(format="openvino", dynamic=True)`, результат — директория `<name>_openvino_model/` с `.xml`/`.bin`.
- Логировать время экспорта и итоговый размер файла на модель.
- Добавить `--force`, чтобы принудительно пересобрать.
- Добавить в `.gitignore` шаблоны для сгенерированных артефактов (`*.onnx`, `*_openvino_model/`)
  рядом с уже существующими исключениями моделей — это генерируемые артефакты, не хранить в git.
- В `ui/widgets/settings_page.py` добавить кнопку «Экспортировать модели для CPU-инференса»
  (группа "Диагностика системы", рядом с «Проверить GPU»), запускающую скрипт в фоновом
  `QThread` (по образцу `VideoScanWorker` в `dashboard_page.py` — не блокировать UI),
  с прогресс-баром/логом и явным сообщением об ошибке, если `onnxruntime`/`openvino`
  не установлены в окружении.

## M.2 — Настройки

В `configs/settings.py`, класс `AppSettings`, добавить:

```python
# ── CPU-инференс (BLOCK M) ─────────────────────────────────────
cpu_inference_backend: Literal["torch", "onnx", "openvino"] = "torch"
```

Дефолт — **`"torch"`** (не менять поведение существующих пользователей без явного
переключения ими самими). Поле должно **игнорироваться**, если `use_cuda=True` — это
нужно enforced не только в UI, но и на уровне логики загрузки моделей (M.3), т.к.
`AppSettings` можно менять и через импорт JSON, минуя UI-контролы.

В `ui/widgets/settings_page.py`:
- Новая группа `SettingsGroup("CPU-инференс")` (или добавить в существующую "Диагностика
  системы") с `QComboBox`: `["PyTorch (по умолчанию)", "ONNX Runtime", "OpenVINO"]`.
- `setEnabled` этого комбобокса должен зависеть от состояния `_cuda_toggle` (аналогично
  тому, как `_workers_spin` зависит от `_processing_mode_combo` — см. существующий
  паттерн `currentIndexChanged.connect(lambda idx: ...)`).
- Tooltip: объяснить, что нужно сначала нажать «Экспортировать модели для CPU-инференса»,
  и что при отсутствии экспортированных файлов приложение автоматически откатится на PyTorch
  с предупреждением в логе.
- Добавить в `_collect_settings()`, `_reset()`, экспорт/импорт JSON (`to_dict()`/`from_dict()`
  уже общие — просто убедиться, что новое поле проходит через них без доп. кода).

## M.3 — Интеграция в `configs/sign_models.py`

Расширить `_LazyModel`, сохранив полную обратную совместимость публичного интерфейса
(`__call__`, `.predict()`, `.to()`) для всех мест, где он уже используется
(`core/detector.py`, `core/lane_detector.py`):

```python
class _LazyModel:
    def __init__(self, path_fn, task: str, onnx_path_fn=None, openvino_path_fn=None):
        self._path_fn = path_fn
        self._task = task                      # "detect" | "classify" | "segment"
        self._onnx_path_fn = onnx_path_fn
        self._openvino_path_fn = openvino_path_fn
        self._model = None
        self._device = None
        self._backend = None                   # реально загруженный backend

    def _resolve_backend(self) -> str:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if settings.use_cuda:
            return "torch"   # CUDA — всегда torch, ONNX/OpenVINO вне области этого блока
        return settings.cpu_inference_backend

    def _load(self):
        if self._model is not None:
            return self._model

        from ultralytics import YOLO
        backend = self._resolve_backend()
        self._device = _resolve_device()

        if backend == "onnx" and self._onnx_path_fn:
            onnx_path = self._onnx_path_fn()
            if os.path.exists(onnx_path):
                self._model = YOLO(onnx_path, task=self._task)
                self._backend = "onnx"
            else:
                logger.warning(
                    f"[sign_models] ONNX-модель не найдена: {onnx_path}. "
                    f"Запустите scripts/export_models_onnx.py. Откат на PyTorch."
                )
                self._model = YOLO(self._path_fn())
                self._model.to(self._device)
                self._backend = "torch"
        elif backend == "openvino" and self._openvino_path_fn:
            ov_path = self._openvino_path_fn()
            if os.path.exists(ov_path):
                self._model = YOLO(ov_path, task=self._task)
                self._backend = "openvino"
            else:
                logger.warning(f"[sign_models] OpenVINO-модель не найдена: {ov_path}. Откат на PyTorch.")
                self._model = YOLO(self._path_fn())
                self._model.to(self._device)
                self._backend = "torch"
        else:
            self._model = YOLO(self._path_fn())
            self._model.to(self._device)   # .to() валиден только для torch-backend
            self._backend = "torch"

        return self._model
```

Важные технические нюансы, которые нужно явно проверить (это не гипотетические риски,
а конкретные грабли API ultralytics):

- **`task=` обязателен** при загрузке «сырого» `.onnx`/OpenVINO IR — ultralytics не всегда
  умеет надёжно определить задачу (detect/classify/segment) из графа без исходного `.pt`.
  Проверить фактическое поведение установленной версии `ultralytics` — если `task=` не
  требуется в этой версии, всё равно передавать явно (безопаснее и не хуже).
- **`.to(device)` — не вызывать** для backend != "torch" (ONNX Runtime/OpenVINO сессии
  этот метод не поддерживают в том же смысле — либо no-op, либо исключение, зависит от
  версии ultralytics; проверить эмпирически и обернуть в `try/except` с логированием,
  если поведение неочевидно).
- Каждый конкретный `_LazyModel(...)` в конце `sign_models.py` (там, где сейчас
  `model_side_detect = _LazyModel(_p("CNN_side/best.pt"))` и т.д.) нужно расширить
  соответствующими `task=`, `onnx_path_fn=`, `openvino_path_fn=` — заведи для этого
  аналогичный `_p()`-хелпер, но возвращающий путь с заменённым расширением
  (`CNN_side/best.onnx`, `CNN_side/best_openvino_model/best.xml` и т.д. — сверить точную
  структуру пути, которую реально генерирует `export()`, экспериментально после M.1,
  не угадывать вслепую).

Обновить `reload_all_models_if_device_changed()`:

```python
_last_resolved_backend: str | None = None

def reload_all_models_if_device_changed() -> bool:
    global _last_resolved_device, _last_resolved_backend
    current_device = _resolve_device()
    from configs.settings import get_app_settings
    current_backend = "torch" if get_app_settings().use_cuda else get_app_settings().cpu_inference_backend

    changed = (
        (_last_resolved_device is not None and _last_resolved_device != current_device)
        or (_last_resolved_backend is not None and _last_resolved_backend != current_backend)
    )
    if changed:
        # существующая логика сброса кэша всех _LazyModel
        ...
    _last_resolved_device = current_device
    _last_resolved_backend = current_backend
    return changed
```

## M.4 — Батчинг и `dynamic axes` (критичный технический риск)

`core/detector.py::_classify_rube_batch()` и `_run_cnn_batch()` вызывают
`model_dict[yolo_class](crops32, verbose=False)`, где `crops32` — Python-список numpy-
массивов **переменной длины** (от 1 до N знаков на кадре). Если классификационные модели
экспортированы со **статическим** batch=1, батч-вызов либо упадёт, либо ultralytics
незаметно перейдёт на покадровый цикл внутри себя (теряя весь смысл батчинга).

**Обязательно:**
1. Экспортировать все `classify`-модели с `dynamic=True` (см. M.1).
2. Написать `tests/test_onnx_backend.py`, проверяющий, что ONNX-загруженная
   классификационная модель корректно принимает списки длиной 1, 3 и 8 и возвращает
   результат такой же формы, что и PyTorch-версия (сравнение `top1` класса, не точных
   float-значений — см. M.6).
3. Только после того, как этот тест зелёный — разрешать `cpu_inference_backend != "torch"`
   в UI (можно held back флагом `EXPERIMENTAL` в коде, если тест ещё не проходит на
   момент промежуточного коммита).

## M.5 — Потокобезопасность (0xC0000409 — обязательно к прочтению)

История проекта содержит документированные краши от конфликта OpenMP/MKL-потоков torch
с Qt (искать `KMP_DUPLICATE_LIB_OK`, `torch.set_num_threads(1)` в
`processing/detector_thread.py` и `processing/detector_process_pool.py::_worker_process_frame`).
ONNX Runtime на CPU по умолчанию тоже создаёт собственный пул потоков (часто поверх
OpenMP/MKL-DNN) — это новый потенциальный источник **той же самой** категории краша.

Обязательно перед включением ONNX/OpenVINO backend по умолчанию для кого-либо:

```python
import onnxruntime as ort
so = ort.SessionOptions()
so.intra_op_num_threads = 1
so.inter_op_num_threads = 1
so.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
```

Если версия `ultralytics`, используемая в проекте, не даёт прямого способа прокинуть
`SessionOptions` в `AutoBackend` — выставить переменные окружения (`OMP_NUM_THREADS=1`,
`ORT_*` при их наличии) **до** первого импорта `onnxruntime`, тем же способом, каким это
уже сделано для torch в существующем коде. Не изобретать новый паттерн — скопировать
проверенный.

**Обязательное условие приёмки этого пункта:** стресс-тест не короче 20 минут в
`single_thread` CPU-режиме с включённым ONNX backend, без единого краша. Это ровно тот же
бар, что проект сам для себя установил в `STATUS.md` §2.2 для любых изменений threading —
не занижать его для новой библиотеки просто потому что «это же не torch».

## M.6 — Регресс-тест точности

Расширить существующий `scripts/test_detector_regression.py`:
- Добавить флаг `--backend torch|onnx|openvino`.
- Baseline снимается с `--backend torch` (как сейчас).
- Сравнение: `--backend onnx`/`--backend openvino` на том же наборе кадров.

Критерий приёмки: `yolo_class`/`cnn_class` совпадают с baseline минимум в **99%**
детекций. Расхождения по `bbox` (xyxy) допустимы в пределах ±2px (float-арифметика ONNX
и PyTorch кернелов немного отличается — это ожидаемо и не является багом само по себе).
Каждое расхождение свыше порога — логировать с номером кадра для ручного разбора, не
скрывать.

## M.7 — Бенчмарк производительности

Расширить `scripts/benchmark_detector.py` флагом `--backend`. Прогнать одинаковый набор
кадров с `--force-cpu` для `torch` и `onnx` (и `openvino`, если реализован), сравнить FPS.

**Честный критерий приёмки:** рекомендовать/включать backend по умолчанию для CPU-
пользователей имеет смысл только при **измеренном, воспроизводимом приросте FPS ≥20%**
относительно torch-бейзлайна. Если прирост меньше или backend медленнее — прямо
задокументировать это в отчёте (см. прецедент честного вывода про Process Pool на CPU в
`STATUS.md` §2.5), не выдавать желаемое за действительное.

## M.8 — Документация

Создать `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` по шаблону, уже устоявшемуся в проекте
(см. `BLOCK_H_TURN_GEOMETRY_IMPLEMENTATION.md` как образец структуры): Проблема → Решение
→ Изменённые файлы → Численные результаты (бейзлайн vs после) → Известные ограничения →
Критерии приёмки (чеклист).

### Критерии приёмки Блока M (итоговый чеклист)

- [ ] `use_cuda=True` — поведение на 100% не изменилось (ручной smoke-тест GPU-пути)
- [ ] `cpu_inference_backend` по умолчанию `"torch"` — поведение по умолчанию не изменилось
- [ ] Скрипт экспорта идемпотентен, не падает при отсутствии `onnxruntime`/`openvino` как
      опциональных зависимостей (даёт понятную ошибку с инструкцией `pip install`)
- [ ] Отсутствие экспортированного файла → автоматический откат на PyTorch с логом
      уровня WARNING, без краша
- [ ] Ни одного нового `print()` — только `logging`
- [ ] `tests/test_onnx_backend.py` подтверждает корректность динамического батчинга
- [ ] Настроена защита от конфликта потоков (M.5), пройден 20-минутный стресс-тест
- [ ] Regression-тест (M.6): ≥99% совпадения классов с torch-бейзлайном
- [ ] Бенчмарк (M.7) — честные цифры в отчёте, включая отрицательный результат, если он есть

---

# БЛОК N — Корректность (баги, найденные аудитом)

## N.1 — Радиус финальной дедупликации молча ограничен геометрией сетки

**Файл:** `core/final_handler.py`, класс `FinalHandler`, метод `_deduplicate()`.

**Проблема:** `GRID_CELL_M = 20.0` — константа. Поиск соседей-дублей проверяет только
окно ±1 ячейка (3×3 = 9 ячеек), что физически ограничивает эффективный радиус поиска
дублей величиной порядка `GRID_CELL_M`–`2×GRID_CELL_M` в зависимости от положения точки
внутри своей ячейки. При этом в `ui/widgets/settings_page.py` (`_dedup_final_spin`)
пользователю разрешено выставлять `dedup_radius_final_m` вплоть до 200 м. Для любого
значения выше ~30–35 м дубликаты за пределами этого фактического радиуса никогда не
будут найдены, независимо от явной проверки `if dist > self.DEDUP_RADIUS_M` дальше по
коду — та проверка лишь отсеивает кандидатов, уже найденных в узком окне 3×3, а не
расширяет поиск.

**Исправление:**

```python
def __init__(self, settings=None):
    ...
    self.DEDUP_RADIUS_M = settings.dedup_radius_final_m
    # Ячейка сетки не больше половины радиуса — гарантирует, что окно ±N ячеек
    # покрывает весь заявленный радиус поиска дублей.
    self.GRID_CELL_M = max(10.0, self.DEDUP_RADIUS_M / 2.0)
```

В `_deduplicate()` — сделать размер окна поиска соседних ячеек производным от
соотношения радиуса и размера ячейки, а не хардкодить `(-1, 0, 1)`:

```python
import math
cells_to_check = max(1, math.ceil(self.DEDUP_RADIUS_M / self.GRID_CELL_M))
for dx in range(-cells_to_check, cells_to_check + 1):
    for dy in range(-cells_to_check, cells_to_check + 1):
        ...
```

**Тест:** расширить `tests/test_deduplication.py` — два фичи на расстоянии 150 м друг от
друга при `dedup_radius_final_m=200` должны мержиться; при дефолтных 20 м — не должны.

## N.2 — `save_error_frames`/`error_frames_dir`: настройка есть, реализации нет

**Проверено:** поля объявлены в `configs/settings.py`, тумблер и биндинги есть в
`ui/widgets/settings_page.py` (`_save_frames_toggle`), присутствуют в экспорте/импорте
JSON — но ни в одном другом файле проекта `save_error_frames` не читается для реального
действия. Переключатель в UI ничего не делает.

**Реализовать** (предпочтительный вариант — инфраструктура уже готова, не выбрасывать её):
в `core/detector.py`, в местах, где классификация не проходит порог confidence
(`_run_cnn_model`/`_run_cnn_batch`, ветка `if conf < self.CONF_CNN: return -1`), при
`settings.save_error_frames == True` сохранять кроп (и желательно — таймстемп/номер кадра
в имени файла) в `settings.error_frames_dir` через `cv2.imwrite`, с троттлингом (например,
не чаще одного сохранения на трекаемый знак — переиспользовать паттерн троттлинга,
уже применённый для OCR через `TrackedSign.should_run_ocr`/`mark_ocr_requested`, либо
завести аналогичный простой счётчик), чтобы не заваливать диск на длинных видео.
Директорию создавать лениво (`os.makedirs(..., exist_ok=True)`) при первом сохранении.

Если после оценки объёма работы решение — не реализовывать, а убрать функционал:
удалить поля из `AppSettings`, контрол и упоминания в `settings_page.py` (`_collect_settings`,
`_reset`, экспорт/импорт). Но перед этим — явное решение, а не оставление «как есть» в
N-й раз подряд.

## N.3 — `turn_detection_radius_m`: неиспользуемая настройка

**Проверено:** поле есть в `AppSettings`, спинбокс есть в `settings_page.py`, но
`setEnabled(False)` с комментарием «пока не используется» — и это состояние
задокументировано ещё в `BLOCK_H_TURN_GEOMETRY_IMPLEMENTATION.md` и
`AGENT_PROMPT_EXECUTION_REPORT_turns_map_settings.md` (§3.3), но так и не разрешено ни в
одной из последующих сессий.

**Решение:** поскольку `core/intersection_geometry.py` уже делает собственный
дистанционно-ограниченный raycast через `turn_ray_max_distance_m`, а привязка знака к
повороту делается через `SignHandler`/`Turn` независимо от этого радиуса — функционал
избыточен по отношению к уже существующим механизмам. Удалить поле, контрол и все
ссылки на него. Явно зафиксировать в отчёте, что удаление сделано осознанно (со ссылкой
на историю в этом промпте), чтобы будущие сессии не пытались «на всякий случай»
восстановить его, не разобравшись в контексте.

### Критерии приёмки Блока N

- [ ] Тест на N.1 зелёный для радиусов значительно больше 20 м
- [ ] N.2 — либо рабочая реализация с ручной проверкой (включить настройку, обработать
      видео, убедиться что файлы появились), либо чистое удаление
- [ ] N.3 — поле удалено, `grep -rn "turn_detection_radius_m"` по репозиторию — пусто

---

# БЛОК O — Мёртвый код и дублирующиеся источники истины

Перед каждым удалением — обязательный `grep -rn "<имя>" .` по актуальной версии
репозитория (не доверять этому списку слепо — состояние могло измениться с момента
аудита).

## O.1 — Файлы, не имеющие входящих ссылок

- `index.html` — легаси-версия карты на ArcGIS. `server/map_server.py` рендерит только
  `templates/map.html` (`flask.render_template("map.html")`); ни один `.py`-файл на
  `index.html` не ссылается. Внутри файла зашит собственный дублирующий JS-словарь
  `names_signs_by_type`, независимый от `configs/sign_data.py::NAMES_SIGNS_BY_TYPE` —
  ещё один потенциальный источник рассинхронизации данных о знаках, как уже случалось
  раньше с дублями ключей в `sign_data.py` (см. `AUDIT_REPORT.md`). Удалить файл.
- `ui/themes/theme_manager_backup.py` — полный дубликат `ThemeManager`, нигде не
  импортируется. Удалить.
- `ui/widgets/placeholder_pages.py` — определяет классы `MapPage`/`ErrorEditorPage`,
  дублирующие по имени полноценные виджеты из `ui/widgets/map_page.py` и
  `ui/widgets/error_editor_page.py`. Нигде не импортируется. Риск: случайный неверный
  импорт в будущем создаст трудноуловимый баг. Удалить.

## O.2 — Неиспользуемый путь построения Feature в `final_handler.py`

`_sign_to_feature()` (строка ~773) и `_snap_sign_coords()` (строка ~727) — старый
покадровый (не batch) путь снаппинга к OSM. Реальный пайплайн (`_process_straight_signs`)
использует только `_sign_to_feature_with_snap()` через batch-снап
(`_batch_snap_signs`/`OSMSnapper.snap_batch`). `_snap_sign_coords` вызывается только из
`_sign_to_feature`, которая, в свою очередь, не вызывается больше нигде. Удалить оба
метода (~90 строк мёртвого кода), предварительно подтвердив grep'ом отсутствие других
вызовов.

## O.3 — `signs.json`

Проверить через grep (Python и JS/HTML), используется ли файл где-либо, кроме уже
удаляемого `index.html`. Если нет активных потребителей — удалить, оставив
`configs/sign_data.py` единственным источником истины по кодам/именам знаков. Если
находится живой потребитель — оставить файл, но добавить комментарий в начале файла,
поясняющий, кто и зачем его читает (чтобы следующая сессия не удалила его вслепую).

## O.4 — Мелкая уборка

- `core/coordinate_calculation.py`: удалить неиспользуемую константу `_ONE_RADIAN`.
- `core/lane_detector.py`: удалить закомментированный debug-код
  (`cv2.rectangle`/`cv2.imshow`/`cv2.waitKey`) и `print('-'.join(result_type_signs))`;
  если строка полезна для отладки — заменить на `logger.debug(...)`.

### Критерии приёмки Блока O

- [ ] Для каждого удалённого символа/файла — `grep -rn` по репозиторию вне git-истории
      удаления возвращает пусто
- [ ] Приложение стартует, полный цикл (детекция → трекинг → `FinalHandler.save_result` →
      GeoJSON) отрабатывает без `ImportError`/`AttributeError`

---

# БЛОК P — Консистентность конфигурации и логирования

## P.1 — `core/lane_detector.py`: пороги уверенности захардкожены

`__process_sign()` использует `conf=0.65` для обеих моделей (`model_lane_detect`,
`model_lane_segment`) напрямую в коде, в то время как `core/detector.py` уже давно берёт
все пороги (`conf_side`, `conf_rube`, `conf_cnn`, `iou_threshold`) из `AppSettings`.

Добавить в `AppSettings`:
```python
lane_conf_detect: float = 0.65
lane_conf_segment: float = 0.65
```
`LaneDetector.__init__(self, settings=None)` — принимать `settings` по аналогии с
`Detector`/`SignHandler`/`FinalHandler`, сохранять пороги в `self.CONF_LANE_DETECT`/
`self.CONF_LANE_SEGMENT`, использовать их вместо хардкода. Добавить UI-контролы в группу
"Обработка видео" (`settings_page.py`) рядом с существующими confidence-спинбоксами.

Также перевести импорт с легаси-шима на прямой:
```python
# было:
from configs.sign_config import model_lane_detect, model_lane_segment
# стало:
from configs.sign_models import model_lane_detect, model_lane_segment
```

## P.2 — Остальные потребители `configs.sign_config`

`processing/ocr_worker.py` и `server/map_server.py` — тоже до сих пор импортируют через
легаси-шим `configs/sign_config.py` (сам файл содержит явную просьбу «не добавляйте сюда
новый код — используйте sign_data.py / sign_models.py»). Перевести на прямые импорты из
`configs.sign_data` (`TYPE_SIGNS_WITH_TEXT`, `NAME_SIGNS_CITY`, `CODES_SIGNS`,
`SIGNS_WITH_VARIOUS_TEXT`, `TYPE_SIGNS_CITY`, `NAMES_SIGNS_BY_TYPE`). В `map_server.py`
имена сейчас в snake_case через алиасы (`type_signs_with_text = TYPE_SIGNS_WITH_TEXT` и
т.п. в реэкспорте `sign_config.py`) — либо переименовать использования в файле на
UPPER_CASE вслед за прямым импортом, либо явно алиасить через `as` при импорте, чтобы не
трогать остальной код файла без необходимости. После перевода всех потребителей — если
`configs/sign_config.py` больше никем не импортируется, рассмотреть его полное удаление
отдельным пунктом (но только после подтверждения через grep, это не входит в обязательный
минимум блока).

## P.3 — Завершить миграцию `print()` → `logging`

`STATUS.md` несколько раз объявлял эту миграцию завершённой — по факту (проверено grep'ом
на момент аудита) `print()` остаётся минимум в: `core/gpx_handler.py`,
`core/lane_detector.py`, `processing/detector_process_pool.py`, `ui/main_window.py`,
`ui/widgets/map_page.py`, `ui/widgets/dashboard_page.py`, `configs/settings.py`,
`ui/widgets/settings_page.py`, `processing/processing_controller.py`, `core/detector.py`,
`core/osm_snap.py`, `server/map_server.py`, `processing/ocr_pool.py`,
`ui/widgets/error_editor_page.py`, `ui/widgets/processing_page.py`.

**Приоритет №1 — `server/map_server.py`** (41 вызов `print()` на момент аудита, включая
горячие API-роуты `/api/signs`, `/api/track`). У модуля сейчас даже нет
`logger = logging.getLogger(__name__)` на уровне модуля — добавить.

Правило переноса уровня логирования (переиспользовать/расширить существующий
`fix_logging.py` как одноразовый скрипт-помощник, а не переписывать всё руками):
`ERROR`/`ОШИБКА`/`Exception` → `logger.error`; `WARNING`/`ВНИМАНИЕ` → `logger.warning`;
частые построчные логи внутри цикла обработки кадра → `logger.debug` (не `info` — иначе
раздувается лог-файл в проде); всё остальное → `logger.info`.

**Перепроверь актуальный список файлов заново** через
`grep -rl "print(" --include="*.py" .` перед началом — список выше зафиксирован на момент
аудита и мог измениться.

### Критерии приёмки Блока P

- [ ] `grep -rln "print(" --include="*.py" .` возвращает только файлы категорий
      `test_*`/`diagnose_*`/`check_*`/`benchmark_*`/`analyze_*` — ноль в `core/`,
      `processing/`, `server/`, `ui/`
- [ ] Пороги `lane_conf_detect`/`lane_conf_segment` настраиваются через Settings UI
- [ ] Ни один файл, кроме самого `configs/sign_config.py`, больше не импортирует из
      `configs.sign_config`

---

# БЛОК Q — Гигиена репозитория

## Q.1 — Консолидация исторических отчётов

В корне репозитория скопилось 25+ markdown-файлов отчётов сессий (`BLOCK_A*.md` —
`BLOCK_I*.md`, `AGENT_PROMPT_EXECUTION_REPORT*.md`, `SESSION_SUMMARY*.md`, `SUMMARY_*.md`,
`TEST_INSTRUCTIONS_*.md`, `TEST_PROCESS_POOL_FIX.md`, `WORKAROUND_PROCESS_POOL_DISABLED.md`,
`WORK_SUMMARY.md`, `AUDIT_REPORT.md`, `STATUS.md`), многие из которых частично
противоречат текущему состоянию кода (см. Блок P.3 — миграция логирования, объявленная
завершённой трижды, но незавершённая по факту).

**Действия:**
- Создать `docs/archive/`, перенести туда все перечисленные файлы, кроме
  `WHY_SINGLE_THREAD_FASTER.md` (это живой архитектурный документ с полезными выводами —
  либо оставить в корне/`docs/`, либо явно решить иначе, но не рассеивать бездумно).
- Создать один `CHANGELOG.md` в корне — краткая по-датовая история реально сделанного
  (сверяясь с фактическим кодом на момент написания записи, а не копируя старые claims).
- `STATUS.md` и `AUDIT_REPORT.md` — не плодить третий файл, а переписать актуальным
  единым документом, отражающим состояние **после** выполнения этого промпта (блоки M–S).

## Q.2 — Разнести скрипты по папкам

Переместить в `scripts/`: `diagnose_empty_geojson.py`, `diagnose_coordinates.py`,
`check_sign_data_duplicates.py`, `fix_logging.py`, `analyze_print_usage.py`,
`benchmark_detector.py`, `benchmark_end_to_end_cpu.py`, `test_detector_regression.py`,
`test_settings_ui.py`, `test_cnn_batching.py`.

`test_import.py`, `test_debug_gap.py`, `test_coordinates.py` — разовые debug-скрипты
конкретных прошлых сессий; для каждого осознанно решить: довести до pytest-совместимого
вида в `tests/`, либо удалить как исчерпавшие актуальность (не переносить не глядя).

## Q.3 — Файл зависимостей

Убедиться, что `requirements.txt` (или `pyproject.toml`) присутствует в репозитории и
содержит зафиксированные версии как минимум для тяжёлых/чувствительных зависимостей:
`torch`, `ultralytics`, `easyocr`, `PyQt6`, `opencv-python`, `shapely`, `pyproj`, `geopy`,
`flask`, `flask-socketio`, `flask-cors`, `gpxpy`, `geojson`, `joblib`, `requests`, и новую
из Блока M — `onnxruntime` (опционально `openvino`). Если файла нет или он неполный —
сгенерировать через `pip freeze` из рабочего venv проекта. Перепроверить `.gitattributes`
на отсутствие правил `*.txt`/`.txt` под Git LFS (эта проблема уже чинилась ранее согласно
`AUDIT_REPORT.md` — убедиться, что не откатилась).

### Критерии приёмки Блока Q

- [ ] В корне репозитория остаются только «живые» файлы (код, `CHANGELOG.md`, `README`,
      файл зависимостей, конфиги) — исторические отчёты в `docs/archive/`
- [ ] Диагностические/бенчмарк-скрипты — в `scripts/`
- [ ] `pip install -r requirements.txt` в чистом venv отрабатывает без ошибок

---

# БЛОК R — Тестирование и CI

## R.1 — CI pipeline

Добавить `.github/workflows/ci.yml` (уточнить у пользователя, если используется другая
CI-платформа) со стадиями:
1. checkout, setup Python
2. `pip install -r requirements.txt`
3. `python -m py_compile $(git ls-files '*.py')` — дешёвая защита от синтаксических ошибок
   (в истории проекта уже несколько раз вручную ловились именно такие баги)
4. `python scripts/check_sign_data_duplicates.py` — падать сборку при дублирующихся ключах
   в `sign_data.py` (сейчас это ручной одноразовый скрипт, никто не обязан его запускать)
5. `pytest tests/ -v`

Учесть: часть зависимостей (`torch`, `PyQt6`, `easyocr`) тяжёлые — использовать
`actions/cache` для pip. Веса моделей (`.pt`) в `.gitignore` и недоступны в CI — тесты,
требующие реальных весов, должны быть помечены `pytest.mark.skipif` по признаку наличия
файлов моделей, чтобы CI не падал из-за отсутствующих закрытых артефактов.

## R.2 — Regression-тест bearing-геометрии на реальном видео

Упоминался как TODO в нескольких `BLOCK_H_*` отчётах и так и не был выполнен. Принять
одно из двух решений явно (не оставлять TODO ещё раз):
- (a) записать короткий (10-20 сек) тестовый клип с известным перекрёстком, закоммитить
  через Git LFS вместе с baseline GeoJSON для сравнения;
- (b) если видео нельзя закоммитить (размер/лицензия) — задокументировать как ручной
  regression-чеклист в `docs/MANUAL_TESTING.md`, один раз и подробно, вместо повторения
  «TODO» в каждом следующем отчёте.

### Критерии приёмки Блока R

- [ ] CI зелёный на основной ветке
- [ ] `check_sign_data_duplicates.py` встроен в CI и красный при дублях
- [ ] Явное (не TODO) решение по regression-тесту bearing-геометрии

---

# БЛОК S — Редактируемая карта (наследие «Блока 4»)

Упоминался как нереализованный минимум в трёх разных отчётах
(`AGENT_PROMPT_EXECUTION_REPORT_turns_map_settings.md`,
`AGENT_PROMPT_EXECUTION_REPORT.md`, `SESSION_SUMMARY_turns_map_settings.md`) и ни разу не
начат. Это самый объёмный из блоков N–S — если бюджет сессии ограничен, стоит выполнить
его отдельной сессией после M–R, а не начинать частично.

## S.1 — `POST /api/sign` в `server/map_server.py`

Принимать `{type, lat, lon, azimuth, description}`, валидировать `type in CODES_SIGNS`.
У существующих знаков геометрия — `LineString` с двумя точками (для отрисовки
направления); для вручную добавленного знака естественной «линии» нет — синтезировать
вторую точку через уже существующий `CoordinateCalculation.point_at_distance(lat, lon,
azimuth)`, переиспользуя логику, а не изобретая новый формат геометрии. Добавить фичу в
загруженный GeoJSON, `_save_geojson()`, `socketio.emit("new_sign", ...)` — по аналогии со
стилем и обработкой ошибок уже существующих `api_sign_update`/`api_sign_delete`.

## S.2 — Расширить `PATCH /api/sign/<sign_id>`

Сейчас обрабатывает только `type`/`description`. Добавить опциональные `lat`/`lon`/
`azimuth` (или напрямую обе конечные точки линии, если фронтенд их прислал — предпочтительно,
поскольку драг маркера на карте естественно даёт точные новые координаты без обратного
пересчёта через азимут).

## S.3 — `templates/map.html`: draggable-маркеры + режим добавления

- Сделать `sign-marker` перетаскиваемыми (`draggable: true`), на `dragend` вызывать
  расширенный `PATCH` с новыми координатами из `e.target.getLatLng()`.
- Добавить кнопку в topbar «Добавить знак», переключающую режим клика по карте
  (`map.on('click', ...)`) с формой выбора типа (переиспользовать уже загружаемый
  `signTypes` из `/api/sign_types`), вызывающую новый `POST /api/sign`.

### Критерии приёмки Блока S

- [ ] Перетаскивание существующего маркера сохраняется — после перезагрузки страницы
      (`loadSigns()`) маркер остаётся в новой позиции (подтверждает, что PATCH реально
      записался в GeoJSON на диске, а не только в состояние фронтенда)
- [ ] Добавление нового знака через клик по карте переживает перезагрузку страницы

---

## Финальный чеклист сессии

- [ ] Блоки выполнены в порядке M → N → O → P → Q → R → (S — опционально/отдельно)
- [ ] Каждый блок закоммичен отдельно с осмысленным сообщением
- [ ] Обновлён единый актуальный статус-документ (Блок Q.1), а не создан очередной
      конкурирующий `SUMMARY_*.md`
- [ ] Для Блока M — реальные измеренные цифры бенчмарка присутствуют в отчёте, включая
      честный вывод, даже если он отрицательный
- [ ] Ни один пункт не помечен «✅ Done» без факта проверки агентом в этой же сессии
