# Процесс релиза Signer PRIME

## Подготовка релиза

### 1. Обновите версию

Отредактируйте `version.json`:
```json
{
  "version": "1.0.5"
}
```

### 2. Подготовьте release notes

Создайте/обновите `docs/release_notes.txt`:
```
Signer PRIME v1.0.5

Новые возможности:
- Добавлена функция X
- Улучшена производительность Y

Исправления:
- Исправлена ошибка Z

Системные требования:
- Windows 10/11 (64-bit)
- 8+ GB RAM
- 5+ GB свободного места на диске
```

### 3. Запустите сборку

```bash
scripts\build\prepare_release.bat
```

**Скрипт автоматически:**
- Проверит зависимости (Python, PyInstaller, 7z)
- Очистит старые сборки
- Соберёт `Signer.exe` и `Updater.exe`
- Создаст многотомный архив (части по 100MB)
- Вычислит SHA-256 чексуммы
- Подготовит файлы в папке `release/`

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

### 4. Проверьте сборку

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
- [ ] Подготовлены release notes в `docs/release_notes.txt`
- [ ] Запущен `prepare_release.bat`
- [ ] Проверены файлы в `release/`
- [ ] Релиз опубликован на GitHub (автоматически или вручную)
- [ ] Скачаны и проверены архивы
- [ ] Протестирована распаковка
- [ ] Проверена работа автообновления

---

## Дополнительная информация

### Структура проекта
- `version.json` — версия приложения
- `docs/release_notes.txt` — описание изменений
- `scripts/build/prepare_release.bat` — сборка релиза
- `scripts/build/upload_release.ps1` — загрузка на GitHub
- `signer.spec`, `updater.spec` — конфигурация PyInstaller

### Система автообновлений
Подробнее: [docs/BUILD_AUTOUPDATE.md](docs/BUILD_AUTOUPDATE.md)

### Архивные скрипты
Старые скрипты разработки находятся в `scripts/archive/`
