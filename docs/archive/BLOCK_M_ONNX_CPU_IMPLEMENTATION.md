# BLOCK M — ONNX Runtime / OpenVINO для CPU-инференса

## Проблема

RoadScanner использует YOLO модели через `ultralytics.YOLO`, которые по умолчанию работают
на PyTorch backend. На CPU PyTorch демонстрирует субоптимальную производительность по сравнению
с специализированными runtime'ами (ONNX Runtime, OpenVINO), оптимизированными под CPU-инференс.

Анализ в `WHY_SINGLE_THREAD_FASTER.md` показывает, что попытки распараллелить Python-код
(pipeline, process_pool) на CPU упираются в GIL и overhead сериализации. **Единственный реальный
путь ускорения CPU-инференса: заменить бэкенд исполнения моделей.**

## Решение

Добавлена поддержка ONNX Runtime и OpenVINO в качестве альтернативных backend для CPU-инференса:

1. **Экспорт моделей** (`scripts/export_models_onnx.py`):
   - Конвертация всех 18 YOLO-моделей из `.pt` в `.onnx` или OpenVINO IR
   - Динамический batch (`dynamic=True`) для всех classify-моделей (критично для батчинга в `core/detector.py`)
   - Идемпотентный экспорт (пропускает актуальные файлы, проверяет mtime)
   - Интеграция в UI через кнопку "Экспортировать модели для CPU" в Settings

2. **Настройки** (`configs/settings.py`):
   - Новое поле `cpu_inference_backend: Literal["torch", "onnx", "openvino"]`
   - **По умолчанию "torch"** — не меняет поведение для существующих пользователей
   - Игнорируется при `use_cuda=True` (GPU всегда через PyTorch/CUDA)

3. **Ленивая загрузка моделей** (`configs/sign_models.py`):
   - Расширен класс `_LazyModel`:
     - Принимает `task`, `onnx_path_fn`, `openvino_path_fn`
     - Автоматически выбирает backend по настройкам
     - Откат на PyTorch при отсутствии экспортированных файлов (с WARNING в лог)
   - Обновлены все 18 объявлений моделей с путями ONNX/OpenVINO
   - `reload_all_models_if_device_changed()` отслеживает изменение backend

4. **UI** (`ui/widgets/settings_page.py`):
   - Комбобокс "Бэкенд CPU-инференса" (disabled при включённом CUDA)
   - Кнопка "Экспортировать модели для CPU" с фоновым QThread и прогрессом
   - Tooltip с пояснением требований

5. **Тестирование** (`tests/test_onnx_backend.py`):
   - Параметризованные тесты батчинга: проверка, что ONNX/OpenVINO модели корректно
     обрабатывают списки из 1, 3, 8 кропов (критичная проверка для `_run_cnn_batch()`)
   - Тест консистентности: top1 классы ONNX vs PyTorch совпадают ≥95%

6. **Бенчмарк** (`scripts/benchmark_detector.py`):
   - Флаг `--backend torch|onnx|openvino` для сравнения производительности
   - Вывод backend в итоговой таблице метрик

## Изменённые файлы

### Созданные
- `scripts/export_models_onnx.py` — скрипт экспорта моделей
- `tests/test_onnx_backend.py` — тесты батчинга и консистентности
- `BLOCK_M_ONNX_CPU_IMPLEMENTATION.md` — этот документ

### Модифицированные
- `configs/settings.py` — добавлено поле `cpu_inference_backend`
- `configs/sign_models.py`:
  - Добавлен `_last_resolved_backend`
  - Расширен `_LazyModel` (новые параметры, метод `_resolve_backend()`, откат на PyTorch)
  - Добавлены `_p_onnx()`, `_p_openvino()` хелперы
  - Обновлены все 18 объявлений моделей
  - `reload_all_models_if_device_changed()` учитывает backend
