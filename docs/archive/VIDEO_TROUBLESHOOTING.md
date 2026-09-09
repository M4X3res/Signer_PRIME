# 🔧 Устранение проблемы "Видео не работает"

## Диагностика

Видео на карте использует новый эндпоинт `/api/video_clip/` который **требует**:
1. ✅ Перезапуск приложения (чтобы Flask подхватил новый эндпоинт)
2. ✅ Установленный ffmpeg в PATH
3. ✅ Очистка кэша браузера (если WebEngineView кэширует старый JS)

---

## Шаг 1: Проверить что ffmpeg установлен

Откройте терминал/cmd и выполните:

```bash
ffmpeg -version
```

### Если команда не найдена:

**Windows (рекомендуемый способ - Chocolatey):**
```bash
choco install ffmpeg
```

**Windows (альтернатива - скачать вручную):**
1. Скачать: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
2. Распаковать в `C:\ffmpeg`
3. Добавить `C:\ffmpeg\bin` в PATH:
   - Win+R → `sysdm.cpl` → Дополнительно → Переменные среды
   - Системные переменные → Path → Изменить → Создать
   - Добавить `C:\ffmpeg\bin`
   - OK → OK → OK
4. **Перезапустить терминал** и проверить: `ffmpeg -version`

**Linux:**
```bash
sudo apt install ffmpeg  # Ubuntu/Debian
sudo dnf install ffmpeg  # Fedora
```

**MacOS:**
```bash
brew install ffmpeg
```

---

## Шаг 2: Полностью перезапустить приложение

**ВАЖНО:** Не достаточно просто закрыть окно! Нужно:

1. Закрыть приложение RoadScanner
2. **Убить процесс Python** (если остался висеть):
   ```bash
   # Windows
   taskkill /F /IM python.exe
   
   # Linux/Mac
   killall python
   ```
3. Запустить заново:
   ```bash
   python main.py
   ```

---

## Шаг 3: Очистить кэш WebEngine (если нужно)

Если видео всё ещё не работает после шагов 1-2, удалите кэш:

**Windows:**
```
C:\Users\<USERNAME>\AppData\Local\RoadScanner\
```

**Linux:**
```
~/.local/share/RoadScanner/
```

**MacOS:**
```
~/Library/Application Support/RoadScanner/
```

Или просто добавьте в начало `main.py`:
```python
import os
from PyQt6.QtWebEngineCore import QWebEngineProfile

# После создания QApplication
profile = QWebEngineProfile.defaultProfile()
profile.clearHttpCache()
```

---

## Шаг 4: Проверка работы

1. Запустить приложение
2. Обработать видео (если ещё не обработано)
3. Открыть вкладку "Карта"
4. Кликнуть на маркер знака

### Ожидаемое поведение:

✅ **Если ffmpeg установлен:**
- Первый клик: транскодирование ~5-10 секунд → воспроизведение
- Логи сервера: `[API /api/video_clip] Транскодирование: ...`
- Повторный клик: кэш, мгновенное воспроизведение
- Логи сервера: `[API /api/video_clip] Cache hit: ...`

❌ **Если ffmpeg НЕ установлен:**
- Панель видео показывает: "Для воспроизведения видео требуется ffmpeg. Установите его и добавьте в PATH. Загрузка: https://ffmpeg.org/download.html"

❌ **Если сервер не перезапущен:**
- Ошибка 404 (Not Found) при запросе `/api/video_clip/...`
- Или старое поведение "Video loading timeout (10s)"

---

## Шаг 5: Проверка логов

Откройте консоль разработчика WebEngine (если доступна) или проверьте логи Flask в терминале:

### Успешный запрос (первый раз):
```
[API /api/video_clip/0] start=123.5, duration=15
[API /api/video_clip] Транскодирование: C:\Videos\video.mp4 -> C:\Videos\video_clip_123_15.webm
[API /api/video_clip] Запуск ffmpeg: ffmpeg -ss 123.5 -i ...
[API /api/video_clip] Транскодирование завершено: C:\Videos\video_clip_123_15.webm
```

### Успешный запрос (кэш):
```
[API /api/video_clip/0] start=123.5, duration=15
[API /api/video_clip] Cache hit: C:\Videos\video_clip_123_15.webm
```

### Ошибка (ffmpeg не найден):
```
[API /api/video_clip] ffmpeg не найден в PATH
```

---

## Альтернатива: Временно использовать старый эндпоинт (НЕ рекомендуется)

Если нужно срочно проверить что-то другое и видео не критично, можно временно вернуть старый код:

### templates/map.html, строка ~1702:

```javascript
// Старый код (только для MP4 с H.264):
const videoSrc = `${API}/video/${videoIdx}`;

// Вместо нового:
// const videoSrc = `${API}/video_clip/${videoIdx}?start=${clipStart}&duration=${clipDuration}`;
```

И строка ~1710:
```javascript
source.type = 'video/mp4';  // Вместо 'video/webm'
```

**НО:** Это НЕ решит проблему если QtWebEngine без H.264 кодеков!

---

## Диагностика кодеков QtWebEngine

Если хотите проверить какие кодеки поддерживает ваш QtWebEngine:

1. Откройте карту
2. Нажмите кнопку "🔍" (диагностика кодеков) рядом с видеоплеером
3. Смотрите результат:
   - ✅ `H.264+AAC: maybe` или `probably` → QtWebEngine с проприетарными кодеками
   - ❌ `H.264+AAC: нет` → QtWebEngine БЕЗ проприетарных кодеков → нужен ffmpeg

Большинство PyQt6-WebEngine из PyPI **не имеют** H.264/AAC кодеков.

---

## Итоговый чек-лист

- [ ] ffmpeg установлен и доступен в PATH (`ffmpeg -version` работает)
- [ ] Приложение полностью перезапущено (процесс Python убит и запущен заново)
- [ ] Кэш WebEngine очищен (если были проблемы)
- [ ] После клика на знак видно транскодирование в логах
- [ ] Видео воспроизводится в WebM-плеере

Если всё ещё не работает → отправьте логи Flask-сервера из терминала!

---

**Дата создания:** 2026-09-07  
**Версия:** RoadScanner v2.0 (Signer PRIME)
