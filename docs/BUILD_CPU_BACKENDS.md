# CPU-бэкенды в Signer PRIME v2.0.1+

## Обзор

Начиная с версии 2.0.1, Signer PRIME **обязательно** поддерживает три инференс-бэкенда:
- **PyTorch** (по умолчанию, если CUDA доступна)
- **ONNX Runtime** (CPU-оптимизированный)
- **OpenVINO** (CPU-оптимизированный, особенно для Intel CPU)

Это обеспечивает:
- Улучшенную производительность на CPU-only системах (до 2-3x быстрее PyTorch CPU)
- Меньшее потребление памяти
- Лучшую стабильность на машинах без GPU

## Требования для сборки релиза

### 1. Установка зависимостей

```bash
pip install -r requirements.txt
```

Файл `requirements.txt` теперь включает:
```
onnx>=1.22.0
onnxruntime>=1.29.0  # CPU-only
openvino>=2024.0
```

Для экспорта моделей также нужен (только на машине сборки):
```bash
pip install openvino-dev>=2024.0
```

### 2. Экспорт моделей

**Автоматически** при запуске `scripts\build\prepare_release.bat` (шаг 3/9).

**Вручную:**
```bash
# Экспорт в оба формата (рекомендуется)
python scripts/export_models_onnx.py --format all

# Только ONNX
python scripts/export_models_onnx.py --format onnx

# Только OpenVINO
python scripts/export_models_onnx.py --format openvino

# Принудительный реэкспорт (игнорировать существующие)
python scripts/export_models_onnx.py --format all --force
```

**Результат:**
```
CNN_side/
├── best.pt                    # Исходная PyTorch модель
├── best.onnx                  # Экспортированная ONNX
└── best_openvino_model/       # Экспортированная OpenVINO
    ├── best.xml
    └── best.bin

lane_guidance_models/
├── arrow_detect.pt
├── arrow_detect.onnx
├── arrow_detect_openvino_model/
├── arrow_segment.pt
├── arrow_segment.onnx
└── arrow_segment_openvino_model/

small_models/
├── rude.pt, rude.onnx, rude_openvino_model/
├── blue.pt, blue.onnx, blue_openvino_model/
└── ... (17 классификационных моделей)
```

### 3. Верификация

**Автоматически** при запуске `scripts\build\prepare_release.bat` (шаг 6/9).

**Вручную:**
```bash
python scripts\build\verify_cpu_backends.py
```

Скрипт:
1. Временно переключает `cpu_inference_backend` на `"onnx"` и `"openvino"`
2. Вызывает `configs.sign_models.verify_backend_active()`
3. Проверяет, что **все** модели загружаются с правильным backend
4. Выводит таблицу: `model_name → actual_backend`

**Пример успешной верификации:**
```
================================================================================
Проверка backend: ONNX
================================================================================

Результаты проверки для ONNX:
------------------------------------------------------------
✅ model_side_detect: onnx
✅ rube_modal: onnx
✅ model_lane_detect: onnx
✅ model_lane_segment: onnx
✅ model_dict[1.1]: onnx
✅ model_dict[1.10]: onnx
...

================================================================================
ИТОГОВАЯ СТАТИСТИКА
================================================================================

✅ ONNX: все модели загружены корректно
✅ OPENVINO: все модели загружены корректно

================================================================================
✅ ПРОВЕРКА ПРОЙДЕНА: все CPU-бэкенды работают корректно
================================================================================
```

**Пример неудачной верификации:**
```
❌ model_side_detect: torch (fallback)
❌ rube_modal: ERROR: ONNX model not found

================================================================================
❌ ПРОВЕРКА НЕ ПРОЙДЕНА: есть проблемы с CPU-бэкендами
Возможные причины:
  1. Не установлены onnxruntime/openvino пакеты
  2. Не экспортированы .onnx/*.openvino_model файлы
     (запустите: python scripts/export_models_onnx.py --format all)
  3. Ошибки при загрузке моделей (см. логи выше)
================================================================================
```

## Процесс сборки релиза

`scripts\build\prepare_release.bat` выполняет (v2.0.1+):

1. **[0/9]** Проверка конфигурации лицензионного сервера
2. **[1/9]** Проверка зависимостей (Python, PyInstaller, 7z)
3. **[2/9]** Очистка старых сборок
4. **[3/9]** 🆕 **Экспорт моделей** в ONNX и OpenVINO
   - Прерывает сборку, если экспорт упал
