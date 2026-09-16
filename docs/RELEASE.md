# Процесс релиза Signer PRIME

## Подготовка релиза

### 1. Обновите версию

Отредактируйте `version.json`:
```json
{
  "version": "1.0.5"
}
```

### 2. Установите зависимости (v2.0.1+)

**НОВОЕ в v2.0.1:** Для поддержки CPU-бэкендов (ONNX Runtime, OpenVINO) необходимо установить дополнительные зависимости:

```bash
pip install -r requirements.txt
```

Этот файл теперь включает:
- `onnx>=1.22.0`
- `onnxruntime>=1.29.0` (CPU-only)
- `openvino>=2024.0`

Для экспорта моделей также требуется (только на машине сборки):
```bash
pip install openvino-dev>=2024.0
```

### 3. Настройте URL сервера лицензий

**КРИТИЧЕСКИ ВАЖНО для production-сборки!**

1. Скопируйте `build_config.json.example` в `build_config.json`:
   ```bash
   copy build_config.json.example build_config.json
   ```

2. Откройте `build_config.json` и укажите реальный URL вашего сервера лицензий:
   ```json
   {
     "license_server_url": "https://your-license-server.run.app"
   }
   ```

3. Замените `https://your-license-server.run.app` на ваш реальный URL (Cloud Run или другой хостинг)

### 3. Настройте URL сервера лицензий

**КРИТИЧЕСКИ ВАЖНО для production-сборки!**

1. Скопируйте `build_config.json.example` в `build_config.json`:
   ```bash
   copy build_config.json.example build_config.json
   ```

2. Откройте `build_config.json` и укажите реальный URL вашего сервера лицензий:
   ```json
   {
     "license_server_url": "https://your-license-server.run.app"
   }
   ```

3. Замените `https://your-license-server.run.app` на ваш реальный URL (Cloud Run или другой хостинг)

**Примечание:** Скрипт сборки `prepare_release.bat` автоматически проверит, что URL не является заглушкой, и прервёт сборку, если вы забудете это сделать.

### 4. Подготовьте release notes

Создайте/обновите `docs/release_notes.txt`:
```
Signer PRIME v2.0.1

Новые возможности:
- Гарантированная поддержка ONNX Runtime и OpenVINO CPU-бэкендов
- Оптимизация производительности на CPU-only системах
- Автоматическая проверка работоспособности бэкендов при сборке

Исправления:
- Исправлен тихий откат с ONNX/OpenVINO на PyTorch

Системные требования:
- Windows 10/11 (64-bit)
- 8+ GB RAM
- 5+ GB свободного места на диске
```

### 5. Запустите сборку

```bash
scripts\build\prepare_release.bat
```

**Скрипт автоматически (обновлено в v2.0.1):**
- Проверит конфигурацию URL сервера лицензий
- Проверит зависимости (Python, PyInstaller, 7z)
- **НОВОЕ:** Экспортирует модели в ONNX и OpenVINO форматы
- Очистит старые сборки
- Обфусцирует модули лицензирования (если PyArmor установлен)
- Соберёт `Signer.exe` и `Updater.exe`
- **НОВОЕ:** Верифицирует работоспособность CPU-бэкендов
- Создаст многотомный архив (части по 100MB)
- Вычислит SHA-256 чексуммы
- Подготовит файлы в папке `release/`

**Что может пойти не так:**

1. **Ошибка экспорта моделей** (шаг 3/9):
   - Убедитесь, что установлены `onnx`, `onnxruntime`, `openvino`, `openvino-dev`
   - Убедитесь, что исходные `.pt` файлы моделей существуют в `CNN_side/`, `lane_guidance_models/`, `small_models/`

2. **Ошибка сборки PyInstaller** (шаг 5/9):
   - Проверьте, что `signer.spec` находит экспортированные модели
   - Проверьте логи PyInstaller на наличие RuntimeError

3. **Ошибка верификации CPU-бэкендов** (шаг 6/9):
   - Это означает, что ONNX Runtime или OpenVINO не работают в собранном приложении
   - Проверьте, что модели экспортированы корректно
   - Проверьте логи верификации для деталей

**Результат:**
```
release/
├── Signer.7z.001      # Часть 1 архива
├── Signer.7z.002      # Часть 2 архива
├── Signer.7z.003      # ...
├── checksum.sha256    # Чексуммы всех частей
├── release_notes.txt  # Описание релиза
├── README.md          # Общая документация
└── BUILD_AUTOUPDATE.md # Документация по автообновлению
```

### 6. Проверьте сборку

1. Убедитесь, что все файлы созданы в `release/`
2. Проверьте размеры архивов (части по ~100MB)
3. Просмотрите `release_notes.txt`

---

## Публикация релиза на GitHub

### Автоматическая загрузка (рекомендуется)

```powershell
.\scripts\build\upload_release.ps1
```

