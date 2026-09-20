# Как получить логи из Console браузера

## Шаги:

1. **Запустите сервер:**
   ```bash
   python test_with_logs.py
   ```

2. **Откройте браузер** по адресу http://127.0.0.1:3000

3. **Откройте DevTools:**
   - **Windows/Linux:** Нажмите `F12` или `Ctrl+Shift+I`
   - **Mac:** `Cmd+Option+I`

4. **Перейдите на вкладку "Console"** (не "Network", не "Elements")

5. **Найдите сообщения начинающиеся с `[loadTileLayer]`**
   - Их должно быть несколько строк
   - Они показывают процесс загрузки карты

6. **Скопируйте ВСЕ сообщения:**
   - Правой кнопкой мыши в Console → "Save as..."
   - Или просто выделите все и скопируйте (Ctrl+A, Ctrl+C)

7. **Вставьте в файл `console.txt`**

## Какие сообщения нужны:

```
[loadTileLayer] Config loaded: ...
[loadTileLayer] Creating vector tile layer...
[loadTileLayer] Attempting to load vector tile styles...
[loadTileLayer] Styles loaded successfully: ... layers
[VectorGrid] Tile loaded: ...
[VectorGrid] Tile error: ...
```

## Если не видите сообщений `[loadTileLayer]`:

Возможно в Console включён фильтр. Убедитесь что:
- Выбран "All levels" (не только Errors)
- Не установлен фильтр по тексту
- Очистите Console (кнопка 🚫) и обновите страницу (F5)
