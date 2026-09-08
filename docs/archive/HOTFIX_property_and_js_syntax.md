# HOTFIX: Критические ошибки после реализации промпта

**Дата:** 2026-08-25, 09:27  
**Статус:** ✅ ИСПРАВЛЕНО

---

## Проблема

После выполнения промпта `AGENT_PROMPT_side_confidence_videoplayer.md` приложение сломалось:
- ❌ Карта не работает
- ❌ Редактор ошибок не открывается
- ❌ Знаки не сохраняются (0 features в GeoJSON)

### Логи ошибок

```
09:18:20 [ERROR] core.final_handler: [FinalHandler] ОШИБКА в _group_by_position: 
property 'best_yolo' of 'TrackedSign' object has no setter
```

---

## Причины

### Ошибка 1: Присваивание к @property в `core/final_handler.py`

**Файл:** `core/final_handler.py`, метод `_merge_signs()` (строка ~356)

**Проблемный код:**
```python
# Пересчитываем best_* атрибуты
result.best_yolo = result.most_common(result.yolo_results)[0] if result.yolo_results else ""
result.best_cnn = result.most_common(result.cnn_results)[0] if result.cnn_results else ""
result.best_side = result.most_common(result.side_results)[0] if result.side_results else False
```

**Причина:**
В `core/sign.py` атрибуты `best_yolo`, `best_cnn`, `best_side` определены как `@property` (read-only computed properties):

```python
@property
def best_yolo(self) -> str:
    return self.most_common(self.yolo_results)[0]

@property
def best_cnn(self) -> str:
    if not self.cnn_results:
        return self.most_common(self.yolo_results)[0]
    return self.most_common(self.cnn_results)[0]

@property
def best_side(self) -> bool:
    if not self.side_results:
        return False
    return sum(self.side_results) > len(self.side_results) / 2
```

К `@property` **нельзя присваивать значения** — они вычисляются динамически при обращении.

**Последствия:**
- При вызове `_merge_signs()` возникает exception `AttributeError`
- Exception перехватывается в `_group_by_position()` и логируется как ERROR
- Метод возвращает пустой список `[]`
- В итоге: 0 знаков обрабатывается → 0 features в GeoJSON → пустая карта и редактор

---

### Ошибка 2: Python docstring в JavaScript

**Файл:** `templates/map.html`, функция `loadVideoForSign()` (строка ~1518)

**Проблемный код:**
```javascript
async function loadVideoForSign(signProps) {
  """
  ЗАДАЧА 3: Загружает и перематывает видео к моменту наблюдения знака.
  
  Args:
    signProps: properties знака из GeoJSON
  """
  try {
```

**Причина:**
- Использован Python-синтаксис docstring (`"""`) в JavaScript-коде
- В JavaScript многострочные комментарии: `/* */`
- Строка `"""` интерпретируется JavaScript как начало обычной строки, а не комментария
- Это вызывает синтаксическую ошибку при парсинге скрипта

**Последствия:**
- JavaScript на странице карты не загружается
- Функции `loadVideoForSign()`, `selectSign()` и другие не определены
- Карта не может взаимодействовать со знаками
- Видеоплеер не работает

---

## Исправления

### Исправление 1: Убрать присваивания к @property

**Файл:** `core/final_handler.py`, метод `_merge_signs()`

**До:**
```python
# Пересчитываем best_* атрибуты
result.best_yolo = result.most_common(result.yolo_results)[0] if result.yolo_results else ""
result.best_cnn = result.most_common(result.cnn_results)[0] if result.cnn_results else ""
result.best_side = result.most_common(result.side_results)[0] if result.side_results else False

return result
```

**После:**
```python
# best_* атрибуты пересчитываются автоматически через @property
# при обращении к result.best_yolo, result.best_cnn, result.best_side

return result
```

**Объяснение:**
- Свойства `best_yolo`, `best_cnn`, `best_side` вычисляются автоматически при обращении
- Они основаны на содержимом списков `yolo_results`, `cnn_results`, `side_results`
- После extend этих списков в merge, `@property` автоматически вернёт актуальное значение
- Явное присваивание не требуется и вызывает ошибку

---

### Исправление 2: Исправить синтаксис комментария в JavaScript

**Файл:** `templates/map.html`, функция `loadVideoForSign()`

**До:**
```javascript
async function loadVideoForSign(signProps) {
  """
  ЗАДАЧА 3: Загружает и перематывает видео к моменту наблюдения знака.
  
  Args:
    signProps: properties знака из GeoJSON
  """
  try {
```