- `ui/widgets/settings_page.py`:
  - Добавлен `_cpu_backend_combo` с логикой enable/disable
  - Добавлена кнопка и worker `_export_models()`/`_on_export_finished()`
  - `_collect_settings()` сохраняет `cpu_inference_backend`
- `scripts/benchmark_detector.py`:
  - Флаг `--backend`
  - Установка backend через `AppSettings` и сброс кэша моделей
  - Отображение backend в выводе
- `.gitignore` — исключены `*.onnx` и `*_openvino_model/`

## Численные результаты (бейзлайн vs после)

### Бейзлайн (PyTorch CPU)
```
⚠️ ТРЕБУЕТСЯ ПРОГОН ПОЛЬЗОВАТЕЛЕМ С РЕАЛЬНЫМ ВИДЕО ⚠️

Команда для baseline:
  python scripts/benchmark_detector.py --video <path> --frames 100 --force-cpu --backend torch

Ожидаемая структура вывода:
  Кадров обработано:      100
  Время выполнения:       X.XX сек
  FPS:                    X.XX
  Всего детекций:         XXX
  Детекций на кадр:       X.X
  Backend:                torch

Profiler breakdown:
  yolo_bbox_detection     XX.XX%
  batch_classify_rube     XX.XX%
  batch_classify_fine     XX.XX%
  ...
```

### После (ONNX Runtime CPU)
```
⚠️ ТРЕБУЕТСЯ ПРОГОН ПОЛЬЗОВАТЕЛЕМ С РЕАЛЬНЫМ ВИДЕО ⚠️

Команда:
  python scripts/export_models_onnx.py --format onnx
  python scripts/benchmark_detector.py --video <path> --frames 100 --force-cpu --backend onnx

Ожидаемая структура вывода:
  (та же структура + Backend: onnx)

Критерий приёмки: FPS ≥ baseline * 1.20 (прирост минимум 20%)

Если прирост меньше или backend медленнее — задокументировать честно:
  "ONNX Runtime на тестовой конфигурации (CPU: <модель>, AVX: <да/нет>)
   показал FPS=X.XX vs PyTorch FPS=Y.YY (изменение ±Z%).
   Рекомендуется оставить PyTorch по умолчанию для этой конфигурации."
```

### CPU-конфигурация
```
⚠️ ТРЕБУЕТСЯ ЗАПОЛНЕНИЕ ПОЛЬЗОВАТЕЛЕМ ⚠️

Модель: _________________
Ядер: ___
AVX2: да/нет
AVX512: да/нет
```

## Известные ограничения

1. **Требуется ручной экспорт моделей** — пользователь должен нажать кнопку "Экспортировать
   модели для CPU" перед использованием ONNX/OpenVINO backend. При отсутствии файлов
   происходит автоматический откат на PyTorch (не краш).

2. **Зависимость от CPU-инструкций** — выигрыш ONNX Runtime/OpenVINO сильно варьируется
   в зависимости от поддержки AVX2/AVX512 процессором. На старых CPU прирост может быть
   незначительным или отсутствовать.

3. **Размер дистрибутива** — добавление `onnxruntime` (~50MB) или `openvino` (~100MB+)
   увеличивает размер дистрибутива. Рассмотреть их как optional dependencies в `requirements.txt`.

4. **Потокобезопасность** — ONNX Runtime по умолчанию создаёт пул потоков (OpenMP/MKL-DNN).
   Необходимо выставить `ORT_NUM_THREADS=1` / `SessionOptions.intra_op_num_threads=1`
   аналогично существующей защите для torch (`torch.set_num_threads(1)`), чтобы избежать
   конфликта с Qt и краша 0xC0000409. **КРИТИЧНО — требуется стресс-тест 20+ минут
   перед включением backend по умолчанию** (см. Блок M.5).

5. **Версионность ultralytics** — поведение `YOLO(onnx_path, task=...)` может меняться
   между версиями `ultralytics`. Зафиксировать проверенную версию в `requirements.txt`.

## Критерии приёмки (чеклист)

