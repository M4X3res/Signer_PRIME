# 🚀 Быстрое руководство по релизу

## Два простых скрипта

### 1️⃣ Подготовка релиза

```cmd
scripts\build\prepare_release.bat
```

**Что делает:**
- ✅ Проверяет зависимости (Python, PyInstaller, 7-Zip)
- ✅ Очищает старые сборки
- ✅ Собирает Signer.exe и Updater.exe
- ✅ Создаёт многотомный архив (100MB части)
- ✅ Вычисляет SHA-256 чексуммы
- ✅ Готовит все файлы в папке `release\`

**Результат:** папка `release\` со всеми файлами для GitHub Release

---

### 2️⃣ Загрузка на GitHub (опционально)

```powershell
.\scripts\build\upload_release.ps1
```

**Что делает:**
- ✅ Создаёт GitHub Release
- ✅ Загружает все файлы из `release\`
- ✅ Открывает страницу релиза

**Требования:** [GitHub CLI](https://cli.github.com/) + авторизация (`gh auth login`)

---

## Быстрый workflow

### Перед релизом

1. **Обновите версию** в `version.json`:
   ```json
   {
     "version": "2.0.1",
     "build_date": "2026-09-11"
   }
   ```

2. **Обновите release notes** в `docs\release_notes.txt`:
   ```
   Signer PRIME v2.0.1
   
   Изменения:
   - Исправлен баг X
   - Добавлена функция Y
   ```

### Создание релиза

```cmd
# 1. Подготовка
scripts\build\prepare_release.bat

# 2. Проверьте файлы в release\

# 3. Загрузите на GitHub (автоматически)
powershell -ExecutionPolicy Bypass -File scripts\build\upload_release.ps1

# Или вручную:
# - Откройте https://github.com/YOUR_REPO/releases/new
# - Тег: v2.0.1
# - Загрузите ВСЕ файлы из release\
```

---

## Требования

### Первоначальная настройка

1. **Python + PyInstaller:**
   ```cmd
   pip install -r requirements.txt
   pip install pyinstaller
   ```

2. **7-Zip:**
   ```cmd
   # Скопируйте 7z.exe и 7z.dll в installer\
   copy "C:\Program Files\7-Zip\7z.*" installer\
   ```
   Или скачайте: https://www.7-zip.org/

3. **GitHub CLI** (только для автозагрузки):
   ```cmd
   winget install --id GitHub.cli
   gh auth login
   ```

---

## Структура release\

После выполнения `prepare_release.bat`:

```
release\
├── Signer.7z.001           ← Часть 1 (100MB)
├── Signer.7z.002           ← Часть 2 (100MB)
├── Signer.7z.003           ← Часть 3 (остаток)
├── ...
├── checksum.sha256         ← SHA-256 всех частей
├── release_notes.txt       ← Описание релиза
├── README.md               ← Документация
└── BUILD_AUTOUPDATE.md     ← Инструкции автообновления
```

**Все эти файлы** нужно загрузить на GitHub Release.

---

## Опции upload_release.ps1

```powershell
# Создать как черновик
.\scripts\build\upload_release.ps1 -Draft

# Создать как пре-релиз
.\scripts\build\upload_release.ps1 -PreRelease

# Указать версию вручную
.\scripts\build\upload_release.ps1 -Version "2.0.1"
```

---

## Checklist

Перед запуском `prepare_release.bat`:
- [ ] Версия обновлена в `version.json`
- [ ] Release notes актуализированы
- [ ] Все изменения закоммичены
- [ ] Код протестирован

После `prepare_release.bat`:
- [ ] Проверены файлы в `release\`
- [ ] Релиз загружен на GitHub (вручную или через скрипт)
- [ ] Автообновление протестировано

---

## Устранение проблем

### PyInstaller не найден
```cmd
pip install pyinstaller
```

### 7-Zip не найден
```cmd
copy "C:\Program Files\7-Zip\7z.*" installer\
```

### GitHub CLI не авторизован
```cmd
gh auth login
```

### Очистка перед повторной сборкой
```cmd
rmdir /s /q build dist release
scripts\build\prepare_release.bat
```

---

## Дополнительно

Полная документация: [docs/](../docs/)
