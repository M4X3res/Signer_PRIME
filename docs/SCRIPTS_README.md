# 📦 Скрипты сборки Signer PRIME

Автоматизация сборки, архивирования и публикации релизов.

---

## 🎯 Доступные скрипты

### 1. `build_test.bat` — Быстрая тестовая сборка ⚡

**Для:** локальное тестирование изменений

**Что делает:**
- Собирает `Signer.exe` и `Updater.exe`
- Копирует необходимые файлы
- **НЕ создает архивы** (быстрее)
- Автоматически запускает приложение

**Использование:**
```cmd
build_test.bat
```

**Результат:** `dist\Signer\Signer.exe` готов к запуску

---

### 2. `build_release.bat` — Полная сборка релиза 📦

**Для:** подготовка файлов для публикации на GitHub

**Что делает:**
- ✅ Проверяет все зависимости (Python, PyInstaller, 7-Zip)
- ✅ Очищает старые сборки
- ✅ Собирает `Signer.exe` и `Updater.exe`
- ✅ Копирует все необходимые файлы
- ✅ Создает многотомный архив `Signer.7z.001`, `.002`, ...
- ✅ Вычисляет SHA-256 чексуммы
- ✅ Подготавливает файлы в папке `release\`

**Использование:**
```cmd
build_release.bat
```

**Результат:** папка `release\` со всеми файлами для GitHub Release

**Требования:**
- Python с установленным PyInstaller
- 7-Zip (`7z.exe` и `7z.dll` в `installer\`)

---

### 3. `upload_release.ps1` — Загрузка на GitHub 🚀

**Для:** автоматическая публикация релиза на GitHub

**Что делает:**
- Создает GitHub Release
- Загружает все файлы из `release\`
- Применяет release notes
- Открывает страницу релиза в браузере

**Использование:**

Базовый:
```powershell
.\upload_release.ps1
```

С параметрами:
```powershell
# Создать как черновик
.\upload_release.ps1 -Draft

# Создать как пре-релиз
.\upload_release.ps1 -PreRelease

# Указать версию вручную
.\upload_release.ps1 -Version "2.0.1"

# Указать репозиторий вручную
.\upload_release.ps1 -RepoOwner "username" -RepoName "repo-name"

# Все вместе
.\upload_release.ps1 -Version "2.0.1" -Draft -RepoOwner "myuser" -RepoName "myrepo"
```

**Требования:**
- [GitHub CLI](https://cli.github.com/) установлен и авторизован
- Файлы подготовлены в `release\` (запустите `build_release.bat`)

**Настройка GitHub CLI:**
```cmd
# Установка
winget install --id GitHub.cli

# Авторизация
gh auth login
```

---

## 🚀 Типичный workflow

### Разработка и тестирование

```cmd
# 1. Внесите изменения в код
# 2. Быстрая сборка и тест
build_test.bat
```

### Публикация релиза

```cmd
# 1. Обновите версию в version.json
notepad version.json

# 2. Обновите release notes
notepad release_notes.txt

# 3. Полная сборка релиза
build_release.bat

# 4. Загрузите на GitHub
powershell -ExecutionPolicy Bypass -File upload_release.ps1
```

---

## 📋 Checklist перед релизом

Перед запуском `build_release.bat`:

- [ ] Версия обновлена в `version.json`
- [ ] Release notes актуализированы в `release_notes.txt`
- [ ] Все изменения закоммичены в git
- [ ] Код протестирован через `build_test.bat`
- [ ] Python окружение активировано

Перед запуском `upload_release.ps1`:

- [ ] GitHub CLI установлен и авторизован
- [ ] Папка `release\` содержит все файлы
- [ ] Проверены чексуммы в `checksum.sha256`

---

## 🛠️ Настройка окружения

### Первоначальная настройка

1. **Установите Python зависимости:**
   ```cmd
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **Установите 7-Zip:**
   - Скачайте: https://www.7-zip.org/
   - Скопируйте `7z.exe` и `7z.dll` в `installer\`

3. **Установите GitHub CLI (для `upload_release.ps1`):**
   ```cmd
   winget install --id GitHub.cli
   gh auth login
   ```

### Проверка готовности

```cmd
# Python
python --version

