# 🚀 Инструкция по сборке RoadScanner (Signer PRIME) с PyInstaller

## Предварительные требования

✅ **Все необходимые файлы и папки присутствуют:**
- `main.py` — точка входа
- `signer.spec` — конфигурация сборки
- `signs.json` — конфигурация знаков
- `assets/icon.ico` — иконка приложения
- Папки с моделями: `CNN_side/`, `lane_guidance_models/`, `small_models/`
- Папки с ресурсами: `sings/`, `sings_text/`, `static/`, `templates/`

## Шаги сборки

### 1. Установите зависимости для сборки

```bash
pip install -r requirements-dev.txt
```

Это установит `pyinstaller>=6.0.0` и другие dev-зависимости.

### 2. Запустите сборку

```bash
pyinstaller signer.spec --noconfirm
```

**Параметры:**
- `--noconfirm` — автоматически перезаписывает старую сборку без запроса подтверждения

### 3. Результат сборки

После успешной сборки в папке `dist/Signer/` будет:
- `Signer.exe` — исполняемый файл приложения
- `_internal/` — папка с зависимостями, моделями и ресурсами

**Режим сборки:** `--onedir` (exe + папка `_internal`)

⚠️ **ВАЖНО:** Приложение работает только вместе с папкой `_internal/`! Не перемещайте `Signer.exe` отдельно от неё.

## Дополнительные опции

### Очистка предыдущей сборки

```bash
# Удалить старые сборки
rmdir /s /q build dist
pyinstaller signer.spec --noconfirm
```

### Сборка с подробным логом

```bash
pyinstaller signer.spec --noconfirm --log-level=DEBUG
```

## Известные особенности

### 1. ffmpeg не включён в сборку

`server/map_server.py` использует системный `ffmpeg` через subprocess для транскодирования видеоклипов.

**Решение:** Убедитесь, что `ffmpeg.exe` доступен в системе:
- Установите ffmpeg и добавьте в PATH
- Или поместите `ffmpeg.exe` рядом с `Signer.exe`

### 2. Опциональные бэкенды (ONNX/OpenVINO)

Если вы **НЕ используете** ONNX или OpenVINO бэкенды, можете удалить их из `signer.spec`:

```python
# Закомментируйте эти строки:
# binaries += collect_dynamic_libs('onnxruntime')
# binaries += collect_dynamic_libs('openvino')
# datas += collect_data_files('onnxruntime')
# datas += collect_data_files('openvino')
# hiddenimports += collect_submodules('onnxruntime')
# hiddenimports += collect_submodules('openvino')
```

Это **уменьшит размер** итоговой сборки.

### 3. Консольное окно

В `signer.spec` установлено `console=False`, поэтому при запуске `Signer.exe` консольное окно **не будет** открываться.

Для отладки можете временно изменить на `console=True`:

```python
exe = EXE(
    ...
    console=True,  # Включить консоль для отладки
    ...
)
```

## Проверка сборки

После сборки запустите:

```bash
dist\Signer\Signer.exe
```

Проверьте:
- ✅ Приложение запускается без ошибок
- ✅ Графический интерфейс отображается корректно
- ✅ Модели загружаются (нет ошибок "model not found")
- ✅ Карта открывается в браузере (Flask-сервер работает)

## Устранение проблем

### Ошибка "No module named 'X'"

Добавьте модуль в `hiddenimports` в `signer.spec`:

```python
hiddenimports += ['X']
```

### Ошибка "File not found: model.pt"

Убедитесь, что папка с моделями включена в `datas` в `signer.spec`:

```python
datas.append(('CNN_side', 'CNN_side'))
```

### Большой размер сборки

1. Удалите ненужные бэкенды (ONNX/OpenVINO) из spec-файла
2. Используйте UPX для сжатия (не рекомендуется для нейросетевых моделей):

```python
coll = COLLECT(
    ...
    upx=True,
    ...
)
```

## Размер итоговой сборки

Ожидаемый размер: **~2-5 ГБ** (в зависимости от включённых бэкендов)

Основной вес:
- PyTorch + TorchVision: ~1-2 ГБ
- Модели YOLO и классификаторы: ~500 МБ - 1 ГБ
- OpenVINO/ONNX Runtime: ~500 МБ - 1 ГБ каждый
- Остальные зависимости: ~500 МБ

## Дополнительные ресурсы

- [Документация PyInstaller](https://pyinstaller.org/en/stable/)
- [PyInstaller Hooks](https://github.com/pyinstaller/pyinstaller-hooks-contrib)

---

**Успешной сборки! 🎉**
