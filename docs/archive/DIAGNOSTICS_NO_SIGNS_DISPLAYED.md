# Диагностика проблемы отображения знаков

## Дата: 2026-07-10

### Проблема
После завершения обработки знаки не отображаются ни на карте, ни в редакторе, хотя сохранение прошло без ошибок.

### Возможные причины

1. **GeoJSON не создаётся или пустой**
2. **Редактор не перезагружается автоматически**
3. **Карта не получает события о завершении обработки**
4. **API возвращает пустые данные**
5. **WebSocket соединение не работает**

### Исправления

#### 1. Включена автоперезагрузка редактора (ui/main_window.py)

**Было:**
```python
# ВРЕМЕННО ОТКЛЮЧЕНО: может вызывать краш
# try:
#     QTimer.singleShot(500, self.page_errors.reload)
```

**Стало:**
```python
try:
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(500, self._reload_editor_after_save)
    self.page_processing.log("Обновление редактора запланировано", "info")
except Exception as e:
    print(f"[MainWindow] Предупреждение при планировании обновления редактора: {e}")

def _reload_editor_after_save(self):
    """Перезагружает редактор после сохранения GeoJSON."""
    try:
        print("[MainWindow] Перезагрузка редактора...")
        self.page_errors.reload()
        print("[MainWindow] Редактор перезагружен успешно")
    except Exception as e:
        print(f"[MainWindow] Ошибка при перезагрузке редактора: {e}")
        import traceback
        traceback.print_exc()
```

#### 2. Добавлено подробное логирование (server/map_server.py)

**API /api/signs:**
```python
@app.route("/api/signs")
def api_signs():
    print(f"[API /api/signs] Запрос получен")
    print(f"[API /api/signs] PATH_TO_GEOJSON = {config.PATH_TO_GEOJSON}")
    print(f"[API /api/signs] Файл существует: {os.path.exists(config.PATH_TO_GEOJSON)}")
    print(f"[API /api/signs] Найдено {len(features)} features в GeoJSON")
    print(f"[API /api/signs] Возвращаем {len(result)} знаков клиенту")
```

**emit_processing_finished:**
```python
def emit_processing_finished():
    print("[MapServer] emit_processing_finished вызван")
    print(f"[MapServer] PATH_TO_GEOJSON = {config.PATH_TO_GEOJSON}")
    print(f"[MapServer] Файл существует: {os.path.exists(config.PATH_TO_GEOJSON)}")
    socketio.emit("processing_finished", {"finished": True})
    print("[MapServer] События отправлены клиентам")
```

#### 3. Улучшено логирование на клиенте (templates/map.html)

**loadSigns:**
```javascript
async function loadSigns() {
  console.log("[loadSigns] Начинаем загрузку знаков...");
  console.log(`[loadSigns] Response status: ${r.status}`);
  console.log(`[loadSigns] Получено данных:`, data);
  console.log(`[loadSigns] Обработано знаков: ${signsData.length}`);
  console.log(`[loadSigns] Рендерим ${signsData.length} маркеров...`);
}
```

**renderMarkers:**
```javascript
function renderMarkers() {
  console.log(`[renderMarkers] Начинаем рендеринг, всего знаков: ${signsData.length}`);
  console.log(`[renderMarkers] Удалено старых маркеров: ${oldCount}`);
  console.log(`[renderMarkers] Отрендерено маркеров: ${filteredCount}`);
}
```

**Socket events:**
```javascript
socket.on("processing_finished", ({ finished }) => {
  console.log("[Socket] processing_finished event received:", finished);
  console.log("[Socket] Processing finished, scheduling data reload...");
  console.log("[Socket] Executing delayed loadAll()...");
  console.log("[Socket] Data reloaded successfully");
}
```

### Процесс диагностики

После следующего запуска проверьте логи в следующем порядке:

#### 1. Проверка сохранения GeoJSON

**В консоли Python ищите:**
```
[FinalHandler] save_result вызван:
  - Знаков: N
  - Поворотов: M
  - Путь: C:\...\output.geojson
[FinalHandler] После обработки: N features
[FinalHandler] После дедупликации: N features
[FinalHandler] Сохранено N знаков → C:\...\output.geojson
```

**Проверка файла:**
- Откройте файл GeoJSON в текстовом редакторе
- Убедитесь что есть массив `features` с элементами
- Проверьте что у features есть `geometry.coordinates`

#### 2. Проверка уведомления карты

**В консоли Python ищите:**
```
[MainWindow] Уведомляем карту о завершении...
[MapServer] emit_processing_finished вызван
[MapServer] PATH_TO_GEOJSON = C:\...\output.geojson
[MapServer] Файл существует: True
[MapServer] События отправлены клиентам
```

#### 3. Проверка получения события на клиенте

**В браузерной консоли (F12) ищите:**
```
[Socket] processing_finished event received: true
[Socket] Processing finished, scheduling data reload...
[Socket] Executing delayed loadAll()...
```

#### 4. Проверка загрузки знаков