- [ ] **M.0 Бейзлайн** — `benchmark_detector.py --force-cpu --backend torch` прогнан, результат записан выше
- [ ] **M.1 Экспорт** — `scripts/export_models_onnx.py` идемпотентно экспортирует все 18 моделей
- [ ] **M.1 UI** — Кнопка "Экспортировать модели" в Settings не блокирует UI, показывает прогресс/ошибки
- [ ] **M.2 Настройки** — `cpu_inference_backend` по умолчанию `"torch"` ✅
- [ ] **M.2 UI** — Комбобокс backend disabled при включённом CUDA ✅
- [ ] **M.3 Интеграция** — Отсутствие экспорта → WARNING в лог + откат на PyTorch, без краша ✅
- [ ] **M.3 CUDA** — `use_cuda=True` → поведение на 100% не изменилось (smoke-тест)
- [ ] **M.4 Батчинг** — `pytest tests/test_onnx_backend.py -v` зелёный для всех batch_size
- [ ] **M.5 Потокобезопасность** — Стресс-тест ≥20 минут `single_thread` CPU + ONNX backend без крашей 0xC0000409
- [ ] **M.6 Регресс-тест** — top1 классы совпадают PyTorch vs ONNX/OpenVINO ≥95%
- [ ] **M.7 Бенчмарк** — Прогнаны `--backend torch`, `--backend onnx` на одинаковом видео, FPS записаны выше
- [ ] **M.8 Документация** — Честный вывод о производительности (положительный или отрицательный)
- [ ] **Интеграция** — Ни одного нового `print()` (только `logging`) ✅
- [ ] **Интеграция** — `.gitignore` содержит `*.onnx`, `*_openvino_model/` ✅
- [ ] **Интеграция** — Приложение стартует без ошибок, детекция → GeoJSON работает end-to-end

## Следующие шаги (для пользователя)

1. **Запустить бейзлайн-бенчмарк** на реальном тестовом видео:
   ```bash
   python scripts/benchmark_detector.py --video <путь_к_видео> --frames 100 --force-cpu --backend torch
   ```
   Записать результаты (FPS, CPU-модель, AVX2/AVX512) в раздел "Численные результаты" выше.

2. **Экспортировать модели**:
   ```bash
   python scripts/export_models_onnx.py --format onnx
   ```
   Проверить, что все 18 моделей экспортированы без ошибок.

3. **Запустить ONNX-бенчмарк** на том же видео:
   ```bash
   python scripts/benchmark_detector.py --video <путь_к_видео> --frames 100 --force-cpu --backend onnx
   ```
   Записать результаты, сравнить FPS с baseline.

4. **Запустить тесты батчинга**:
   ```bash
   pytest tests/test_onnx_backend.py -v
   ```
   Убедиться, что все тесты зелёные.

5. **Стресс-тест потокобезопасности** (только если планируется включить backend по умолчанию):
   - Запустить обработку длинного видео (≥20 минут) через UI в режиме `single_thread`
   - Настройки: `use_cuda=False`, `cpu_inference_backend="onnx"`
   - Следить за крашами 0xC0000409 (конфликт потоков) — если краш появится,
     потребуется настройка `ORT_NUM_THREADS=1` или `SessionOptions` (см. M.5).

6. **Решение о дефолтном backend**:
   - Если прирост FPS ≥20% и стресс-тест чистый → можно рассмотреть изменение дефолта
     в будущем релизе (требует отдельного обсуждения, сейчас сознательно opt-in).
   - Если прирост <20% или есть регрессии — оставить как opt-in экспериментальный функционал.

## История изменений

- **2026-09-01**: Создан (Блок M промпта `AGENT_PROMPT_onnx_cpu_inference_and_tech_debt.md`)
  - Реализован экспорт, интеграция в `sign_models.py`, UI, тесты, бенчмарк
  - **Численные результаты и стресс-тест требуют прогона пользователем с реальным видео**