**Требования:**
- [GitHub CLI](https://cli.github.com/) установлен
- Авторизация: `gh auth login`

**Скрипт автоматически:**
- Определит версию из `version.json`
- Найдёт репозиторий из git remote
- Создаст релиз с тегом `v1.0.5`
- Загрузит все файлы из `release/`
- Откроет страницу релиза в браузере

**Опции:**
```powershell
# Создать черновик
.\scripts\build\upload_release.ps1 -Draft

# Пре-релиз
.\scripts\build\upload_release.ps1 -PreRelease

# Указать версию вручную
.\scripts\build\upload_release.ps1 -Version "1.0.5"
```

---

### Ручная загрузка

Если автоматический скрипт не работает, загрузите вручную:

1. **Откройте:** https://github.com/YOUR_USERNAME/YOUR_REPO/releases/new

2. **Заполните:**
   - Tag: `v1.0.5`
   - Release title: `Signer PRIME v1.0.5`
   - Description: содержимое из `release/release_notes.txt`

3. **Загрузите ВСЕ файлы** из папки `release/`:
   - `Signer.7z.001`, `Signer.7z.002`, `Signer.7z.003`, ...
   - `checksum.sha256`
   - `release_notes.txt`
   - `README.md`
   - `BUILD_AUTOUPDATE.md`

4. **Опубликуйте** релиз

---

## Проверка после публикации

1. **Откройте страницу релиза** и убедитесь, что все файлы загружены
2. **Скачайте архивы** и проверьте чексуммы:
   ```powershell
   certutil -hashfile Signer.7z.001 SHA256
   ```
   Сравните с `checksum.sha256`

3. **Распакуйте архив:**
   ```bash
   # Все части должны быть в одной папке
   7z x Signer.7z.001
   ```

4. **Запустите `Signer.exe`** и проверьте работу автообновления:
   - Откройте Settings → Check for updates
   - Должна появиться информация о новой версии

---

## Устранение проблем

### PyInstaller не найден
```bash
pip install pyinstaller
```

### 7z.exe не найден
1. Скачайте 7-Zip: https://www.7-zip.org/download.html
2. Скопируйте `7z.exe` и `7z.dll` в `installer/`

### GitHub CLI не авторизован
```bash
gh auth login
```

### Релиз уже существует
Скрипт предложит удалить существующий релиз. Или удалите вручную:
```bash
gh release delete v1.0.5 --yes
```

### Ошибка загрузки файлов
Проверьте права доступа к репозиторию и размер файлов (GitHub ограничивает до 2GB на файл).

---

## Контрольный чек-лист

- [ ] Обновлена версия в `version.json`
- [ ] **НОВОЕ (v2.0.1+):** Установлены CPU-бэкенды (`pip install onnx onnxruntime openvino openvino-dev`)
- [ ] Подготовлены release notes в `docs/release_notes.txt`
- [ ] Настроен URL лицензионного сервера в `build_config.json`
- [ ] Запущен `prepare_release.bat`
- [ ] **НОВОЕ (v2.0.1+):** Экспорт моделей прошёл успешно (шаг 3/9)
- [ ] **НОВОЕ (v2.0.1+):** Верификация CPU-бэкендов прошла успешно (шаг 6/9)
- [ ] Проверены файлы в `release/`
- [ ] Релиз опубликован на GitHub (автоматически или вручную)
- [ ] Скачаны и проверены архивы
- [ ] Протестирована распаковка
- [ ] Проверена работа автообновления
- [ ] **НОВОЕ (v2.0.1+):** Протестирована работа ONNX Runtime и OpenVINO бэкендов в Settings

---

## Дополнительная информация

### Структура проекта
- `version.json` — версия приложения
- `docs/release_notes.txt` — описание изменений
- `scripts/build/prepare_release.bat` — сборка релиза
- `scripts/build/upload_release.ps1` — загрузка на GitHub
- `scripts/export_models_onnx.py` — **НОВОЕ (v2.0.1+):** экспорт моделей в ONNX/OpenVINO
- `scripts/build/verify_cpu_backends.py` — **НОВОЕ (v2.0.1+):** верификация CPU-бэкендов
- `signer.spec`, `updater.spec` — конфигурация PyInstaller

### CPU-бэкенды (v2.0.1+)
Начиная с версии 2.0.1, приложение **обязательно** включает поддержку ONNX Runtime и OpenVINO для оптимизации производительности на CPU-only системах:

1. **Экспорт моделей** (автоматически в `prepare_release.bat`):
   ```bash
   python scripts/export_models_onnx.py --format all
   ```

2. **Верификация** (автоматически в `prepare_release.bat`):
   ```bash
   python scripts/build/verify_cpu_backends.py
   ```

3. **Ручной экспорт** (если нужно обновить модели без полной сборки):
   ```bash
   # Только ONNX
   python scripts/export_models_onnx.py --format onnx
   
   # Только OpenVINO
   python scripts/export_models_onnx.py --format openvino
   
   # Принудительный реэкспорт
   python scripts/export_models_onnx.py --format all --force
   ```

4. **Устранение проблем:**
   - Если модели не экспортируются: проверьте, что установлены `onnx`, `onnxruntime`, `openvino-dev`
   - Если верификация падает: запустите скрипт вручную для подробных логов
   - Если бэкенды откатываются на PyTorch: проверьте, что экспортированные файлы существуют

### Система автообновлений
Подробнее: [docs/BUILD_AUTOUPDATE.md](docs/BUILD_AUTOUPDATE.md)

### Архивные скрипты
Старые скрипты разработки находятся в `scripts/archive/`
