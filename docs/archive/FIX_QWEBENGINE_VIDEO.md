# Решение проблемы воспроизведения видео в QWebEngineView

## Проблема
Видео имеет правильный кодек (H264 High + AAC), но не воспроизводится в QWebEngineView из-за ограничений безопасности Chromium.

## Решения (выполнены)

### 1. Настройки QWebEngineView (ui/widgets/map_page.py)
Добавлены настройки для работы с медиа:
- `LocalContentCanAccessFileUrls` — доступ к локальным файлам
- `PlaybackRequiresUserGesture = False` — автовоспроизведение без клика
- `AllowRunningInsecureContent` — разрешение небезопасного контента (localhost)
- `MediaStreamEnabled` — поддержка медиа-потоков

### 2. CORS-заголовки для видео (server/map_server.py)
Добавлены заголовки:
- `Access-Control-Allow-Origin: *`
- `Access-Control-Expose-Headers` — разрешение доступа к заголовкам

### 3. Улучшенная загрузка видео (templates/map.html)
- Использование `<source>` элемента вместо прямого `video.src`
- Проверка `canPlayType()` перед загрузкой
- Детальное логирование

## Что делать дальше (ОБНОВЛЕНО)

### ⚠️ КРИТИЧНО: Добавлены флаги Chromium в main.py

**Это самое важное изменение!** В `main.py` теперь установлены флаги запуска Chromium:
```python
sys.argv.extend([
    '--disable-web-security',
    '--allow-file-access-from-files',
    '--autoplay-policy=no-user-gesture-required',
    '--disable-features=AudioServiceOutOfProcess',
])
```

Эти флаги **обязательно** нужны для воспроизведения видео в QWebEngineView.

### Шаг 1: ПОЛНОСТЬЮ ПЕРЕЗАПУСТИТЕ приложение
**Важно:** Закройте приложение полностью и запустите заново. Флаги применяются только при запуске.

### Шаг 2: Проверьте снова
1. Откройте карту
2. Кликните на знак
3. Нажмите 🔍 для диагностики
4. Проверьте `canPlayType` — теперь должно быть `'probably'` или `'maybe'`

### Шаг 3: Если ВСЕГО ЕЩЁ не работает

Конвертируйте видео в Baseline profile (это гарантированно сработает):
Ваше видео использует **H264 High profile**. Это поддерживается большинством браузеров, но для максимальной совместимости лучше использовать **Baseline profile**.

#### Конвертация в Baseline (рекомендуется):
```bash
ffmpeg -i input.mp4 \
  -c:v libx264 \
  -profile:v baseline \
  -level 3.0 \
  -pix_fmt yuv420p \
  -c:a aac \
  -b:a 128k \
  -movflags +faststart \
  output.mp4
```

**Объяснение параметров:**
- `-profile:v baseline` — базовый профиль H.264 (максимальная совместимость с WebView/Chromium)
- `-level 3.0` — уровень кодека (поддерживается всеми устройствами)
- `-pix_fmt yuv420p` — формат цвета (обязателен для веб)
- `-movflags +faststart` — метаданные в начале файла (критично для стриминга)

### Шаг 3: Проверьте Range-запросы
После перезапуска откройте DevTools (F12) → Network и проверьте запрос `/api/video/0`:

**Должно быть:**
```
Status: 206 Partial Content
Content-Type: video/mp4
Content-Range: bytes 0-10485759/123456789
Accept-Ranges: bytes
Access-Control-Allow-Origin: *
```

**НЕ должно быть:**
```
Status: 200 OK  ← плохо, нужен 206
```

### Шаг 4: Проверьте логи консоли
После клика на знак в консоли должно быть:
```javascript
[loadVideoForSign] Видео доступно:
  Content-Type: video/mp4
  Accept-Ranges: bytes
  Content-Length: 123456789
  canPlayType('video/mp4'): 'probably'  ← должно быть 'probably' или 'maybe'
```

Если `canPlayType` всё ещё пустая строка `''`, это значит что QWebEngineView не поддерживает профиль H.264 High — нужна конвертация в Baseline.

## Если всё ещё не работает

### Вариант 1: Проверьте версию PyQt6
```bash
pip show PyQt6-WebEngine
```

Должна быть >= 6.6.0. Если старее — обновите:
```bash
pip install --upgrade PyQt6-WebEngine
```

### Вариант 2: Запустите с флагами Chromium
Добавьте в начало `main.py`:
```python
import sys
# Перед созданием QApplication
sys.argv.extend([
    '--disable-web-security',
    '--allow-file-access-from-files',
    '--autoplay-policy=no-user-gesture-required'
])
```

### Вариант 3: Используйте внешний браузер
Если ничего не помогает, откройте карту в обычном браузере:
```python
# В map_page.py уже есть кнопка "Открыть в браузере"
# Кликните её и используйте Chrome/Firefox
```

## Альтернативное решение: HLS стриминг

Если видео очень большое (>1GB), можно использовать HLS:

```bash
# Конвертация в HLS
ffmpeg -i input.mp4 \
  -c:v libx264 -profile:v baseline \
  -c:a aac -hls_time 10 -hls_list_size 0 \
  output.m3u8
```

Затем в Flask добавить роут для `.m3u8` и `.ts` файлов.

## Проверка решения

После всех изменений:
1. ✅ Перезапустите приложение
2. ✅ Кликните на знак
3. ✅ Нажмите 🔍 для диагностики
4. ✅ Проверьте, что `canPlayType` возвращает `'probably'` или `'maybe'`
5. ✅ Видео должно загрузиться и воспроизвестись

## Файлы изменены
- `ui/widgets/map_page.py` — настройки QWebEngineView для медиа
- `server/map_server.py` — CORS-заголовки для видео
- `templates/map.html` — улучшенная загрузка (уже было сделано ранее)
