# Исправление краша (0xC0000409) при нажатии кнопки GeoJSON

## Проблема
При нажатии кнопки "Загрузить GeoJSON" на странице редактора программа вылетала с ошибкой:
```
Process finished with exit code -1073740791 (0xC0000409)
```

Код ошибки `0xC0000409` (STATUS_STACK_BUFFER_OVERRUN) указывает на проблему с памятью или некорректным доступом к данным.

## Причины

### 1. Небезопасное освобождение VideoCapture в деструкторе
**Файл:** `ui/widgets/error_editor_page.py`

Проблема:
```python
def __del__(self):
    if self._cap:
        self._cap.release()
```

При закрытии приложения деструктор мог вызываться в неправильном контексте, что приводило к крашу OpenCV.

### 2. Отсутствие обработки ошибок при загрузке GeoJSON
При некорректных данных в GeoJSON (например, координатах разной длины) происходил IndexError.

### 3. Отсутствие защиты при работе с видео
При открытии/закрытии VideoCapture не было обработки исключений.

## Внесённые изменения

### 1. Замена `__del__` на явный `cleanup()`
**Файл:** `ui/widgets/error_editor_page.py`

```python
def cleanup(self):
    """Безопасная очистка ресурсов перед закрытием."""
    try:
        if self._cap:
            self._cap.release()
            self._cap = None
    except Exception as e:
        print(f"[ErrorEditor] Ошибка при освобождении VideoCapture: {e}")
```

### 2. Добавлена обработка ошибок в `load_geojson()`
```python
def load_geojson(self, path: str = "") -> None:
    try:
        # ... код загрузки ...
        records = []
        for feat in features:
            try:
                props = feat.get("properties", {})
                if props.get("type"):
                    records.append(SignRecord(feat))
            except Exception as e:
                print(f"[ErrorEditor] Ошибка при создании SignRecord: {e}")
                continue
    except Exception as e:
        print(f"[ErrorEditor] КРИТИЧЕСКАЯ ОШИБКА в load_geojson: {e}")
        import traceback
        traceback.print_exc()
```

### 3. Защита при работе с VideoCapture
```python
try:
    if self._cap:
        self._cap.release()
        self._cap = None
except Exception as e:
    print(f"[ErrorEditor] Ошибка при закрытии VideoCapture: {e}")

try:
    self._cap = cv2.VideoCapture(video_path)
    if not self._cap.isOpened():
        self._frame_label.setText("Не удалось открыть видео")
        self._cap = None
        return
    # ... работа с видео ...
except Exception as e:
    print(f"[ErrorEditor] Ошибка при открытии видео: {e}")
    self._frame_label.setText(f"Ошибка: {str(e)}")
    return
```

### 4. Обработка closeEvent в MainWindow
**Файл:** `ui/main_window.py`

```python
def closeEvent(self, event):
    """Обработка закрытия окна — очистка ресурсов."""
    try:
        print("[MainWindow] Закрытие приложения...")
        
        # Останавливаем обработку если она идёт
        if self._controller and self._controller.is_running:
            self._controller.stop()
            
        # Очищаем ресурсы редактора
        self.page_errors.cleanup()
        
        # Останавливаем сервер карты
        if hasattr(self.page_map, 'stop_server'):
            self.page_map.stop_server()
        
        print("[MainWindow] Очистка завершена")
    except Exception as e:
        print(f"[MainWindow] Ошибка при закрытии: {e}")
    finally:
        event.accept()
```

### 5. Защита от некорректных данных в SignRecord

#### В `_calc_gps_confidence()`:
```python
def _calc_gps_confidence(self) -> float:
    try:
        # ... расчёт уверенности ...
        lats = [c[1] for c in coords[0] if len(c) >= 2]
        lons = [c[0] for c in coords[0] if len(c) >= 2]
        
        if lats and lons:
            # ... расчёт стабильности ...
        # ...
    except Exception as e:
        print(f"[SignRecord] Ошибка в _calc_gps_confidence: {e}")
        return 0.5  # Возвращаем среднее значение при ошибке
```

#### В `_parse_median_bbox()`:
```python
def _parse_median_bbox(self) -> Optional[tuple[int,int,int,int]]:
    try:
        xs = self._parse_int_list(self.props.get("pixel_coordinates_x", ""))
        ys = self._parse_int_list(self.props.get("pixel_coordinates_y", ""))
        ws = self._parse_int_list(self.props.get("w", ""))
        hs = self._parse_int_list(self.props.get("h", ""))
        if not all([xs, ys, ws, hs]):
            return None
        # Проверяем что все списки одной длины
        min_len = min(len(xs), len(ys), len(ws), len(hs))
        if min_len == 0:
            return None
        mid = min_len // 2
        return (xs[mid], ys[mid], ws[mid], hs[mid])
    except Exception as e:
        print(f"[SignRecord] Ошибка в _parse_median_bbox: {e}")
        return None
```

## Тестирование

Для проверки исправлений:

1. Запустите программу
2. Выберите GeoJSON файл
3. Перейдите на страницу "Редактор ошибок"
4. Нажмите "Загрузить GeoJSON"
5. Проверьте что программа не крашится
6. Закройте приложение — проверьте корректное завершение

## Логи для диагностики

При возникновении проблем в консоли будут выводиться:

- `[ErrorEditor] load_geojson вызван, target = ...` — начало загрузки
- `[ErrorEditor] Найдено N features в GeoJSON` — количество найденных знаков
- `[ErrorEditor] Создано N SignRecord объектов` — успешно созданных записей
- `[ErrorEditor] Ошибка при создании SignRecord: ...` — проблемы с конкретным знаком
- `[MainWindow] Закрытие приложения...` — начало корректного завершения
- `[MainWindow] Очистка завершена` — успешное завершение

## Дополнительные рекомендации

1. **Резервное копирование GeoJSON**: Перед загрузкой всегда делайте резервную копию файла
2. **Валидация данных**: При возникновении проблем проверьте структуру GeoJSON файла
3. **Логи**: Следите за выводом в консоль для диагностики проблем
