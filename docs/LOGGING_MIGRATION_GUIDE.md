# Руководство по замене print() на logging

## Статус

- ✅ **main.py** — настроен `logging.basicConfig()`, все print() заменены на logger
- ✅ **ui/main_window.py** — добавлен `logger = logging.getLogger(__name__)`
- ⏳ **Остальные модули** — требуется замена

## Инструкция для каждого модуля

### 1. Добавить в начало файла (после импортов):

```python
import logging

logger = logging.getLogger(__name__)
```

### 2. Заменить print() согласно контексту:

| Тип сообщения | Замена |
|---------------|--------|
| Ошибки, исключения | `print("Error: ...")` → `logger.error("...")` |
| Предупреждения | `print("Warning: ...")` → `logger.warning("...")` |
| Отладочная информация | `print("[DEBUG] ...")` → `logger.debug("...")` |
| Обычная информация | `print("Запуск...")` → `logger.info("...")` |
| Исключения с traceback | `traceback.print_exc()` → `logger.exception("...")` |

### 3. Примеры замены:

**Было:**
```python
print("[MainWindow] Начинаем сохранение результатов...")
print(f"[MainWindow] Ошибка удаления checkpoint: {e}")
```

**Стало:**
```python
logger.info("Начинаем сохранение результатов...")
logger.error(f"Ошибка удаления checkpoint: {e}")
```

**Было:**
```python
except Exception as e:
    print(f"Ошибка: {e}")
    traceback.print_exc()
```

**Стало:**
```python
except Exception as e:
    logger.exception(f"Ошибка: {e}")  # автоматически добавит traceback
```

## Модули требующие замены (приоритет)

### Высокий приоритет:
1. `ui/main_window.py` — ~20 print()
2. `processing/detector_thread.py` — ~15 print()
3. `processing/processing_controller.py` — ~10 print()
4. `server/map_server.py` — ~20 print()
5. `core/final_handler.py` — ~5 print()

### Средний приоритет:
6. `ui/widgets/error_editor_page.py`
7. `ui/widgets/processing_page.py`
8. `ui/widgets/map_page.py`
9. `core/sign_handler.py`
10. `core/detector.py`

### Низкий приоритет:
11. Остальные модули в `ui/widgets/`
12. `core/turn.py`, `core/gpx_handler.py`

## Преимущества logging над print()

1. **Уровни важности** — можно отфильтровать по важности
2. **Таймстемпы** — автоматически добавляются к каждому сообщению
3. **Имя модуля** — видно откуда сообщение (`[ui.main_window]`)
4. **Запись в файл** — логи сохраняются в `roadscan.log`
5. **Контроль verbosity** — можно отключить отладочные сообщения

## Текущая конфигурация (main.py)

```python
logging.basicConfig(
    level=logging.INFO,  # По умолчанию показывать INFO и выше
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S',
    handlers=[
        logging.StreamHandler(sys.stdout),  # В консоль
        logging.FileHandler('roadscan.log', encoding='utf-8', mode='a')  # В файл
    ]
)
```

## Настройка уровня для разработки

Для включения DEBUG сообщений измените в main.py:

```python
logging.basicConfig(
    level=logging.DEBUG,  # Показывать всё
    # ...
)
```

Или для конкретного модуля:

```python
logging.getLogger('processing.detector_thread').setLevel(logging.DEBUG)
```

## Автоматизация

Используйте скрипт `scripts/analyze_print_usage.py` для анализа:

```bash
python scripts/analyze_print_usage.py
```

Он покажет все print() с рекомендациями по уровню логирования.

## Проверка после замены

1. Запустите приложение
2. Проверьте что логи появляются в консоли
3. Проверьте что создается файл `roadscan.log`
4. Убедитесь что уровни логирования соответствуют важности сообщений
