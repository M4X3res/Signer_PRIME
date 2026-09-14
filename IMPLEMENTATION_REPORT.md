# Отчёт о выполнении: 3 доработки Signer PRIME

Дата: 2026-09-14
Выполнено: 3 независимые задачи по расширению функциональности

---

## Задача 1: Управление лицензией в настройках ✅

### Что сделано:

#### 1.1. Общая константа для названий планов
- **Файл**: `licensing/license_manager.py`
  - Добавлена константа `PLAN_DISPLAY_NAMES` с русскими названиями планов подписки
  - Константа экспортируется для использования в UI-компонентах

#### 1.2. Обновление LicenseDialog
- **Файл**: `ui/widgets/license_dialog.py`
  - Импортируется `PLAN_DISPLAY_NAMES` из `license_manager`
  - Удалён дублирующийся локальный словарь `plan_names`
  - Использует общую константу вместо дублирования

#### 1.3. Блок управления лицензией в настройках
- **Файл**: `ui/widgets/settings_page.py`
  - Добавлен импорт `LicenseManager`, `LicenseStatus`, `PLAN_DISPLAY_NAMES`
  - Конструктор принимает опциональный параметр `license_manager`
  - Добавлена группа "Лицензия" **сразу после переключателя режимов**, ДО группы "Интерфейс"
  - Группа **НЕ включена** в `_advanced_only_widgets` — видна всегда
  
  **Содержимое блока:**
  - **Статус лицензии**: цветной текст (зелёный/жёлтый/красный/серый) в зависимости от статуса
  - **Детали лицензии**: план, дата окончания, ключ (для активных лицензий)
  - **Кнопка "Управление лицензией"**: открывает существующий `LicenseDialog`
  - **Кнопка "🔄 Обновить статус"**: синхронная проверка + асинхронный refresh с сервера
  
  **Методы:**
  - `_update_license_display()`: обновляет UI на основе текущего статуса
  - `_open_license_dialog()`: открывает диалог лицензии, после закрытия обновляет UI
  - `_refresh_license_status()`: обновляет статус локально и с сервера, показывает результат

#### 1.4. Передача license_manager через MainWindow
- **Файл**: `main.py`
  - После создания `license_manager` в `main()`, передаётся в `window.license_manager`

- **Файл**: `ui/main_window.py`
  - Добавлен `@property` и `@setter` для `license_manager`
  - Setter автоматически передаёт менеджер в `SettingsPage._license_manager`
  - После установки вызывает `_update_license_display()` для обновления UI

#### 1.5. Regression-тест
- **Файл**: `tests/check_license_settings.py`
  - Проверяет наличие константы `PLAN_DISPLAY_NAMES`
  - Проверяет использование константы в `license_dialog.py`
  - Проверяет наличие блока лицензии в настройках
  - Проверяет что блок НЕ в `_advanced_only_widgets`
  - Проверяет property в `MainWindow`

---

## Задача 2: Кэш видео-клипов в отдельной папке ✅

### Что сделано:

#### 2.1. Константа и хелперы для кэша
- **Файл**: `server/map_server.py`
  - Константа `CLIP_CACHE_DIRNAME = ".signer_clip_cache"`
  - Функция `_get_clip_cache_dir(video_path)`: возвращает путь к подпапке кэша, создаёт если нет
  - Функция `clear_clip_cache(video_dir)`: безопасно удаляет кэш, возвращает `(files_removed, bytes_freed)`

#### 2.2. Обновление api_video_clip
- **Файл**: `server/map_server.py`
  - Изменён путь кэша: вместо `os.path.join(video_dir, cache_filename)` теперь `os.path.join(cache_dir, cache_filename)`
  - Используется `cache_dir = _get_clip_cache_dir(video_path)`
  - Старый паттерн (кэш прямо в папке с видео) полностью удалён

#### 2.3. Роут для очистки кэша
- **Файл**: `server/map_server.py`
  - Добавлен `@app.route("/api/clear_clip_cache", methods=["POST"])`
  - Возвращает JSON: `{"ok": true, "files_removed": N, "bytes_freed": N, "mb_freed": N}`
  - Проверяет наличие `PATH_TO_VIDEO`, вызывает `clear_clip_cache(video_dir)`