# PyInstaller
python -c "import PyInstaller"

# 7-Zip
dir installer\7z.*

# GitHub CLI (опционально)
gh --version
```

---

## 📝 Структура файлов

### После `build_test.bat`:
```
dist\Signer\
├── Signer.exe
├── Updater.exe
├── 7z.exe
├── 7z.dll
├── version.json
└── _internal\
    └── (зависимости PyInstaller)
```

### После `build_release.bat`:
```
release\
├── Signer.7z.001           ← Часть 1 архива (100MB)
├── Signer.7z.002           ← Часть 2 архива (100MB)
├── Signer.7z.003           ← Часть 3 архива
├── ...
├── checksum.sha256         ← SHA-256 всех частей
├── release_notes.txt       ← Описание релиза
├── README.md               ← Документация
└── BUILD_AUTOUPDATE.md     ← Инструкции
```

---

## ⚙️ Настройка параметров сборки

### Изменение размера частей архива

Отредактируйте `build_release.bat`, строка:
```cmd
..\installer\7z.exe a -v100m -mx=5 Signer.7z Signer\*
```

**Параметр `-v`:** размер части
- `-v50m` — 50MB (для медленного интернета)
- `-v100m` — 100MB (по умолчанию)
- `-v200m` — 200MB (для быстрого интернета)

### Изменение уровня сжатия

**Параметр `-mx`:** уровень сжатия
- `-mx=3` — быстрое сжатие, больше размер
- `-mx=5` — нормальное (по умолчанию)
- `-mx=9` — максимальное, медленнее (для релизов)

---

## 🐛 Устранение проблем

### `pyinstaller: command not found`
```cmd
pip install pyinstaller
```

### `7z.exe не найден`
Скопируйте из установки 7-Zip:
```cmd
copy "C:\Program Files\7-Zip\7z.exe" installer\
copy "C:\Program Files\7-Zip\7z.dll" installer\
```

### `gh: command not found`
```cmd
winget install --id GitHub.cli
```

### `GitHub CLI не авторизован`
```cmd
gh auth login
```

### Ошибка сборки PyInstaller

1. Очистите кеш:
   ```cmd
   rmdir /s /q build
   rmdir /s /q dist
   ```

2. Проверьте spec-файлы:
   - `signer.spec`
   - `updater.spec`

3. Проверьте зависимости:
   ```cmd
   pip install -r requirements.txt --upgrade
   ```

---

## 📖 Дополнительная документация

- `QUICK_RELEASE_GUIDE.md` — Краткое руководство
- `BUILD_AUTOUPDATE.md` — Детальная инструкция по сборке
- `BUILD_INSTRUCTIONS.md` — Общие инструкции по сборке

---

## 🔄 Автоматизация через CI/CD

Скрипты можно интегрировать в GitHub Actions:

```yaml
name: Release Build

on:
  push:
    tags:
      - 'v*'

jobs:
  build:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: |
          pip install -r requirements.txt
          pip install pyinstaller
      - name: Build release
        run: .\build_release.bat
      - name: Upload to GitHub Release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: .\upload_release.ps1
```

---

## 💡 Советы

1. **Перед каждым релизом:** запустите `build_test.bat` для проверки
2. **Версионирование:** используйте семантическое версионирование (2.0.0, 2.1.0, 2.1.1)
3. **Release notes:** пишите понятные описания изменений для пользователей
4. **Тестирование:** проверяйте автообновление со старой версии на новую
5. **Бэкапы:** сохраняйте предыдущие релизы на случай отката

---

## 📞 Поддержка

Если возникли проблемы:
1. Проверьте все зависимости через чеклист выше
2. Посмотрите логи ошибок
3. Очистите кеш: `rmdir /s /q build dist`
4. Попробуйте пересобрать с нуля
