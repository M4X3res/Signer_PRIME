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

📚 **Подробнее:** [RELEASE.md](RELEASE.md)

## Документация

Подробная документация находится в директории `docs/`.

### Система лицензирования

Приложение использует систему подписок (месяц / 3 месяца / год).

- **Быстрый старт:** [QUICKSTART_LICENSING.md](QUICKSTART_LICENSING.md)
- **Документация клиента:** [docs/LICENSING.md](docs/LICENSING.md)
- **Документация сервера:** [docs/LICENSE_SERVER.md](docs/LICENSE_SERVER.md)

Для разработки без сервера установите `LICENSE_MOCK_MODE = True` в `licensing/license_client.py`.

## Структура проекта

### Основные файлы
- `main.py` — точка входа в приложение
- `version.json` — версия приложения
- `signer.spec`, `updater.spec` — конфигурация PyInstaller

### Пакеты
- `app/` — утилиты и версионирование
- `updater/` — система автообновлений
- `licensing/` — система лицензирования по подписке
- `core/` — ядро системы: детекторы, обработчики знаков, GPS
- `configs/` — конфигурация моделей и настройки
- `processing/` — потоки обработки видео, OCR, детекция
- `server/` — Flask-сервер для карты
- `ui/` — графический интерфейс (PyQt6)
- `templates/` — HTML-шаблоны для карты
- `scripts/build/` — скрипты сборки и релиза
- `scripts/archive/` — архив старых скриптов разработки
- `tests/` — тесты
- `docs/` — документация
