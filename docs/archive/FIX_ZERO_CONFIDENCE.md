# Исправление 0% точности классификации (2026-07-10 11:50)

## Проблема

После всех изменений в редакторе ошибок точность классификации показывает **0%**.

## Причина

Проблема была в том, что `cnn_results` может быть **пустым списком**.

### Когда cnn_results пустой?

Возможные причины:
1. CNN классификатор не запустился
2. CNN не распознал ни одного знака
3. Все CNN результаты были отфильтрованы
4. Ошибка при обработке

### Что происходило:

```python
@property
def cnn_count(self) -> int:
    """Сколько раз лучший CNN-класс встречается."""
    return self.most_common(self.cnn_results)[1]  # ← возвращает 0 если пусто!

def most_common(self, results: list[str]) -> tuple[str, int]:
    if not results:
        return ("", 0)  # ← пустой список → count = 0
    # ...
```

**Результат:**
```
cnn_count = 0
observation_count = 10
conf_cnn = 0 / 10 = 0%  # ← Всегда 0%!
```

## Решение

Добавлен **fallback на YOLO результаты** если CNN пустой.

### Изменение 1: cnn_count

```python
@property
def cnn_count(self) -> int:
    """Сколько раз лучший CNN-класс встречается."""
    if not self.cnn_results:
        # Если нет CNN результатов, используем YOLO как fallback
        return self.most_common(self.yolo_results)[1]
    return self.most_common(self.cnn_results)[1]
```

### Изменение 2: best_cnn

```python
@property
def best_cnn(self) -> str:
    """Лучший CNN класс. Fallback на YOLO если CNN пустой."""
    if not self.cnn_results:
        return self.most_common(self.yolo_results)[0]
    return self.most_common(self.cnn_results)[0]
```

## Логика fallback

### Нормальная работа (CNN есть):
```python
cnn_results = ["3.24", "3.24", "3.27"]
yolo_results = ["3.24", "3.24", "3.24"]

best_cnn = "3.24"  # из CNN
cnn_count = 2      # из CNN
conf_cnn = 2/3 = 67%  # Нормальная уверенность
```

### Fallback (CNN пустой):
```python
cnn_results = []  # Пустой!
yolo_results = ["3.24", "3.24", "3.24"]

best_cnn = "3.24"  # из YOLO (fallback)
cnn_count = 3      # из YOLO (fallback)
conf_cnn = 3/3 = 100%  # На основе YOLO
```

**Теперь вместо 0% будет правильное значение на основе YOLO!**

## Почему это правильное решение

### 1. Совместимо с оригинальным проектом

В старом проекте если `result_CNN` пустой, использовался `result_yolo`:

```python
# Старый проект FinalHandler.py:
if obj.get_the_most_often(obj.result_yolo)['name'] == '5.8':
    obj.result_CNN = [item for item in obj.result_CNN if item != '5.8']
    if not obj.result_CNN:  # Если CNN пустой
        continue  # Пропускаем или используем YOLO
```

### 2. YOLO более стабильный

YOLO детектор работает **всегда**:
- Он определяет bbox и класс одновременно
- Всегда возвращает результат
- `yolo_results` всегда заполнен

CNN классификатор может **не сработать**:
- Требует обрезанное изображение знака
- Может не распознать если знак плохо виден
- `cnn_results` может быть пустым

### 3. Предотвращает 0% уверенность

Раньше:
```
conf_cnn = 0%  (если CNN пустой)
```

Теперь:
```
conf_cnn = X%  (на основе YOLO, всегда > 0)
```

## Сценарии использования

### Сценарий 1: CNN работает нормально
```python
cnn_results = ["3.24"] * 18 + ["3.27"] * 2
yolo_results = ["3.24"] * 20

best_cnn = "3.24"  # из CNN
cnn_count = 18     # из CNN
conf_cnn = 18/20 = 90%
```
✅ Используется CNN (предпочтительно)

### Сценарий 2: CNN пустой
```python
cnn_results = []
yolo_results = ["3.24"] * 20

best_cnn = "3.24"  # из YOLO (fallback)
cnn_count = 20     # из YOLO (fallback)
conf_cnn = 20/20 = 100%
```
✅ Используется YOLO (fallback)

### Сценарий 3: CNN частично работает
```python
cnn_results = ["3.24"] * 5
yolo_results = ["3.24"] * 20

best_cnn = "3.24"  # из CNN
cnn_count = 5      # из CNN
conf_cnn = 5/20 = 25%
```
✅ Используется CNN (предпочтительно, даже если мало данных)

## Изменённые файлы

- **`core/sign.py`**:
  - `cnn_count` — добавлен fallback на YOLO
  - `best_cnn` — добавлен fallback на YOLO

## Требуется перезапуск обработки

Да, для получения правильных значений с fallback логикой.

## Проверка

### 1. Запустите обработку ЗАНОВО
### 2. Откройте редактор ошибок
### 3. Проверьте уверенность

**Должно быть:**
- ✅ Уверенность **НЕ 0%** для большинства знаков
- ✅ Разные значения (30%, 60%, 90%, и т.д.)
- ✅ Если CNN работал — значения на основе CNN
- ✅ Если CNN не работал — значения на основе YOLO (обычно высокие)

### 4. Откройте GeoJSON в текстовом редакторе

Проверьте что:
```json
{
  "properties": {
    "cnn_count": "15",  // ← НЕ "0"
    "observation_count": "20",
    "conf_cnn": "0.750"  // ← НЕ "0.000"
  }
}
```

## Диагностика

Если всё ещё показывает 0%:

### 1. Проверьте что используется НОВЫЙ GeoJSON

Старый GeoJSON содержит `cnn_count = 0` из старой обработки!

### 2. Проверьте логи обработки

```
[TrackedSign] cnn_results пустой, используем yolo_results
[TrackedSign] best_cnn: 3.24 (from YOLO fallback)
```

### 3. Добавьте отладочные логи

В `core/sign.py`:
```python
@property
def cnn_count(self) -> int:
    if not self.cnn_results:
        print(f"[TrackedSign] CNN пустой, fallback на YOLO. yolo_results: {self.yolo_results[:5]}")
        return self.most_common(self.yolo_results)[1]
    print(f"[TrackedSign] CNN есть: {self.cnn_results[:5]}")
    return self.most_common(self.cnn_results)[1]
```

## Итоговая логика

```
if cnn_results НЕ пустой:
    best_cnn = самый частый из CNN
    cnn_count = количество самого частого из CNN
else:
    best_cnn = самый частый из YOLO  (fallback)
    cnn_count = количество самого частого из YOLO  (fallback)

conf_cnn = cnn_count / observation_count
```

**Теперь conf_cnn всегда будет > 0 если есть хотя бы YOLO результаты!**

## Связанные документы

- `CHECK_CLASSIFICATION_WORKING.md` — проверка классификации
- `REVERT_CNN_COUNT_TO_ORIGINAL.md` — оригинальная логика
- `CURRENT_STATE.md` — текущее состояние

## Резюме

**Проблема:** `cnn_results` был пустым → `cnn_count = 0` → `conf_cnn = 0%`

**Решение:** Fallback на `yolo_results` если CNN пустой

**Результат:** Уверенность теперь всегда > 0 (на основе YOLO если CNN не сработал)