#### 2.4. UI-кнопка очистки кэша
- **Файл**: `templates/map.html`
  - Добавлена кнопка "🗑 Очистить кэш" в `#topbar`, перед кнопкой "↓ GeoJSON"
  - JavaScript-функция `clearClipCache()`:
    - Делает `POST` запрос к `/api/clear_clip_cache`
    - Показывает toast с результатом ("Очищено: X файлов (Y МБ)" или "Кэш уже пуст")
    - Обрабатывает ошибки

#### 2.5. Regression-тест
- **Файл**: `tests/check_clip_cache.py`
  - Проверяет наличие `CLIP_CACHE_DIRNAME`
  - Проверяет функции `_get_clip_cache_dir` и `clear_clip_cache`
  - Проверяет что `api_video_clip` использует подпапку (не старый паттерн)
  - Проверяет роут `/api/clear_clip_cache`
  - Проверяет кнопку и функцию в `map.html`

---

## Задача 3: Ручное добавление знака на карте ✅

### Что сделано:

#### 3.1. Исправление серверной части (api_sign_create)
- **Файл**: `server/map_server.py`
  - **Добавлено поле `is_left`** (bool, default=False) в теле запроса
  - **Валидация координат**: lat ∈ [-90, 90], lon ∈ [-180, 180]
  - **Исправлено поле `left`**: теперь `str(is_left)` → `"True"`/`"False"` (консистентно с `final_handler.py`)
  - **Добавлено отдельное поле `manually_added: True`** (флаг происхождения знака)
  - **Удалён старый вариант**: `"left": "manually_added"` (ломал фильтр лево/право)

#### 3.2. UI: кнопка "Добавить знак"
- **Файл**: `templates/map.html`
  - Добавлена кнопка "＋ Добавить знак" в `#topbar`
  - Вызывает `togglePlacementMode()` при клике

#### 3.3. Режим размещения знака
- **Файл**: `templates/map.html`
  - Переменная `let placementMode = false`
  - Функция `togglePlacementMode()`:
    - Включает/выключает режим размещения
    - Меняет курсор на `crosshair`
    - Меняет текст кнопки на "✕ Отменить размещение"
    - Добавляет класс `accent` к кнопке
    - Регистрирует обработчик `map.once('click', onMapClickForPlacement)`
    - Добавляет обработчик `Escape` для отмены
  
  - Функция `onMapClickForPlacement(e)`:
    - Отключает режим размещения
    - Получает координаты клика `(lat, lon)`
    - Вызывает `openCreateSignPanel(lat, lon)`

#### 3.4. Панель создания знака
- **Файл**: `templates/map.html`
  - Функция `createCreateSignPanel()`: создаёт HTML-панель с полями:
    - **Тип знака**: `<select>` со всеми типами из `/api/sign_types`
    - **Текст/Описание**: показывается только для знаков с текстом (динамически)
    - **Сторона дороги**: два радио "Слева"/"Справа" (default: Справа)
    - **Азимут**: числовой инпут 0-360°
    - **Широта/Долгота**: readonly поля с координатами клика
    - **Кнопки**: "Отмена" и "Сохранить знак"
  
  - Функция `openCreateSignPanel(lat, lon)`:
    - Создаёт панель если её нет
    - Заполняет координаты
    - Показывает панель
  
  - Функция `onCreateTypeChange()`:
    - Показывает поле "Текст/Описание" только для знаков с текстом
  
  - Функция `saveNewSign()`:
    - Валидирует что тип выбран
    - Делает `POST /api/sign` с телом: `{type, lat, lon, azimuth, description, is_left}`
    - При успехе: `loadSigns()` → `renderMarkers()` → `selectSign(result.id)`
    - Показывает toast с результатом

#### 3.5. Обратная совместимость
- **Примечание**: вручную добавленные знаки **не переживут** повторный запуск обработки того же проекта
  - `FinalHandler.save_result()` перезаписывает GeoJSON целиком новым `FeatureCollection`
  - Это задокументировано в промпте как известная особенность
  - UI предупреждение не добавлено (опционально по промпту)

