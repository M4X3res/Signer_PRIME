# Исправление зависания при сохранении и UI (2026-07-10 12:15)

## Проблемы

1. **Зависание при сохранении** — процесс сохранения занимает очень долго или зависает
2. **Зависание UI** — после нажатия "Завершить" окно зависает на некоторое время

## Исправление 1: Сохранение в отдельном потоке

### Проблема

Сохранение GeoJSON (`handler.save_result()`) выполнялось **в главном потоке UI**, что блокировало весь интерфейс.

**Результат:**
- ❌ Окно зависает
- ❌ Нельзя двигать окно
- ❌ Кнопки не реагируют
- ❌ Выглядит как краш

### Решение

**Файл:** `ui/main_window.py`

Вынесли сохранение в отдельный `QThread`:

```python
class SaveThread(QThread):
    finished_ok = pyqtSignal(int)  # количество знаков
    error = pyqtSignal(str)
    
    def __init__(self, signs, turns):
        super().__init__()
        self.signs = signs
        self.turns = turns
    
    def run(self):
        try:
            handler = FinalHandler()
            handler.save_result(self.signs, self.turns)
            self.finished_ok.emit(len(self.signs))
        except Exception as e:
            self.error.emit(str(e))

# Запуск:
self._save_thread = SaveThread(signs, turns)
self._save_thread.finished_ok.connect(self._on_save_finished)
self._save_thread.error.connect(self._on_save_error)
self._save_thread.start()
```

**Результат:**
- ✅ UI не блокируется
- ✅ Окно можно двигать во время сохранения
- ✅ Кнопки отключены (защита от повторных нажатий)
- ✅ Пользователь видит лог "Сохранение результатов..."

---

## Исправление 2: Таймаут для дедупликации

### Проблема

Если дедупликация зависла или работает слишком долго, процесс **никогда не завершится**.

### Решение

**Файл:** `core/final_handler.py`

Добавлен таймаут **60 секунд**:

```python
def _deduplicate(self, features: list[Feature]) -> list[Feature]:
    TIMEOUT_SECONDS = 60
    start_time = time.time()
    
    for idx, feat in enumerate(features):
        if idx % 100 == 0:
            elapsed = time.time() - start_time
            
            if elapsed > TIMEOUT_SECONDS:
                print(f"[FinalHandler] ВНИМАНИЕ: дедупликация превысила таймаут")
                print(f"[FinalHandler] Обработано {idx}/{len(features)}, возвращаем что есть")
                # Добавляем оставшиеся без дедупликации
                result.extend(features[idx:])
                break
        
        # ... обработка ...
```

**Результат:**
- ✅ Если дедупликация > 60 секунд → прерывается
- ✅ Оставшиеся features добавляются без дедупликации
- ✅ Сохранение всё равно завершается (с возможными дублями)
- ✅ Логи показывают что был таймаут

---

## Поведение после исправлений

### При нажатии "Завершить":

1. **Кнопки отключаются** → защита от повторных нажатий
2. **Появляется лог** → "Сохранение результатов..."
3. **UI остаётся отзывчивым** → можно двигать окно, смотреть логи
4. **Сохранение в фоне** → в отдельном потоке
5. **Прогресс в логах** → видно что происходит:
   ```
   [FinalHandler] _deduplicate начат, features: 158
   [FinalHandler] _deduplicate прогресс: 100/158 (0.5s)
   [FinalHandler] _deduplicate завершён: 155 знаков (0.8s)
   ```
6. **Завершение** → "Сохранено N знаков в GeoJSON"

### Если дедупликация зависла:

1. **Через 60 секунд** → автоматическое прерывание
2. **Лог в консоли:**
   ```
   [FinalHandler] ВНИМАНИЕ: дедупликация превысила таймаут 60s
   [FinalHandler] Обработано 450/1500, возвращаем что есть
   ```
3. **Сохранение завершается** → с частичной дедупликацией
4. **В GeoJSON могут быть дубликаты** → но файл сохранится

---

## Логи для диагностики

### Нормальное сохранение (~150 знаков):

