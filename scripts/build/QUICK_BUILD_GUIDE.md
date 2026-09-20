# Быстрая инструкция: Сборка релиза

## Предварительные требования

1. **Python venv активирован:**
   ```bash
   .venv\Scripts\activate
   ```

2. **Установлены зависимости:**
   ```bash
   pip install -r requirements.txt
   pip install pyinstaller
   pip install pyarmor  # Опционально
   ```

3. **Настроен build_config.json:**
   ```bash
   copy build_config.json.example build_config.json
   notepad build_config.json  # Укажите реальный URL
   ```

4. **Модели на месте:**
   - `sings/` — модели детекции
   - `sings_text/` — модели OCR

## Сборка

```bash
scripts\build\prepare_release.bat
```

Скрипт выполнит:
1. Проверку конфигурации
2. Проверку зависимостей
3. Обфускацию (если PyArmor установлен)
4. Сборку Signer.exe и Updater.exe
5. Создание многотомного архива
6. Вычисление чексумм
7. Подготовку файлов в `release/`

## Результат

```
release/
├── Signer.7z.001
├── Signer.7z.002
├── ...
├── checksum.sha256
├── README.md
└── release_notes.txt
```

## Загрузка на GitHub

```powershell
.\scripts\build\upload_release.ps1
```

## Проблемы?

**Ошибка "obfuscate_licensing.py not found":**
- ✅ Исправлено! Файл создан.

**Ошибка "PyArmor not found":**
- Скрипт автоматически соберёт без обфускации
- Установите: `pip install pyarmor`

**Ошибка "PyInstaller not found":**
- Установите: `.venv\Scripts\pip.exe install pyinstaller`

**Ошибка "build_config.json not found":**
- Скопируйте: `copy build_config.json.example build_config.json`
- Отредактируйте URL сервера

## См. также

- Полная документация: `docs/RELEASE.md`
- Система обновлений: `docs/BUILD_AUTOUPDATE.md`
