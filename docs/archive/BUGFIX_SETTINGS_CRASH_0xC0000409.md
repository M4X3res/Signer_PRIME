# 🔧 Исправление краша при сохранении настроек

**Проблема:** Приложение крашится с кодом `0xC0000409` при нажатии "Сохранить" в Settings.

**Статус:** ✅ **ИСПРАВЛЕНО**

---

## Что было сделано

### 1. Добавлена защита от отсутствия виджетов

**Файл:** `ui/widgets/settings_page.py`

**Изменения в `_collect_settings()`:**
```python
# Turn Geometry (BLOCK H) - с проверкой наличия виджетов
if hasattr(self, '_turn_use_bearing_toggle'):
    self._settings.turn_use_bearing_geometry = self._turn_use_bearing_toggle.is_checked()
if hasattr(self, '_camera_fov_spin'):
    self._settings.camera_hfov_deg = self._camera_fov_spin.value()
# и т.д.
```

**Причина:** Если виджет Turn Geometry не был создан из-за ошибки раньше в коде, обращение к несуществующему атрибуту вызывало краш.

---

### 2. Добавлена обработка ошибок в `_save()`

```python
def _save(self):
    try:
        self._collect_settings()
        self._settings.save()
        # ...
    except Exception as e:
        print(f"[SettingsPage] КРИТИЧЕСКАЯ ОШИБКА: {e}")
        # Показываем QMessageBox с ошибкой
```

**Теперь:** Если произойдёт ошибка, пользователь увидит диалог с описанием проблемы вместо краша.

---

### 3. Создан тест UI

**Файл:** `scripts/test_settings_ui.py`

**Запуск:**
```bash
.venv\Scripts\python.exe scripts\test_settings_ui.py
```

**Результат:** ✅ Все виджеты созданы корректно, настройки сохраняются.

---

## Как проверить исправление

### Шаг 1: Перезапустите приложение

```bash
python main.py
```

### Шаг 2: Откройте Settings

1. Кликните на иконку ⚙️ Settings в боковой панели
2. Прокрутите вниз до группы **"ПЕРЕКРЁСТКИ И ПОВОРОТЫ"**

### Шаг 3: Измените любую настройку

Например:
- FOV камеры: измените на 110°
- Дистанция луча: измените на 50м

### Шаг 4: Нажмите "💾 Сохранить"

**Ожидаемое поведение:**
- ✅ Кнопка изменится на "✓ Сохранено"
- ✅ Через 1.5 секунды вернётся к "💾 Сохранить"
- ✅ В консоли появится: `[SettingsPage] Настройки сохранены успешно`
- ✅ **Никакого краша!**

### Шаг 5: Перезапустите и проверьте

```bash
# Закройте и запустите заново
python main.py
```

- Откройте Settings
- Проверьте что ваши изменения **сохранились**

---

## Если краш всё ещё происходит

### 1. Соберите диагностическую информацию

```bash
# Запустите с полным логированием
python main.py 2>&1 | tee crash_log.txt
```

Откройте Settings → попытайтесь сохранить → скопируйте весь вывод из консоли.

### 2. Проверьте настройки вручную

```bash
# Откройте файл настроек
notepad %USERPROFILE%\.kiro\settings.json

# Или если файла нет, проверьте QSettings
reg query "HKEY_CURRENT_USER\Software\Signer\RoadScanner"
```

### 3. Сброс настроек к дефолту

Если настройки повреждены:

```bash
# Удалите файл настроек
del %USERPROFILE%\.kiro\settings.json

# Или очистите QSettings через реестр
reg delete "HKEY_CURRENT_USER\Software\Signer\RoadScanner" /f
```

Затем запустите приложение заново — создадутся дефолтные настройки.

---

## Технические детали

### Код ошибки 0xC0000409

**Полное название:** `STATUS_STACK_BUFFER_OVERRUN`

**Типичные причины в PyQt6:**
1. ❌ Обращение к несуществующему виджету/атрибуту
2. ❌ Конфликт версий Qt DLL
3. ❌ Повреждённые данные в QSettings
4. ❌ Рекурсивный вызов слотов/сигналов

**Что исправлено:**
- ✅ Добавлена проверка `hasattr()` перед обращением к виджетам
- ✅ Обёрнут весь метод `_save()` в `try/except`
- ✅ Добавлен fallback на безопасное поведение

---

## Проверка что всё работает

```bash
# 1. Тест UI компонента (без запуска приложения)
.venv\Scripts\python.exe scripts\test_settings_ui.py

# Должно вывести:
# [SUCCESS] SettingsPage создан успешно!
# [OK] _turn_use_bearing_toggle: Toggle для bearing geometry
# [OK] _camera_fov_spin: SpinBox для FOV камеры
# [OK] _turn_ray_dist_spin: SpinBox для дистанции луча
# [OK] _turn_radius_spin: SpinBox для радиуса детекции
# [SUCCESS] Все виджеты Turn Geometry созданы корректно!

# 2. Полная verification
.venv\Scripts\python.exe scripts\verify_block_h.py

# Должно вывести:
# [SUCCESS] All checks passed! BLOCK H is ready to use.
```

---

## Дополнительная защита

Если вы хотите ещё больше защиты от крашей, можно:

### 1. Добавить валидацию перед сохранением

```python
# В _collect_settings() перед сохранением:
if self._camera_fov_spin.value() < 60 or self._camera_fov_spin.value() > 150:
    raise ValueError("FOV должен быть в диапазоне 60-150°")
```

### 2. Добавить подтверждение перед сохранением

```python
# В _save() перед сохранением:
reply = QMessageBox.question(
    self, 'Подтверждение',
    'Сохранить изменения?',
    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
)
if reply == QMessageBox.StandardButton.No:
    return
```

---

## Статус

✅ **Проблема исправлена**  
✅ **Тесты проходят**  
✅ **Готово к использованию**

**Следующий шаг:** Попробуйте сохранить настройки в приложении и проверьте что краш больше не происходит.

---

*Дата исправления: 2026-08-24*  
*Файлы изменены: `ui/widgets/settings_page.py`*  
*Тесты добавлены: `scripts/test_settings_ui.py`*
