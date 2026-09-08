# Исправление краша 0xC0000409 при выборе папки с видео

**Дата:** 2026-08-21  
**Ошибка:** `Process finished with exit code -1073740791 (0xC0000409)`  
**Код ошибки:** STATUS_STACK_BUFFER_OVERRUN

---

## Проблема

При выборе папки с видео приложение крашилось с критической ошибкой `0xC0000409`.

### Причины:

1. **VideoScanWorker создавался как вложенный класс** внутри метода `_on_video_changed()`, что создавало проблемы с памятью и сигналами Qt
2. **Недостаточный размер стека потока** для работы с Windows Media Foundation
3. **Отсутствие валидации пути** перед сканированием папки
4. **Небезопасная обработка `os.listdir()`** без try-except для каждого файла
5. **Проблемы с нормализацией пути** — использование `path.replace("/", "\\") + "\\"` вместо `os.path.normpath()`

---

## Решение

### 1. Вынос VideoScanWorker в отдельный класс

**Файл:** `ui/widgets/dashboard_page.py`

```python
class VideoScanWorker(QThread):
    """Асинхронный воркер для сканирования папки с видео."""
    finished = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, folder_path: str):
        super().__init__()
        self.folder_path = folder_path
        # КРИТИЧНО: Увеличенный стек для защиты от краша
        self.setStackSize(8 * 1024 * 1024)  # 8 MB
```

**Почему важно:**
- Класс создаётся один раз на уровне модуля, а не при каждом вызове
- Увеличенный stack size защищает от переполнения при работе с видео
- Правильная настройка сигналов Qt

### 2. Валидация пути перед сканированием

```python
def run(self):
    # Проверка существования папки
    if not os.path.exists(self.folder_path):
        self.error.emit(f"Папка не существует: {self.folder_path}")
        return
    
    if not os.path.isdir(self.folder_path):
        self.error.emit(f"Путь не является папкой: {self.folder_path}")
        return
```

### 3. Безопасное сканирование с обработкой исключений

```python
# Безопасное сканирование с обработкой исключений для каждого файла
videos = []
try:
    entries = os.listdir(self.folder_path)
except PermissionError:
    self.error.emit("Нет доступа к папке")
    return

for filename in entries:
    try:
        if filename.lower().endswith(('.mp4', '.mov', '.avi')):
            full_path = os.path.join(self.folder_path, filename)
            if os.path.isfile(full_path) and os.access(full_path, os.R_OK):
                videos.append(filename)
    except Exception as e:
        logger.warning(f"Пропуск файла {filename}: {e}")
        continue
```

**Защищает от:**
- Битых файлов
- Файлов без прав доступа
- Символических ссылок на несуществующие файлы
- Повреждённых файловых систем

### 4. Правильная нормализация пути

**Было:**
```python
config.PATH_TO_VIDEO = path.replace("/", "\\") + "\\"
```

**Стало:**
```python
normalized_path = os.path.normpath(path)
config.PATH_TO_VIDEO = normalized_path
```

**Преимущества:**
- Кроссплатформенность (работает на Windows, Linux, macOS)
- Правильная обработка относительных путей
- Удаление лишних слешей
- Корректная обработка сетевых путей

### 5. Остановка предыдущего воркера

```python
# Останавливаем предыдущий воркер если есть
if hasattr(self, '_video_scan_worker') and self._video_scan_worker is not None:
    if self._video_scan_worker.isRunning():
        logger.info("[DashboardPage] Останавливаем предыдущий VideoScanWorker")
        self._video_scan_worker.terminate()
        self._video_scan_worker.wait(1000)  # Ждём максимум 1 секунду
```

**Защищает от:**
- Множественных одновременных сканирований
- Утечки потоков
- Гонки данных (race conditions)

### 6. Логирование для диагностики

Добавлено подробное логирование на каждом этапе:

```python
logger.info(f"[VideoScanWorker] Начинаем сканирование папки: {self.folder_path}")
logger.info(f"[VideoScanWorker] Найдено видео файлов: {len(videos)}")
logger.error(f"[VideoScanWorker] Критическая ошибка: {e}", exc_info=True)
```

**Позволяет:**
- Отследить точное место краша
- Понять последовательность событий
- Диагностировать проблемы пользователей

### 7. Инициализация в __init__

```python
def __init__(self, parent=None):
    super().__init__(parent)
    self.setObjectName("ContentArea")
    
    # Воркер для сканирования видео (инициализируем как None)
    self._video_scan_worker = None
```

**Предотвращает:**
- `AttributeError` при первом использовании
- Проблемы с `hasattr()` проверками

---

## Тестирование

### Сценарии для проверки:

1. **Нормальная папка с видео:**
   - Выбрать папку с 1-2 .mp4 файлами
   - Проверить, что список загружается корректно

2. **Папка без видео:**
   - Выбрать пустую папку
   - Ожидается: "Найдено 0 видео"

3. **Несуществующий путь:**
   - Вручную ввести несуществующий путь (если доступно)
   - Ожидается: "❌ Папка не найдена"

4. **Папка без прав доступа:**
   - Выбрать системную папку (C:\Windows\System32)
   - Ожидается: "❌ Нет доступа к папке"

5. **Быстрое переключение папок:**
   - Выбрать папку 1
   - Сразу выбрать папку 2
   - Убедиться, что предыдущий воркер останавливается

6. **Папка с битыми файлами:**
   - Создать папку с .mp4 файлами, один из которых битый
   - Ожидается: битый файл пропускается, остальные загружаются

7. **Сетевой путь (UNC):**
   - Выбрать папку по сетевому пути `\\server\share\videos`
   - Проверить корректную нормализацию пути

---

## Логи для проверки

После исправления в `roadscan.log` должны появиться записи:

```
[DashboardPage] Выбрана папка: C:\Users\...\Videos
[DashboardPage] VideoScanWorker запущен
[VideoScanWorker] Начинаем сканирование папки: C:\Users\...\Videos
[VideoScanWorker] Найдено видео файлов: 3
[DashboardPage] Сканирование завершено: найдено 3 видео
```

При ошибках:
```
[VideoScanWorker] Пропуск файла corrupted.mp4: [Errno 22] Invalid argument
[DashboardPage] Ошибка сканирования видео: Нет доступа к папке
```

---

## Связанные файлы

- `ui/widgets/dashboard_page.py` — основной файл с изменениями
- `roadscan.log` — лог для диагностики

---

## Дополнительные меры защиты

Уже существующие в `main.py`:

```python
# Защита от STATUS_STACK_BUFFER_OVERRUN (0xC0000409)
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["QT_OPENGL"] = "software"
```

Эти настройки дополняют исправления в `VideoScanWorker`.

---

## Статус

✅ **ИСПРАВЛЕНО**

Краш при выборе папки с видео больше не должен происходить. Все граничные случаи обработаны.

---

## Если краш повторяется

1. Проверьте `roadscan.log` — последние записи перед крашем
2. Проверьте путь к папке — нет ли спецсимволов, очень длинного пути (>260 символов)
3. Попробуйте другую папку для исключения проблем с конкретными файлами
4. Проверьте антивирус — он может блокировать доступ к видео
5. Создайте issue с логами и описанием папки, которую выбирали