#### 3.6. Regression-тест
- **Файл**: `tests/check_manual_sign_add.py`
  - Проверяет обработку `is_left` в `api_sign_create`
  - Проверяет что `left` формируется через `str(bool)`, а не `"manually_added"`
  - Проверяет наличие кнопки "Добавить знак"
  - Проверяет логику `placementMode` (курсор crosshair, обработчик клика, Escape)
  - Проверяет панель создания знака (функции, поля, POST запрос)
  - Проверяет совместимость формата данных с `final_handler`

---

## Изменённые/созданные файлы

### Изменено:
1. `licensing/license_manager.py` — добавлена константа `PLAN_DISPLAY_NAMES`
2. `ui/widgets/license_dialog.py` — использует импортированную константу
3. `ui/widgets/settings_page.py` — добавлен блок управления лицензией
4. `main.py` — передача `license_manager` в `MainWindow`
5. `ui/main_window.py` — property для передачи `license_manager` в `SettingsPage`
6. `server/map_server.py` — кэш клипов в подпапке, очистка кэша, исправление `api_sign_create`
7. `templates/map.html` — кнопка очистки кэша, режим размещения знака, панель создания

### Создано:
1. `tests/check_license_settings.py` — тест для Задачи 1
2. `tests/check_clip_cache.py` — тест для Задачи 2
3. `tests/check_manual_sign_add.py` — тест для Задачи 3

---

## Соответствие требованиям промпта

### Критические ограничения (п. 0):
- ✅ НЕ тронута логика обработки видео в `core/` и `processing/`
- ✅ НЕ сломаны существующие HTTP-эндпоинты
- ✅ Сохранена консистентность полей GeoJSON `properties`
- ✅ Поле `"left"` хранится как строка `"True"`/`"False"` (консистентно с `final_handler.py`)
- ✅ Все пользовательские тексты на русском
- ✅ После каждой задачи созданы regression-тесты

### Задача 1:
- ✅ Группа "Лицензия" добавлена **после переключателя режимов**, ДО группы "Интерфейс"
- ✅ Группа **НЕ в** `_advanced_only_widgets` — видна всегда
- ✅ Статус лицензии с цветной индикацией
- ✅ План, дата окончания, ключ (для активных лицензий)
- ✅ Кнопка "Управление лицензией" — открывает `LicenseDialog`
- ✅ Кнопка "Обновить статус" — локально + асинхронно с сервера
- ✅ `PLAN_DISPLAY_NAMES` вынесена в общее место (не дублируется)
- ✅ `license_manager` переиспользуется из `main.py` → `MainWindow` → `SettingsPage`

### Задача 2:
- ✅ Константа `CLIP_CACHE_DIRNAME = ".signer_clip_cache"`
- ✅ Функция `_get_clip_cache_dir()` с `os.makedirs(..., exist_ok=True)`
- ✅ Функция `clear_clip_cache()` с безопасной проверкой имени папки
- ✅ `api_video_clip` использует подпапку для кэша
- ✅ Старый паттерн (кэш в `video_dir`) удалён
- ✅ Роут `POST /api/clear_clip_cache` возвращает `(files_removed, bytes_freed)`
- ✅ Кнопка "🗑 Очистить кэш" в `templates/map.html` в topbar
- ✅ JavaScript функция `clearClipCache()` с fetch и toast

### Задача 3:
- ✅ `api_sign_create` принимает `is_left` (bool)
- ✅ Поле `"left"` формируется через `str(is_left)` → `"True"`/`"False"`
- ✅ Отдельное поле `"manually_added": True`
- ✅ Валидация координат (lat ∈ [-90, 90], lon ∈ [-180, 180])
- ✅ Кнопка "＋ Добавить знак" в topbar
- ✅ Режим размещения: курсор crosshair, клик по карте, Escape для отмены
- ✅ Панель создания знака: тип, сторона, азимут, координаты, описание
- ✅ POST к `/api/sign` с `is_left`
- ✅ После создания: `loadSigns()` → `renderMarkers()` → `selectSign()`
- ✅ Формат данных совместим с `final_handler.py` и фильтром лево/право

---

## Итог

✅ Все 3 задачи выполнены на 100%
✅ Созданы regression-тесты для каждой задачи
✅ Сохранена консистентность с существующей архитектурой
✅ Код следует паттернам проекта (русские комментарии, стиль, theme_manager)
✅ Не затронута логика обработки видео и детекции
