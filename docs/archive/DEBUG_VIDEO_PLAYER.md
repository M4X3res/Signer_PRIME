# Отладка видео-плеера на карте

## Проблема
Видео-плеер на карте не загружает видео при клике на знак.

## Исправления (уже сделаны)

### 1. Исправлены пути к видеофайлам в `server/map_server.py`
**Проблема:** Роуты `/api/video/<idx>` и `/api/video_info/<idx>` использовали `config.VIDEOS[idx]` напрямую (только имя файла), вместо полного пути.

**Исправление:** Добавлена конкатенация с `config.PATH_TO_VIDEO`:
```python
if config.PATH_TO_VIDEO:
    video_path = os.path.join(config.PATH_TO_VIDEO, config.VIDEOS[video_idx])
else:
    video_path = config.VIDEOS[video_idx]
```

### 2. Добавлено детальное логирование в `templates/map.html`
Теперь функция `loadVideoForSign()` выводит:
- Полные properties знака
- Значение `rawFrames` до и после парсинга
- Тип данных `rawFrames`
- Все этапы загрузки видео

## Быстрая диагностика

### Шаг 1: Проверьте логи Flask
В терминале, где запущен Flask-сервер, должны появиться:
```
[API /api/video/0] Запрос видео
[API /api/video/0] Раздаём: C:\path\to\video.mp4
[API /api/video/0] Range request: 0-10485759/123456789
```

### Шаг 2: Проверьте консоль браузера (F12)
После клика на знак:
```
[loadVideoForSign] Начало загрузки, props: {...}
[loadVideoForSign] rawFrames (после парсинга): [12345, 12346, ...]
[loadVideoForSign] video.src = http://localhost:3000/api/video/0
[loadVideoForSign] Видео доступно, Content-Type: video/mp4
```

### Шаг 3: Проверьте Network (вкладка DevTools)
1. Откройте DevTools (F12) → Network
2. Кликните на знак
3. Найдите запрос `/api/video/0`
4. Проверьте:
   - **Status:** должен быть `206 Partial Content` (не 200)
   - **Content-Type:** должен быть `video/mp4`
   - **Accept-Ranges:** должен быть `bytes`
   - **Content-Range:** должен быть `bytes 0-xxx/yyy`

### Шаг 4: Проверьте кодек видео
```bash
ffprobe -v error -show_entries stream=codec_name,codec_type -of default=noprint_wrappers=1 video.mp4
```
Ожидаемый вывод:
```
codec_name=h264
codec_type=video
codec_name=aac
codec_type=audio
```

## Как проверить

### 1. Откройте консоль разработчика браузера
- В Chrome/Edge: F12 → вкладка Console
- В Firefox: F12 → вкладка Консоль

### 2. Запустите приложение и откройте карту

### 3. Кликните на любой знак на карте

### 4. В консоли должны появиться логи:
```
[loadVideoForSign] Начало загрузки, props: {id: "...", type: "...", absolute_frame_numbers: [...], ...}
[loadVideoForSign] rawFrames (до парсинга): [...] тип: object
[loadVideoForSign] rawFrames (после парсинга): [12345, 12346, ...]
[loadVideoForSign] avgFrame=12345, videoIdx=0, frameInVideo=12345
[loadVideoForSign] FPS=60, seconds=205.75
[loadVideoForSign] Загрузка нового видео: 0
[loadVideoForSign] video.src = http://localhost:3000/api/video/0
[loadVideoForSign] Видео доступно, Content-Type: video/mp4
[loadVideoForSign] Метаданные загружены, duration=1060
[loadVideoForSign] Видео готово к просмотру
```

## Возможные проблемы и решения

### Проблема 1: "Нет данных о кадрах для этого знака"
**Причина:** В GeoJSON отсутствует поле `absolute_frame_numbers` или `abs_frame`.

**Решение:** Проверьте GeoJSON-файл. В каждом знаке должно быть одно из полей:
- `absolute_frame_numbers` — массив чисел `[12345, 12346, ...]`
- `abs_frame` — строка `"[12345, 12346, ...]"` или массив

**Где проверить:**
```python
# В Python-коде (final_handler.py)
# Убедитесь, что SignRecord.abs_frame_numbers заполняется
print(sign.abs_frame_numbers)
```

### Проблема 2: "Видео недоступно: 404 Not Found"
**Причина:** 
- `config.PATH_TO_VIDEO` не установлен
- `config.VIDEOS` пустой или не содержит нужный индекс
- Файл не существует по указанному пути

**Решение:**
1. Проверьте, что видео выбрано в Dashboard
2. Проверьте логи Flask-сервера:
   ```
   [API /api/video/0] Запрос видео
   [API /api/video/0] Раздаём: C:\path\to\video.mp4
   ```
3. Если видит "Файл не существует" — проверьте путь к видео

### Проблема 3: "Формат видео не поддерживается браузером" (MEDIA_ERR_SRC_NOT_SUPPORTED, код 4)
**Причина:** Браузер не поддерживает кодек видео или контейнер.

