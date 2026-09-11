# 🚀 Быстрая сборка и публикация релиза

## Автоматический способ (рекомендуется)

### Шаг 1: Обновите версию

Отредактируйте `version.json`:
```json
{
  "version": "2.0.1",
  "build_date": "2026-09-11"
}
```

### Шаг 2: Обновите release notes (опционально)

Отредактируйте `release_notes.txt` или скрипт создаст его автоматически.

### Шаг 3: Запустите сборку

```cmd
build_release.bat
```

Этот скрипт автоматически:
- ✅ Проверит все зависимости (Python, PyInstaller, 7-Zip)
- ✅ Очистит старые сборки
- ✅ Соберет Signer.exe и Updater.exe
- ✅ Скопирует все необходимые файлы
- ✅ Создаст многотомный архив (100MB части)
- ✅ Вычислит SHA-256 чексуммы
- ✅ Подготовит все файлы в папке `release\`

**Результат:** папка `release\` со всеми файлами для загрузки на GitHub.

### Шаг 4: Загрузите на GitHub (два способа)

#### Способ A: Автоматически через GitHub CLI (рекомендуется)

```powershell
.\upload_release.ps1
```

Скрипт автоматически:
- Определит версию из `version.json`
- Определит репозиторий из git remote
- Создаст релиз на GitHub
- Загрузит все файлы из `release\`
- Откроет страницу релиза в браузере

**Требования:**
- Установлен [GitHub CLI](https://cli.github.com/)
- Выполнена авторизация: `gh auth login`

**Опции:**
```powershell
# Создать как черновик
.\upload_release.ps1 -Draft

# Создать как пре-релиз
.\upload_release.ps1 -PreRelease

# Указать версию вручную
.\upload_release.ps1 -Version "2.0.1"

# Указать репозиторий вручную
.\upload_release.ps1 -RepoOwner "username" -RepoName "repo-name"
```

#### Способ B: Вручную через веб-интерфейс

1. Откройте: `https://github.com/YOUR_USERNAME/YOUR_REPO/releases/new`
2. Создайте тег: `v2.0.1`
3. Перетащите **ВСЕ** файлы из папки `release\`:
   - `Signer.7z.001`, `Signer.7z.002`, ... (все части архива)
   - `checksum.sha256`
   - `release_notes.txt`
   - `README.md` (опционально)
   - `BUILD_AUTOUPDATE.md` (опционально)
4. Нажмите **Publish release**

---

## Ручной способ (для экспертов)

Если нужен полный контроль:

```cmd
# 1. Сборка основного приложения
pyinstaller signer.spec --noconfirm

# 2. Сборка Updater
pyinstaller updater.spec --noconfirm

# 3. Копирование файлов
copy dist\Updater\Updater.exe dist\Signer\Updater.exe
copy installer\7z.exe dist\Signer\7z.exe
copy installer\7z.dll dist\Signer\7z.dll

# 4. Создание архива
cd dist
..\installer\7z.exe a -v100m -mx=5 Signer.7z Signer\*

# 5. Вычисление чексумм
for %%f in (Signer.7z.*) do certutil -hashfile "%%f" SHA256 >> checksum.sha256

# 6. Загрузка на GitHub
gh release create v2.0.1 --title "Signer PRIME v2.0.1" --notes-file release_notes.txt
gh release upload v2.0.1 Signer.7z.* checksum.sha256 --clobber
```

---

## Проверка релиза

После публикации проверьте:

1. ✅ Все части архива загружены (`Signer.7z.001`, `.002`, `.003`, ...)
2. ✅ Файл `checksum.sha256` присутствует
3. ✅ Release notes отображаются корректно
4. ✅ Тег версии соответствует версии в `version.json`

---

## Устранение проблем

### GitHub CLI не найден

```cmd
winget install --id GitHub.cli
```

Или скачайте: https://cli.github.com/

### GitHub CLI не авторизован

```cmd
gh auth login
```

### 7-Zip не найден

Скопируйте `7z.exe` и `7z.dll` из `C:\Program Files\7-Zip\` в `installer\`

Или скачайте: https://www.7-zip.org/

### PyInstaller не найден

```cmd
pip install pyinstaller
```

---

## Структура файлов релиза

```
release\
├── Signer.7z.001       ← Часть 1 архива (100MB)
├── Signer.7z.002       ← Часть 2 архива (100MB)
├── Signer.7z.003       ← Часть 3 архива (остаток)
├── ...
├── checksum.sha256     ← SHA-256 чексуммы всех частей
├── release_notes.txt   ← Описание релиза
├── README.md           ← Документация (опционально)
└── BUILD_AUTOUPDATE.md ← Инструкции сборки (опционально)
```

Все эти файлы должны быть загружены на GitHub Release для работы автообновления.

---

## Дополнительно

### Изменение размера частей архива

По умолчанию: **100MB** части

Для изменения отредактируйте `build_release.bat`, строка:
```cmd
..\installer\7z.exe a -v100m -mx=5 Signer.7z Signer\*
```

Варианты:
- `-v50m` — 50MB части (для медленного интернета)
- `-v200m` — 200MB части (для быстрого интернета)

### Изменение уровня сжатия

По умолчанию: **-mx=5** (нормальное сжатие)

Варианты:
- `-mx=3` — быстрое сжатие, больше размер
- `-mx=9` — максимальное сжатие, медленнее (рекомендуется для релизов)

---

## Контрольный чеклист перед публикацией

- [ ] Версия обновлена в `version.json`
- [ ] Все тесты пройдены
- [ ] Release notes актуальны
- [ ] Собрано через `build_release.bat`
- [ ] Протестировано локально в `dist\Signer\`
- [ ] Все файлы в папке `release\`
- [ ] Релиз опубликован на GitHub
- [ ] Автообновление работает (проверка через старую версию)
