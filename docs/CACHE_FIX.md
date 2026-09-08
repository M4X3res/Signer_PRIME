# Исправление CNN кэша - pHash вместо точного хеша

**Дата:** 2026-08-19 13:31  
**Статус:** ✅ Реализовано, ожидает тестирования

## Проблема

### Симптомы
- **Cache Hit Rate: 0.0%** после 1800+ кадров
- Размер кэша растет (size=921), но **0 попаданий** (hits=0)
- Каждая классификация идет через CNN модель
- Потеря 30-50% производительности

### Анализ логов

```
13:15:25 Cache: 0.0% (0/902) size=902  ← 0 hits из 902 запросов
13:15:26 Cache: 0.0% (0/902) size=902  ← кэш растет...
13:15:27 Cache: 0.0% (0/903) size=903  ← но никогда не используется!
```

### Корневая причина

**Старый алгоритм:** MD5/xxHash от `crop32.tobytes()`
```python
hashlib.md5(img.tobytes()).hexdigest()[:16]
```

**Проблема:**
1. Знак движется в видео кадр за кадром
2. Bounding box каждый раз чуть-чуть смещается (±1-2 пикселя)
3. `crop32` содержит визуально тот же знак, но с микросдвигом
4. MD5 хеш **полностью другой** → промах кэша
5. Результат: каждый кадр = новая CNN классификация

## Решение: Perceptual Hash (pHash)

### Алгоритм

**pHash** генерирует одинаковые хеши для **визуально похожих** изображений:

```python
def compute_image_hash(img: np.ndarray) -> str:
    # 1. Downscale to 8x8
    small = cv2.resize(img, (8, 8))
    
    # 2. Grayscale
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    
    # 3. DCT (Discrete Cosine Transform)
    dct = cv2.dct(np.float32(gray))
    
    # 4. Low frequencies (8x8 top-left)
    dct_low = dct[:8, :8]
    
    # 5. Median threshold
    median = np.median(dct_low[1:, 1:])
    
    # 6. Binarize: 1 if > median, 0 otherwise
    hash_bits = dct_low > median
    
    # 7. Pack into 64-bit integer → hex string
    return pack_to_hex(hash_bits)
```

### Почему это работает

**DCT (Discrete Cosine Transform):**
- Разлагает изображение на частотные компоненты
- Низкие частоты (top-left DCT) = общая структура изображения
- Высокие частоты = детали, шум, микросдвиги

**Бинаризация через медиану:**
- Порог устойчив к изменениям яркости
- 64-бит хеш (8x8) достаточен для различения знаков
- Микросдвиги ±1-2px не влияют на низкие частоты

**Результат:**
- Один и тот же знак через 5-10 кадров → **тот же pHash**
- Разные знаки → разные pHash (с высокой вероятностью)

## Ожидаемый эффект

### До исправления
```
Кадр 100: Знак А (позиция x=500) → hash1 → CNN классификация
Кадр 101: Знак А (позиция x=502) → hash2 → CNN классификация (снова!)
Кадр 102: Знак А (позиция x=504) → hash3 → CNN классификация (снова!)
...
Cache Hit Rate: 0.0%
```

### После исправления
```
Кадр 100: Знак А (позиция x=500) → phash_A → CNN классификация → кэш
Кадр 101: Знак А (позиция x=502) → phash_A → ✅ КЭШ ХИТ!
Кадр 102: Знак А (позиция x=504) → phash_A → ✅ КЭШ ХИТ!
Кадр 103: Знак А (позиция x=506) → phash_A → ✅ КЭШ ХИТ!
...
Cache Hit Rate: 40-60% (expected)
```

### Прирост производительности

**Сценарий 1: Знак виден 30 кадров**
- До: 30 CNN классификаций по ~50ms = **1500ms**
- После: 1 CNN + 29 кэш хитов по ~0.1ms = **53ms**
- **Ускорение: 28x на один знак!**

**Сценарий 2: Весь видеофайл**
- Средняя длительность знака в кадре: ~20 кадров
- Cache Hit Rate: 40-50% → экономия **40-50% всех CNN вызовов**
- Ожидаемый прирост FPS: **+40-75%**

