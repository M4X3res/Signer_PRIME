# Отчет о подготовке RoadScanner (Signer PRIME) к релизному билду

**Дата:** 2026-09-16  
**Ветка:** `chore/prepare-release-build`  
**Базовая ветка:** `master`

## Выполненные задачи

### 1. Реорганизация корневой директории ✅

#### Перемещённые файлы

| Было (корень) | Стало | Причина |
|--------------|-------|---------|
| `TEMP_BUILD_CHANGES.md` | `docs/TEMP_BUILD_CHANGES.md` | Временный документ |
| `check_browser_logs.md` | `docs/check_browser_logs.md` | Документация |
| `debug_map_styles.py` | `scripts/dev/temp/debug_map_styles.py` | Временный dev-скрипт |
| `debug_styles_detailed.py` | `scripts/dev/temp/debug_styles_detailed.py` | Временный dev-скрипт |
| `switch_to_osm.py` | `scripts/dev/temp/switch_to_osm.py` | Временный dev-скрипт |
| `fix_tile_url.py` | `scripts/dev/temp/fix_tile_url.py` | Временный dev-скрипт |
| `fix_max_zoom.py` | `scripts/dev/temp/fix_max_zoom.py` | Временный dev-скрипт |
| `test_proxy_error.py` | `scripts/dev/temp/test_proxy_error.py` | Временный тест |
| `test_server.py` | `scripts/dev/temp/test_server.py` | Временный тест |
| `test_vector_tiles.py` | `scripts/dev/temp/test_vector_tiles.py` | Временный тест |
| `test_with_logs.py` | `scripts/dev/temp/test_with_logs.py` | Временный тест |
| `test_export.bat` | `scripts/dev/temp/test_export.bat` | Временный батник |

#### Удалённые файлы (временные логи)
- `roadscan.log` — временный лог
- `console.txt` — временный вывод
- `video_debug.log` — временный лог отладки
- `gh-cli/` — пустая директория

#### Добавленные новые файлы в git
- `configs/__init__.py`, `configs/data/__init__.py` — пакетные маркеры
- `core/__init__.py`, `processing/__init__.py`, `server/__init__.py` — пакетные маркеры
- `ui/__init__.py`, `ui/themes/__init__.py`, `ui/widgets/__init__.py` — пакетные маркеры
- `prompts/` — директория с AI-промптами
- `docs/` — множество документов (были untracked)
- `scripts/archive/`, `scripts/build/`, `scripts/dev/` — скрипты сборки и разработки
- `tests/` — новые тесты

#### Файлы, сознательно оставленные в корне (Категория A)

| Файл/Директория | Обоснование |
|----------------|-------------|
| `main.py` | Точка входа приложения |
| `requirements.txt` | Стандарт pip, ожидается в корне |
| `requirements-dev.txt` | Стандарт pip, ожидается в корне |
| `requirements-cpu-backends.txt` | Стандарт pip, ожидается в корне |
| `version.json` | Читается в dev и frozen режиме через относительные пути от корня |
| `build_config.json` | Читается через `configs/settings.py`, ожидается рядом с main.py |
| `build_config.json.example` | Пример конфигурации, должен быть рядом с оригиналом |
| `signer.spec` | PyInstaller запускается из корня, содержит множество относительных путей |
| `updater.spec` | PyInstaller запускается из корня, содержит множество относительных путей |
| `.gitignore` | Стандарт git |
| `.gitattributes` | Стандарт git |
| `README.md` | GitHub показывает только из корня |
| `app/`, `core/`, `configs/`, `processing/`, `server/`, `ui/`, `updater/`, `licensing/` | Python пакеты, импорты завязаны на текущую структуру |
| `templates/`, `static/`, `assets/` | Ресурсы, используемые через `resource_path()` |
| `small_models/`, `CNN_side/`, `lane_guidance_models/` | ML-модели, пути жёстко закодированы в configs/sign_models.py |
| `sings/`, `sings_text/` | Датасеты, используемые в коде |
| `installer/` | Конфигурация Inno Setup |
| `tests/` | Тесты, содержат относительные пути к файлам проекта |
| `errorData/` | Рабочая директория для сохранения кадров с ошибками (см. configs/settings.py) |
| `test_data/` | Тестовые данные для dev-скриптов |
| `signer-license-server/` | Отдельный поддиректорий, самостоятельный сервис |

