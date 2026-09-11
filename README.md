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

### Быстрая тестовая сборка

```bash
scripts\build\build_test.bat
```

Быстрая сборка без архивации для локального тестирования.

### Полная сборка релиза

```bash
scripts\build\build_release.bat
```

Автоматически:
- Собирает `Signer.exe` и `Updater.exe`
- Создает многотомный архив (100MB части)
- Вычисляет SHA-256 чексуммы
- Подготавливает файлы в папке `release\`

### Загрузка на GitHub

```powershell
.\scripts\build\upload_release.ps1
```

Автоматическая публикация релиза на GitHub (требует GitHub CLI).

📚 **Подробнее:** [docs/QUICK_RELEASE_GUIDE.md](docs/QUICK_RELEASE_GUIDE.md) | [docs/SCRIPTS_README.md](docs/SCRIPTS_README.md)

## Документация

Подробная документация по архитектуре и функциональности проекта находится в директории `docs/`.

Для быстрого доступа к документации используйте:
```bash
scripts\build\docs.bat
```

## Структура проекта

### Основные файлы
- `main.py` — точка входа в приложение
- `version.json` — версия приложения
- `signer.spec`, `updater.spec` — конфигурация PyInstaller

### Пакеты
- `app/` — утилиты и версионирование
- `updater/` — система автообновлений
- `core/` — ядро системы: детекторы, обработчики знаков, GPS
- `configs/` — конфигурация моделей и настройки
- `processing/` — потоки обработки видео, OCR, детекция
- `server/` — Flask-сервер для карты
- `ui/` — графический интерфейс (PyQt6)
- `templates/` — HTML-шаблоны для карты
- `scripts/` — утилиты для экспорта моделей, бенчмарки, сборки
  - `scripts/build/` — скрипты сборки и релиза
  - `scripts/dev/` — скрипты для разработки
- `tests/` — тесты
- `docs/` — документация
- `docs/` — документация