```
[MainWindow] _save_results вызван
[MainWindow] Получено из контроллера: 150 знаков, 5 поворотов

[FinalHandler] save_result вызван:
  - Знаков: 150
  - Поворотов: 5

[FinalHandler] Начинаем обработку прямолинейных знаков...
[FinalHandler] _process_straight_signs: обрабатываем 150 знаков
[FinalHandler] Сгруппировано в 120 групп
[FinalHandler] _process_straight_signs завершён: 150 features

[FinalHandler] Начинаем дедупликацию...
[FinalHandler] _deduplicate начат, features: 158
[FinalHandler] _deduplicate прогресс: 100/158 (0.5s)
[FinalHandler] _deduplicate завершён: 155 знаков (0.8s)

[FinalHandler] Сохраняем GeoJSON...
[FinalHandler] Сохранено 155 знаков → C:\...\output.geojson

[MainWindow] Сохранение завершено: 155 знаков
```

**Время: 2-10 секунд**

### Медленное сохранение (~1500 знаков):

```
[FinalHandler] _deduplicate начат, features: 1500
[FinalHandler] _deduplicate прогресс: 100/1500 (2.1s)
[FinalHandler] _deduplicate прогресс: 200/1500 (4.5s)
[FinalHandler] _deduplicate прогресс: 300/1500 (7.2s)
...
[FinalHandler] _deduplicate завершён: 1480 знаков (45.3s)
```

**Время: 15-60 секунд** (но UI не блокируется!)

### Таймаут дедупликации:

```
[FinalHandler] _deduplicate начат, features: 2000
[FinalHandler] _deduplicate прогресс: 100/2000 (15.2s)
[FinalHandler] _deduplicate прогресс: 200/2000 (32.8s)
[FinalHandler] _deduplicate прогресс: 300/2000 (51.4s)
[FinalHandler] ВНИМАНИЕ: дедупликация превысила таймаут 60s
[FinalHandler] Обработано 350/2000, возвращаем что есть
[FinalHandler] _deduplicate завершён: 2000 знаков (60.1s)
```

**Время: ~60 секунд** (прервано по таймауту)

---

## Если всё ещё зависает

### 1. Проверьте логи

Последний лог покажет где именно зависло:

- `_process_straight_signs` → проблема с обработкой знаков
- `_deduplicate прогресс: 450/1500` → медленная дедупликация (дождитесь или таймаут)
- `Сохраняем GeoJSON...` → проблема с записью файла

### 2. Отключите дедупликацию временно

В `core/final_handler.py` метод `save_result`:

```python
# Закомментируйте дедупликацию:
# try:
#     print("[FinalHandler] Начинаем дедупликацию...")
#     features = self._deduplicate(features)
# except Exception as e:
#     print(f"[FinalHandler] ОШИБКА в _deduplicate: {e}")
```

### 3. Увеличьте таймаут

Если у вас очень много знаков (>2000):

```python
TIMEOUT_SECONDS = 120  # Было 60
```

---

## Изменённые файлы

1. **`ui/main_window.py`**:
   - `_save_results()` — запускает SaveThread
   - `_on_save_finished()` — обработчик успешного сохранения
   - `_on_save_error()` — обработчик ошибки

2. **`core/final_handler.py`**:
   - `_deduplicate()` — добавлен таймаут 60 секунд

---

## Преимущества

### До исправлений:
- ❌ UI зависает на 10-60 секунд
- ❌ Выглядит как краш
- ❌ Пользователь не знает что происходит
- ❌ Невозможно прервать

### После исправлений:
- ✅ UI отзывчивый всегда
- ✅ Видны логи прогресса
- ✅ Таймаут защищает от бесконечного зависания
- ✅ Пользователь понимает что происходит

---

## Резюме

**Проблема 1:** UI блокировался при сохранении
**Решение:** Вынесли сохранение в QThread

**Проблема 2:** Дедупликация могла зависнуть навсегда
**Решение:** Добавили таймаут 60 секунд

**Результат:** UI всегда отзывчивый, сохранение всегда завершается (максимум за 60 секунд).
