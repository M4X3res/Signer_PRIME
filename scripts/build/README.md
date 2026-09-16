# Скрипты сборки и релиза

## 📦 Подготовка релиза

```bash
prepare_release.bat
```

**Что делает (7 шагов):**
1. Проверка конфигурации `build_config.json`
2. Проверка зависимостей (Python, PyInstaller, 7z)
3. Очистка старых сборок
4. **Обфускация лицензирования** (PyArmor, опционально)
5. Сборка Signer.exe и Updater.exe
6. Создание многотомного архива (части по 100MB)
7. Вычисление SHA-256 чексумм

**Результат:** папка `release/` с готовым релизом

---

## 🚀 Загрузка на GitHub

```powershell
.\upload_release.ps1
```

**Требования:**
- GitHub CLI: `winget install --id GitHub.cli`
- Авторизация: `gh auth login`

**Опции:**
```powershell
.\upload_release.ps1 -Draft        # Черновик
.\upload_release.ps1 -PreRelease   # Пре-релиз
.\upload_release.ps1 -Version "1.0.5"  # Указать версию
```

---

## 🛠️ Вспомогательные скрипты

- `obfuscate_licensing.py` — обфускация модулей (вызывается автоматически)
- `restore_originals.py` — восстановление файлов после обфускации

---

## 📋 Быстрый старт

1. **Настройте конфигурацию:**
   ```bash
   copy build_config.json.example build_config.json
   notepad build_config.json  # Укажите URL сервера
   ```

2. **Соберите релиз:**
   ```bash
   scripts\build\prepare_release.bat
   ```

3. **Загрузите на GitHub:**
   ```powershell
   .\scripts\build\upload_release.ps1
   ```

---

## 📖 Документация

- **Полная инструкция:** `../../docs/RELEASE.md`
- **Быстрый гайд:** `QUICK_BUILD_GUIDE.md`
- **Система обновлений:** `../../docs/BUILD_AUTOUPDATE.md`
