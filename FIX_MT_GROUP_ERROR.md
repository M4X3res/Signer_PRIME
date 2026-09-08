# Исправление: NameError в settings_page.py

## Проблема
```
NameError: name 'mt_group' is not defined. Did you mean: 'ui_group'?
```

## Причина
В **Task E** группа "Многопоточность" (`mt_group`) была корректно удалена из кода, но осталась ссылка на неё в двух местах:

1. **Список `_advanced_only_widgets`** (строка 754) — содержал `mt_group` среди скрываемых групп
2. **Метод `_import_settings()`** (строки 1434-1437) — использовал `self._processing_mode_combo` и `self._workers_spin` без проверки `hasattr`

## Исправления

### 1. Удалена ссылка на `mt_group` из `_advanced_only_widgets`

**Было:**
```python
self._advanced_only_widgets = [
    ui_group,
    proc_group,
    gps_group,
    mt_group,              # ❌ Ошибка: группа не существует
    lane_group,
    ...
]
```

**Стало:**
```python
self._advanced_only_widgets = [
    ui_group,
    proc_group,
    gps_group,
    # mt_group УДАЛЕНА (Task E) - группа "Многопоточность" больше не существует
    lane_group,
    ...
]
```

### 2. Добавлены `hasattr` проверки в `_import_settings()`

**Было:**
```python
proc_mode = settings_dict.get("processing_mode", "single_thread")
mode_idx = {"single_thread": 0, "pipeline": 1, "process_pool": 2}.get(proc_mode, 0)
self._processing_mode_combo.setCurrentIndex(mode_idx)  # ❌ Виджет не существует
self._workers_spin.setValue(settings_dict.get("process_pool_workers", 0))  # ❌
```

**Стало:**
```python
# Task E: processing_mode, workers, ocr_* виджеты УДАЛЕНЫ (пропускаем с hasattr)
if hasattr(self, '_processing_mode_combo'):
    proc_mode = settings_dict.get("processing_mode", "single_thread")
    mode_idx = {"single_thread": 0, "pipeline": 1, "process_pool": 2}.get(proc_mode, 0)
    self._processing_mode_combo.setCurrentIndex(mode_idx)

if hasattr(self, '_workers_spin'):
    self._workers_spin.setValue(settings_dict.get("process_pool_workers", 0))
```

## Результат
✅ Приложение запускается без ошибок  
✅ Старые сохранённые настройки (с `processing_mode`/`process_pool_workers`) загружаются корректно  
✅ Новые настройки сохраняются без этих полей  

## Файлы
- `ui/widgets/settings_page.py` — исправлены 2 проблемных места

## Тестирование
```bash
# Активируйте venv
venv\Scripts\activate

# Запустите приложение
python main.py
# → Должно открыться без ошибок
# → Settings → проверить, что нет групп "Режим обработки" и "Многопоточность"
```