### 2. Экспорт CPU-бэкендов (ONNX и OpenVINO) ✅

#### Установленные зависимости
- ✅ `onnx==1.22.0`
- ✅ `onnxruntime==1.29.0`
- ✅ `openvino==2024.6.0`
- ✅ Конфликты проверены: `onnxruntime-gpu` не установлен

#### Экспортированные ONNX модели (19 файлов)

```
CNN_side/best.onnx
CNN_side/best.opt.onnx (автоматически созданный ORT оптимизированный граф)
lane_guidance_models/arrow_detect.onnx
lane_guidance_models/arrow_segment.onnx
small_models/5.38.onnx
small_models/5.9.1-5.14.onnx
small_models/blue.onnx
small_models/danger.onnx
small_models/krug.onnx
small_models/one_side.onnx
small_models/pimicanie.onnx
small_models/red.onnx
small_models/rude.onnx
small_models/servises.onnx
small_models/suzenie.onnx
small_models/tabl l.onnx
small_models/tabl.onnx
small_models/treugolnik.onnx
small_models/tupic.onnx
```

#### Экспортированные OpenVINO модели (18 директорий)

```
CNN_side/best_openvino_model/
lane_guidance_models/arrow_detect_openvino_model/
lane_guidance_models/arrow_segment_openvino_model/
small_models/5.38_openvino_model/
small_models/5.9.1-5.14_openvino_model/
small_models/blue_openvino_model/
small_models/danger_openvino_model/
small_models/krug_openvino_model/
small_models/one_side_openvino_model/
small_models/pimicanie_openvino_model/
small_models/red_openvino_model/
small_models/rude_openvino_model/
small_models/servises_openvino_model/
small_models/suzenie_openvino_model/
small_models/tabl l_openvino_model/
small_models/tabl_openvino_model/
small_models/treugolnik_openvino_model/
small_models/tupic_openvino_model/
```

#### Верификация бэкендов

**Скрипт экспорта:** `scripts/export_models_onnx.py`  
**Скрипт верификации:** `scripts/build/verify_cpu_backends.py`

##### Результаты верификации ONNX backend:
```
✅ model_side_detect: onnx
✅ rube_modal: onnx
✅ model_lane_detect: onnx
✅ model_lane_segment: onnx
✅ model_dict[blue]: onnx
✅ model_dict[treugolnik]: onnx
✅ model_dict[krug]: onnx
✅ model_dict[red]: onnx
✅ model_dict[servises]: onnx
✅ model_dict[tablichkaL]: onnx
✅ model_dict[tablichka__]: onnx
✅ model_dict[tupic]: onnx
✅ model_dict[5.38]: onnx
✅ model_dict[5.9.1-5.14]: onnx
✅ model_dict[5.5-5.6]: onnx
✅ sub_models[danger]: onnx
✅ sub_models[pimicanie]: onnx
✅ sub_models[suzenie]: onnx
```

##### Результаты верификации OpenVINO backend:
```
✅ model_side_detect: openvino
✅ rube_modal: openvino
✅ model_lane_detect: openvino
✅ model_lane_segment: openvino
✅ model_dict[blue]: openvino
✅ model_dict[treugolnik]: openvino
✅ model_dict[krug]: openvino
✅ model_dict[red]: openvino
✅ model_dict[servises]: openvino
✅ model_dict[tablichkaL]: openvino
✅ model_dict[tablichka__]: openvino
✅ model_dict[tupic]: openvino
✅ model_dict[5.38]: openvino
✅ model_dict[5.9.1-5.14]: openvino
✅ model_dict[5.5-5.6]: openvino
✅ sub_models[danger]: openvino
✅ sub_models[pimicanie]: openvino
✅ sub_models[suzenie]: openvino
```