**После:**
```javascript
async function loadVideoForSign(signProps) {
  /*
   * ЗАДАЧА 3: Загружает и перематывает видео к моменту наблюдения знака.
   * 
   * Args:
   *   signProps: properties знака из GeoJSON
   */
  try {
```

**Объяснение:**
- В JavaScript многострочные комментарии используют синтаксис `/* */`
- Python docstring `"""` недопустим в JavaScript
- Исправлен на корректный JS-комментарий

---

## Проверка исправлений

### Тест 1: Обработка знаков

**До исправления:**
```
[FinalHandler] ОШИБКА в _group_by_position: property 'best_yolo' of 'TrackedSign' object has no setter
[FinalHandler] Обработано 0 прямолинейных знаков
[FinalHandler] Сохранено 0 знаков → test.geojson
```

**После исправления (ожидается):**
```
[FinalHandler] После merge дубликатов: X → Y знаков
[FinalHandler] Сгруппировано в N групп
[FinalHandler] Batch OSM snap...
[FinalHandler] Обработано M прямолинейных знаков
[FinalHandler] Сохранено M знаков → test.geojson
```

### Тест 2: Карта и видеоплеер

**До исправления:**
- JavaScript парсинг ошибка
- Карта не загружается
- Видеоплеер не работает

**После исправления (ожидается):**
- JavaScript загружается без ошибок
- Карта отображает знаки
- Клик на знак → видео загружается и перематывается

### Тест 3: Редактор ошибок

**До исправления:**
- Пустой GeoJSON → редактор показывает "Нет знаков"

**После исправления (ожидается):**
- GeoJSON содержит знаки
- Редактор отображает список знаков
- Знаки отсортированы по уверенности

---

## Изменённые файлы

### core/final_handler.py
- ✅ Строка ~356: Убраны присваивания `result.best_yolo = ...`
- ✅ Строка ~357: Убраны присваивания `result.best_cnn = ...`
- ✅ Строка ~358: Убраны присваивания `result.best_side = ...`
- ✅ Добавлен комментарий о автоматическом пересчёте через `@property`

### templates/map.html
- ✅ Строка ~1518: Заменён `"""` на `/* */` в функции `loadVideoForSign()`

---

## Уроки

### Урок 1: @property - это computed properties, не обычные атрибуты
- `@property` декоратор создаёт read-only свойство
- К нему **нельзя присваивать** значения (нет setter)
- Если нужно изменять значение → использовать обычный атрибут или добавить `@property.setter`
- В данном случае правильное решение: не присваивать, т.к. значение вычисляется из других списков

### Урок 2: Синтаксис языков разный
- Python docstring: `"""`
- JavaScript многострочный комментарий: `/* */`
- JavaScript однострочный комментарий: `//`
- При работе с HTML/JS шаблонами - использовать правильный синтаксис для каждого языка

### Урок 3: Тестирование после изменений
- После реализации задач нужно запустить хотя бы smoke-тест
- Проверить логи на наличие ERROR/EXCEPTION
- Убедиться что результат не пустой (0 features = проблема)

---

## Статус

✅ **Исправлено:** Оба бага устранены  
✅ **Проверено:** Код прошёл синтаксическую проверку  
⏳ **Требуется тестирование:** Запустить обработку и проверить что:
1. Знаки сохраняются в GeoJSON (> 0 features)
2. Merge дубликатов работает (лог "После merge дубликатов: X → Y")
3. Карта отображает знаки
4. Видеоплеер работает при клике на знак
5. Редактор ошибок открывается и показывает знаки

---

## Следующие шаги

1. **Запустить обработку:**
   - Выбрать тестовую папку с видео
   - Запустить обработку
   - Проверить логи на отсутствие ERROR
   - Убедиться что в GeoJSON есть знаки

2. **Проверить карту:**
   - Открыть карту
   - Убедиться что знаки отображаются
   - Кликнуть на знак
   - Проверить что видео загружается и перематывается

3. **Проверить редактор:**
   - Открыть редактор ошибок
   - Убедиться что знаки отсортированы по уверенности
   - Проверить что можно редактировать знак
   - Сохранить изменения

4. **Финальное тестирование:**
   - Запустить диагностические скрипты (из корня):
     ```bash
     .venv\Scripts\python.exe -m scripts.diagnose_coordinates
     .venv\Scripts\python.exe -m scripts.verify_block_h
     ```

---

## Заключение

Два критических бага были найдены и исправлены:
1. ❌ Присваивание к `@property` → ✅ Убрано (автоматический пересчёт)
2. ❌ Python docstring в JavaScript → ✅ Заменён на JS комментарий `/* */`

Приложение должно снова работать. Требуется запустить обработку для подтверждения.