**В браузерной консоли ищите:**
```
[loadSigns] Начинаем загрузку знаков...
[loadSigns] Response status: 200
[loadSigns] Получено данных: [{...}, {...}, ...]
[loadSigns] Обработано знаков: N
```

**В консоли Python (сервер) ищите:**
```
[API /api/signs] Запрос получен
[API /api/signs] PATH_TO_GEOJSON = C:\...\output.geojson
[API /api/signs] Файл существует: True
[API /api/signs] Найдено N features в GeoJSON
[API /api/signs] Возвращаем N знаков клиенту
```

#### 5. Проверка рендеринга маркеров

**В браузерной консоли ищите:**
```
[renderMarkers] Начинаем рендеринг, всего знаков: N
[renderMarkers] Удалено старых маркеров: M
[renderMarkers] Отрендерено маркеров: N
```

#### 6. Проверка редактора

**В консоли Python ищите:**
```
[MainWindow] Обновление редактора запланировано
[MainWindow] Перезагрузка редактора...
[MainWindow] Редактор перезагружен успешно
```

### Возможные проблемы и решения

#### Проблема 1: PATH_TO_GEOJSON пустой

**Симптомы:**
```
[MapServer] PATH_TO_GEOJSON = 
[API /api/signs] PATH_TO_GEOJSON пустой
```

**Решение:**
- Проверьте что вы выбрали файл GeoJSON на Dashboard
- Убедитесь что config.PATH_TO_GEOJSON устанавливается при старте

#### Проблема 2: Файл не существует

**Симптомы:**
```
[MapServer] Файл существует: False
[API /api/signs] Файл не найден: C:\...\output.geojson
```

**Решение:**
- Проверьте что FinalHandler успешно сохранил файл
- Проверьте права на запись в директорию
- Убедитесь что путь корректный (нет невалидных символов)

#### Проблема 3: GeoJSON пустой

**Симптомы:**
```
[API /api/signs] Найдено 0 features в GeoJSON
[loadSigns] Обработано знаков: 0
```

**Решение:**
- Откройте GeoJSON файл и проверьте содержимое
- Проверьте что FinalHandler получил знаки из контроллера:
  ```
  [MainWindow] Получено из контроллера: N знаков
  ```
- Если N = 0, проблема в детекции, не в отображении

#### Проблема 4: WebSocket не работает

**Симптомы:**
- Нет логов `[Socket] processing_finished event received`
- В браузере: `Socket connection error`

**Решение:**
- Проверьте что сервер карты запущен
- Откройте DevTools → Network → WS и проверьте соединение
- Проверьте порт 3000 не занят другим приложением

#### Проблема 5: Координаты некорректные

**Симптомы:**
```
[renderMarkers] Отрендерено маркеров: N
```
Но маркеров не видно на карте.

**Решение:**
- Откройте браузерную консоль и выполните:
  ```javascript
  console.log(signsData[0])
  ```
- Проверьте что `lat` и `lon` имеют разумные значения (не 0, не null)
- Попробуйте центрировать карту вручную на координаты первого знака

#### Проблема 6: Редактор падает при загрузке

**Симптомы:**
```
[MainWindow] Ошибка при перезагрузке редактора: ...
```

**Решение:**
- Проверьте traceback в консоли
- Возможно проблема с видео файлом или капчером
- Проверьте что все видео доступны

### Быстрая проверка

После завершения обработки выполните:

1. **Проверка файла:**
   ```powershell
   # Откройте PowerShell
   Get-Content "путь\к\output.geojson" | Select-String -Pattern "features"
   ```

2. **Проверка в браузере:**
   - Откройте http://localhost:3000/api/signs
   - Должен вернуться JSON массив с знаками

3. **Ручная перезагрузка:**
   - Откройте карту
   - Нажмите F12 (DevTools)
   - В консоли выполните: `loadAll()`
   - Проверьте логи

4. **Проверка редактора:**
   - Перейдите на вкладку "Редактор"
   - Должен показаться список знаков
   - Если пустой — проверьте логи редактора

### Дополнительные улучшения

Если после всех проверок проблема сохраняется:

1. **Добавьте кнопку ручной перезагрузки на карте:**
   - В topbar уже есть кнопка "↺ Перезагрузить"
   - Нажмите её после завершения обработки

2. **Проверьте что карта открыта:**
   - Перейдите на вкладку "Карта"
   - WebSocket должен автоматически подключиться

3. **Проверьте фильтры:**
   - Убедитесь что фильтр по типу пустой
   - Убедитесь что выбран "Все" стороны

4. **Проверьте масштаб карты:**
   - Нажмите кнопку "По треку" чтобы центрировать

### Следующие шаги

После сбора логов мы сможем точно определить на каком этапе происходит сбой:
1. Сохранение GeoJSON
2. Уведомление через WebSocket
3. Загрузка данных через API
4. Рендеринг маркеров
5. Загрузка в редактор

Запустите обработку снова и отправьте:
- Логи из консоли Python (полностью)
- Логи из браузерной консоли (вкладка Console)
- Содержимое http://localhost:3000/api/signs (если доступно)