5. **[4/9]** Обфускация модулей лицензирования (опционально)
6. **[5/9]** Сборка PyInstaller (Signer.exe, Updater.exe)
   - `signer.spec` проверяет наличие `onnxruntime`/`openvino` в venv
   - Проверяет наличие экспортированных `.onnx`/`*_openvino_model`
   - **Прерывает сборку**, если что-то отсутствует
7. **[6/9]** 🆕 **Верификация CPU-бэкендов**
   - Прерывает сборку, если бэкенды откатываются на PyTorch
8. **[7/9]** Создание многотомного архива
9. **[8/9]** Вычисление SHA-256 чексумм
10. **[9/9]** Подготовка папки `release/`

## Что изменилось в signer.spec (v2.0.1)

### До (v2.0.0):
```python
# Опциональные CPU-бэкенды — тихо игнорируются, если не установлены
binaries += collect_dynamic_libs('onnxruntime')
binaries += collect_dynamic_libs('openvino')
```

### После (v2.0.1):
```python
# Обязательные CPU-бэкенды — прерывают сборку, если не установлены
onnx_installed = check_package_installed('onnxruntime')
if onnx_installed:
    binaries += collect_dynamic_libs('onnxruntime')
    print(f"✅ ONNX Runtime: найдено {len(onnx_libs)} библиотек")
else:
    raise RuntimeError("ONNX Runtime отсутствует...")

# Аналогично для OpenVINO
```

```python
# Проверка наличия экспортированных моделей
onnx_models = glob.glob(os.path.join(ROOT, '*/**.onnx'))
if not onnx_models:
    raise RuntimeError("ONNX модели не найдены. Запустите: python scripts/export_models_onnx.py")
```

## Устранение проблем

### Ошибка: "ONNX Runtime не установлен"
```bash
pip install onnx onnxruntime
```

### Ошибка: "OpenVINO не установлен"
```bash
pip install openvino openvino-dev
```

### Ошибка: "ONNX модели не найдены"
```bash
python scripts/export_models_onnx.py --format onnx
```

### Ошибка: "OpenVINO модели не найдены"
```bash
python scripts/export_models_onnx.py --format openvino
```

### Ошибка: "Верификация CPU-бэкендов не пройдена"
Запустите вручную для деталей:
```bash
python scripts\build\verify_cpu_backends.py
```

Проверьте, что:
- Пакеты установлены (`pip show onnxruntime openvino`)
- Модели экспортированы (есть файлы `.onnx` и папки `*_openvino_model/`)
- Нет ошибок импорта (запустите `python -c "import onnxruntime; import openvino"`)

### Модели не экспортируются (ошибка ultralytics)
Убедитесь, что:
- Установлена совместимая версия ultralytics: `pip install ultralytics>=8.2.0`
- Исходные `.pt` файлы существуют и не повреждены
- Достаточно памяти для экспорта (может потребоваться до 4GB RAM)

## Тестирование в разработке

Без сборки релиза:
```bash
# 1. Установите зависимости
pip install onnx onnxruntime openvino openvino-dev

# 2. Экспортируйте модели
python scripts/export_models_onnx.py --format all

# 3. Запустите приложение
python main.py

# 4. В Settings → Performance выберите CPU inference backend:
#    - ONNX Runtime
#    - OpenVINO
#    - PyTorch (по умолчанию)

# 5. Проверьте в roadscan.log, что модели загружаются с правильным backend:
#    [sign_models] Загружена ONNX-модель: best.onnx (CPU mode)
#    [sign_models] Загружена OpenVINO-модель: best.xml
```

## Дополнительная информация

- **Документация релиза:** [docs/RELEASE.md](RELEASE.md)
- **Архивная документация CPU-оптимизаций:** [docs/archive/BLOCK_M_ONNX_CPU_IMPLEMENTATION.md](archive/BLOCK_M_ONNX_CPU_IMPLEMENTATION.md)
- **Скрипт экспорта:** `scripts/export_models_onnx.py`
- **Скрипт верификации:** `scripts/build/verify_cpu_backends.py`
- **Конфигурация моделей:** `configs/sign_models.py`