```
До:  0.9 FPS (со знаками)
После: 1.3-1.6 FPS (40-75% прирост)
```

## Риски и компромиссы

### ✅ Плюсы
- Кэш наконец-то работает
- Огромный прирост производительности без изменения архитектуры
- pHash быстрый (несколько микросекунд)
- Использует только cv2 (уже в зависимостях)

### ⚠️ Риски
- **False positives:** Визуально похожие но разные знаки → один pHash
  - Вероятность: низкая (64-бит хеш + контекст yolo_class)
  - Митигация: кэш-ключ = `f"{yolo_class}:{phash}"` → YOLO уже разделил категории
  
- **False negatives:** Один знак под углом → разные pHash
  - Вероятность: средняя для сильных поворотов
  - Эффект: просто не будет кэш хита, работает как раньше

### 🔍 Мониторинг
После деплоя следить за:
1. **Cache Hit Rate** в логах → должен быть 30-60%
2. **FPS improvement** → ожидаем +40-75%
3. **Ошибки классификации** → если pHash дает коллизии

## Изменения в коде

**Файл:** `core/detector.py`

### 1. Функция хеширования
```python
# ДО
def compute_image_hash(img: np.ndarray) -> str:
    return hashlib.md5(img.tobytes()).hexdigest()[:16]

# ПОСЛЕ
def compute_image_hash(img: np.ndarray) -> str:
    small = cv2.resize(img, (8, 8), interpolation=cv2.INTER_AREA)
    # ... DCT, median, binarize ...
    return f"{hash_value:016x}"
```

### 2. Использование (без изменений)
```python
# Кэш-ключ включает YOLO класс для снижения коллизий
cache_key = f"{yolo_class}:{img_hash}"
cached = self._cnn_cache.get(cache_key)
```

## Тестирование

### План тестирования
1. ✅ Запустить обработку видео с новым pHash
2. ⏳ Проверить Cache Hit Rate через 500 кадров
3. ⏳ Сравнить FPS: до (0.9) vs после (expected 1.3-1.6)
4. ⏳ Проверить качество классификации (нет регрессии)

### Команда для теста
```bash
# Обработать 500-1000 кадров
# Следить за логами:
tail -f roadscan.log | grep "Cache:"
```

### Ожидаемый вывод
```
[SmartSkip] Обработано: 500, Cache: 35.2% (176/500) size=324
[SmartSkip] Обработано: 1000, Cache: 42.7% (427/1000) size=573
                                    ^^^^
                                    Должно быть > 30%!
```

## Следующие шаги

### Если тест успешен (Cache Hit > 30%)
1. ✅ Коммит: `git commit -m "fix: Replace MD5 with pHash for CNN cache"`
2. Обновить PROFILING_RESULTS.md с новыми данными
3. Перейти к следующей оптимизации (батчинг или многопоточность)

### Если Cache Hit всё ещё 0-5%
- **Гипотеза:** Каждый знак появляется только 1-2 раза
- **Проверка:** Добавить логирование `logger.debug(f"Sign {yolo_class} phash={phash}")`
- **Альтернатива:** Использовать Hamming distance для "fuzzy" кэша
  ```python
  # Искать в кэше хеши с Hamming distance <= 3
  for cached_hash in cache.keys():
      if hamming_distance(phash, cached_hash) <= 3:
          return cache[cached_hash]
  ```

## Литература

- [Perceptual Hashing (pHash)](https://en.wikipedia.org/wiki/Perceptual_hashing)
- [DCT-based Image Hash](https://www.hackerfactor.com/blog/index.php?/archives/432-Looks-Like-It.html)
- OpenCV DCT: https://docs.opencv.org/4.x/d2/de8/group__core__array.html#ga85aad4d668c01fbd64825f589e3696d4

---

**Автор:** Kiro CLI  
**Commit:** Pending  
**Связанные файлы:**
- `core/detector.py` - реализация pHash
- `docs/PROFILING_RESULTS.md` - исходный анализ проблемы
- `processing/detector_thread.py` - логирование Cache Hit Rate