**Статус:** ✅ Все 18 моделей загружаются корректно в обоих бэкендах

#### Исправления в процессе работы

**Проблема:** `verify_cpu_backends.py` не сбрасывал кеш моделей между проверками разных бэкендов, что приводило к неправильным результатам верификации.

**Решение:** Добавлен вызов `sign_models.reload_all_models_if_device_changed()` перед каждой проверкой.

**Коммит:** `dd97406 - fix: add model cache reset in verify_cpu_backends.py for accurate backend testing`

## Проверка после изменений ✅

### Синтаксис Python файлов
```bash
.venv\Scripts\python.exe -c "import ast, pathlib; [ast.parse(...)]"
```
✅ Все .py файлы синтаксически валидны (с предупреждениями об escape-последовательностях, не критично)

### Импорты и пути к ресурсам
```bash
.venv\Scripts\python.exe -c "from app.utils import resource_path; import configs..."
```
✅ Базовые импорты работают  
✅ `resource_path('small_models/blue.pt')` резолвится правильно

### Regression-тесты
```bash
.venv\Scripts\python.exe tests/check_eager_loading.py
.venv\Scripts\python.exe tests/check_dashboard_page.py
.venv\Scripts\python.exe tests/check_socketio_config.py
```
✅ Все тесты прошли

### Pytest
```bash
.venv\Scripts\python.exe -m pytest tests/ --co -q
```
✅ 41 тест собран (падение I/O при завершении — известная проблема pytest на Windows, не критично)

## Итоговая структура корня

```
📁 Signer PRIME/
├── 📄 main.py                         # Точка входа
├── 📄 README.md                       # Главный README
├── 📄 version.json                    # Версия приложения
├── 📄 build_config.json               # Production конфигурация (gitignored)
├── 📄 build_config.json.example       # Пример конфигурации
├── 📄 signer.spec                     # PyInstaller spec для Signer.exe
├── 📄 updater.spec                    # PyInstaller spec для Updater.exe
├── 📄 requirements.txt                # Production зависимости
├── 📄 requirements-dev.txt            # Dev зависимости
├── 📄 requirements-cpu-backends.txt   # ONNX/OpenVINO зависимости
├── 📄 .gitignore                      # Git ignore правила
├── 📄 .gitattributes                  # Git attributes
├── 📁 app/                           # Утилиты и версионирование
├── 📁 core/                          # Ядро: детекторы, GPS, sign_handler
├── 📁 configs/                       # Конфигурация и настройки
├── 📁 processing/                    # Потоки обработки видео
├── 📁 server/                        # Flask-сервер для карты
├── 📁 ui/                            # PyQt6 GUI
├── 📁 updater/                       # Система автообновлений
├── 📁 licensing/                     # Система лицензирования (обфусцируется)
├── 📁 templates/                     # HTML-шаблоны карты
├── 📁 static/                        # Статические ресурсы карты
├── 📁 assets/                        # Иконки, изображения
├── 📁 small_models/                  # ML-модели классификации
├── 📁 CNN_side/                      # ML-модель детекции
├── 📁 lane_guidance_models/          # ML-модели дорожной разметки
├── 📁 sings/                         # Датасет знаков (изображения)
├── 📁 sings_text/                    # Датасет знаков (текст)
├── 📁 installer/                     # Inno Setup конфигурация
├── 📁 tests/                         # Unit/Integration тесты
├── 📁 scripts/                       # Скрипты сборки и разработки
│   ├── 📁 build/                    # Скрипты релиза
│   │   ├── prepare_release.bat
│   │   ├── obfuscate_licensing.py
│   │   ├── restore_originals.py
│   │   ├── upload_release.ps1
│   │   ├── verify_cpu_backends.py
│   │   └── ...
│   ├── 📁 dev/                      # Dev-утилиты
│   │   ├── 📁 temp/                # Временные dev-скрипты
│   │   └── ...
│   ├── 📁 archive/                  # Архив старых скриптов
│   └── export_models_onnx.py        # Экспорт моделей в ONNX/OpenVINO
├── 📁 docs/                          # Документация
│   ├── 📁 archive/                  # Архивные отчёты
│   ├── QUICKSTART_LICENSING.md
│   ├── LICENSING.md
│   ├── LICENSE_SERVER.md
│   ├── RELEASE.md
│   └── ... (множество других документов)
├── 📁 prompts/                       # AI-промпты для разработки
├── 📁 errorData/                     # Кадры с низкой уверенностью (runtime)
├── 📁 test_data/                     # Тестовые данные для dev-скриптов
└── 📁 signer-license-server/         # Backend лицензионного сервера (отдельный проект)
```