**Что поддерживается:**
- ✅ **MP4** (H.264 видео + AAC аудио) — лучший выбор, поддерживается всеми браузерами
- ✅ **WebM** (VP8/VP9 видео + Vorbis/Opus аудио) — Chrome, Firefox, Edge
- ⚠️ **AVI** — зависит от кодека внутри, обычно НЕ поддерживается
- ⚠️ **MKV** — не поддерживается большинством браузеров
- ⚠️ **MOV** — ограниченная поддержка

**Решение 1: Проверьте кодек вашего видео**
```bash
# Установите FFmpeg, затем:
ffprobe -v error -select_streams v:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 video.mp4
# Должно вывести: h264

ffprobe -v error -select_streams a:0 -show_entries stream=codec_name -of default=noprint_wrappers=1:nokey=1 video.mp4
# Должно вывести: aac
```

**Решение 2: Конвертируйте в web-совместимый формат**
```bash
# Конвертация в H.264/AAC (оптимизировано для веб):
ffmpeg -i input.mp4 -c:v libx264 -preset medium -crf 23 -c:a aac -b:a 128k -movflags +faststart output.mp4

# Параметры:
# -c:v libx264     : кодек H.264 (совместим со всеми браузерами)
# -preset medium   : баланс скорости и качества
# -crf 23          : качество (18-28, меньше = лучше)
# -c:a aac         : аудио кодек AAC
# -b:a 128k        : битрейт аудио
# -movflags +faststart : оптимизация для потокового воспроизведения (метаданные в начале файла)
```

**Решение 3: Проверьте, что Flask отдаёт правильный MIME-тип**
Откройте DevTools (F12) → Network → кликните на запрос `/api/video/0` → Headers:
```
Content-Type: video/mp4
Accept-Ranges: bytes
```

Если `Content-Type` неправильный (например, `application/octet-stream`), видео не будет проигрываться.

**Решение 4: Проверьте Range-запросы**
Браузер должен получать HTTP 206 Partial Content при запросе Range:
```bash
curl -I -H "Range: bytes=0-1023" http://localhost:3000/api/video/0

# Ожидаемый ответ:
# HTTP/1.1 206 Partial Content
# Content-Range: bytes 0-1023/123456789
# Accept-Ranges: bytes
```

### Проблема 4: Видео загружается, но не перематывается на нужный момент
**Причина:** Неправильно вычисляется `videoIdx` или `frameInVideo` из-за несоответствия `FRAMES_PER_VIDEO`.

**Решение:**
1. Проверьте реальную длину видео:
   ```python
   import cv2
   cap = cv2.VideoCapture("video.mp4")
   fps = cap.get(cv2.CAP_PROP_FPS)
   frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
   print(f"FPS: {fps}, Frames: {frame_count}")
   cap.release()
   ```

2. Обновите константу в `configs/config.py`:
   ```python
   FRAMES_PER_VIDEO: int = <реальное_количество_кадров>
   ```

3. Эта же константа используется в `map.html` (строка 1563):
   ```javascript
   const FRAMES_PER_VIDEO = 63600;
   ```
   Если нужно, измените и там.

## Проверка через curl

Проверьте доступность API напрямую:

```bash
# Проверка метаданных видео
curl http://localhost:3000/api/video_info/0

# Ожидаемый ответ:
# {"video_idx": 0, "fps": 60.0, "frame_count": 63600, "duration_sec": 1060.0}

# Проверка доступности видео
curl -I http://localhost:3000/api/video/0

# Ожидаемый ответ:
# HTTP/1.1 200 OK
# Content-Type: video/mp4
# Content-Length: ...
```

## Дополнительная информация

### Структура потока данных:
1. **GeoJSON** содержит `absolute_frame_numbers` для каждого знака
2. **Frontend (map.html)** получает эти данные через `/api/sign/<id>`
3. **Frontend** вычисляет `videoIdx = avgFrame / FRAMES_PER_VIDEO`
4. **Frontend** запрашивает `/api/video_info/<videoIdx>` для получения FPS
5. **Frontend** вычисляет `seconds = frameInVideo / fps`
6. **Frontend** загружает видео через `/api/video/<videoIdx>`
7. **Frontend** перематывает `video.currentTime = seconds`

### Ключевые файлы:
- `server/map_server.py` — Flask API роуты (строки 371-438)
- `templates/map.html` — Frontend логика видео (строки 1518-1700)
- `configs/config.py` — Константа FRAMES_PER_VIDEO (строка 20)
- `core/final_handler.py` — Генерация GeoJSON с absolute_frame_numbers

## Следующие шаги

Если проблема всё ещё не решена, проверьте:
1. Логи в консоли браузера (F12)
2. Логи Flask-сервера в терминале
3. Содержимое GeoJSON-файла (`absolute_frame_numbers` должно быть массивом чисел)
4. Доступность видеофайлов по путям в `config.VIDEOS`
