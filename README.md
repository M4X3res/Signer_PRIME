# RoadScanner (Signer PRIME)

Система автоматической детекции и геопривязки дорожных знаков по видео с GPS-треком.

## Установка зависимостей

```bash
pip install -r requirements.txt
```

## Запуск

```bash
python main.py
```

## Сборка и релиз

### Подготовка релиза

```bash
scripts\build\prepare_release.bat
```

Автоматически:
- Собирает `Signer.exe` и `Updater.exe`
- Создаёт многотомный архив (100MB части)
- Вычисляет SHA-256 чексуммы
- Подготавливает файлы в папке `release\`

### Загрузка на GitHub

```powershell
.\scripts\build\upload_release.ps1
```

Автоматическая публикация релиза на GitHub (требует GitHub CLI).

📚 **Подробнее:** [docs/RELEASE.md](docs/RELEASE.md)

## Документация

Подробная документация находится в директории `docs/`.

### Система лицензирования

Приложение использует систему подписок (месяц / 3 месяца / год).

- **Быстрый старт:** [docs/QUICKSTART_LICENSING.md](docs/QUICKSTART_LICENSING.md)
- **Документация клиента:** [docs/LICENSING.md](docs/LICENSING.md)
- **Документация сервера:** [docs/LICENSE_SERVER.md](docs/LICENSE_SERVER.md)

Для разработки без продакшн-сервера запустите локальный dev-сервер из `signer-license-server/` и установите `SIGNER_LICENSE_SERVER_URL=http://localhost:8000`.

## Структура проекта

### Основные файлы
- `main.py` — точка входа в приложение
- `version.json` — версия приложения
- `signer.spec`, `updater.spec` — конфигурация PyInstaller  
- `build_config.json` — production конфигурация (URL лицензионного сервера)

### Пакеты
- `app/` — утилиты и версионирование
- `updater/` — система автообновлений
- `licensing/` — система лицензирования по подписке (обфусцируется PyArmor перед релизом)
- `core/` — ядро системы: детекторы, обработчики знаков, GPS
- `configs/` — конфигурация моделей и настройки
- `processing/` — потоки обработки видео, OCR, детекция
- `server/` — Flask-сервер для карты
- `ui/` — графический интерфейс (PyQt6)
- `templates/` — HTML-шаблоны для карты

### Скрипты и тесты
- `scripts/build/` — скрипты сборки и релиза:
  - `prepare_release.bat` — главный скрипт подготовки релиза
  - `obfuscate_licensing.py` — обфускация через PyArmor (пишет в `build/obfuscated/`)
  - `restore_originals.py` — восстановление исходников после обфускации
  - `upload_release.ps1` — публикация релиза на GitHub
- `scripts/dev/` — dev-утилиты и git-хелперы
- `scripts/archive/` — архив старых скриптов
- `tests/` — unit/integration тесты
- `docs/` — документация
- `docs/archive/` — архивные отчёты AI-сессий

### Ресурсы и модели
- `assets/` — иконки, изображения
- `installer/` — конфигурация Inno Setup + 7z.exe/7z.dll
- `CNN_side/`, `lane_guidance_models/`, `small_models/` — ML-модели (не в git)
- `sings/`, `sings_text/` — датасеты знаков
- `templates/` — HTML-шаблоны для карты

### Сторонние проекты
- `signer-license-server/` — backend лицензионного сервера (отдельный поддиректорий, не трогать при клиентской разработке)