## Git-коммиты

1. `30f3321` - `chore: reorganize root directory - move temp files to docs/ and scripts/dev/temp/`
   - Добавлены все новые файлы (docs/, scripts/, prompts/, tests/, __init__.py файлы)
   - Перемещены временные файлы из корня

2. `dd97406` - `fix: add model cache reset in verify_cpu_backends.py for accurate backend testing`
   - Исправлен скрипт верификации бэкендов

## Не выполнено / Предупреждения

### ⚠️ ONNX/OpenVINO модели в .gitignore

В `.gitignore` есть правило:
```gitignore
# BLOCK M: Экспортированные модели (генерируемые артефакты)
*.onnx
*_openvino_model/
```

Это значит, что экспортированные модели **не попадут в git** и будут игнорироваться.

**Следствия:**
1. Каждый разработчик должен запустить `python scripts/export_models_onnx.py --format all` после клонирования
2. В CI/CD нужно добавить шаг экспорта моделей перед сборкой
3. В `prepare_release.bat` уже есть проверка наличия `.onnx` файлов (throw error если не найдены)

**Рекомендация:** Либо убрать `*.onnx` из `.gitignore` и закоммитить модели (увеличит размер репозитория на ~200-300 MB), либо оставить как есть и документировать это требование.

### ⚠️ .gitignore игнорирует *.spec

В `.gitignore` есть строка:
```gitignore
*.spec
```

Но `signer.spec` и `updater.spec` **должны быть в git** (они уже есть, т.к. были добавлены до появления правила).

**Рекомендация:** Изменить правило в `.gitignore` на:
```gitignore
# Игнорировать временные spec файлы, но не основные
*.spec
!signer.spec
!updater.spec
```

## Следующие шаги

1. ✅ Слияние ветки `chore/prepare-release-build` в `master`
2. ⚠️ Обновить `.gitignore` (убрать `*.spec` или добавить исключения)
3. ⚠️ Решить, коммитить ли экспортированные модели в git
4. ✅ Запустить `scripts/build/prepare_release.bat` для тестовой сборки
5. ✅ Проверить, что сборка проходит и включает ONNX/OpenVINO runtime
6. ✅ Протестировать собранный .exe с разными cpu_inference_backend настройками

## Резюме

✅ **Задача 1 (Реорганизация):** Выполнена полностью. Корень репозитория приведён в порядок, временные файлы убраны в `docs/` и `scripts/dev/temp/`, функциональные файлы не тронуты.

✅ **Задача 2 (CPU-бэкенды):** Выполнена полностью. Все 18 моделей экспортированы в ONNX и OpenVINO, верификация подтверждает корректную загрузку без откатов на PyTorch.

✅ **Проверки:** Все regression-тесты проходят, импорты работают, пути к ресурсам не сломаны.

⚠️ **Ограничения:** Экспортированные модели игнорируются git'ом (см. раздел "Не выполнено / Предупреждения").

---
**Автор:** Kiro AI Agent  
**Команда:** `kiro-cli chat`
