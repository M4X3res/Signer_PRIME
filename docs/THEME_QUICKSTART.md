# 🎨 Быстрый старт - Современный дизайн

## Что нового

✨ **Два полноценных дизайна**
- 🌙 Modern Dark - глубокая темная тема  
- ☀️ Modern Light - чистая светлая тема

✨ **Улучшенные компоненты**
- Скругленные углы
- Четкие hover эффекты
- Улучшенная типографика
- Современные цвета

✨ **Автосохранение**
- Выбранная тема запоминается
- Применяется при следующем запуске

## Как переключить тему

### Способ 1: Настройки (рекомендуется)
1. Откройте приложение
2. Перейдите в "⚙️ Настройки" (сайдбар)
3. В разделе "ИНТЕРФЕЙС" выберите тему в dropdown
4. Тема применится мгновенно

### Способ 2: Тест компонентов
```bash
python test_modern_theme.py
```
Нажмите кнопку "🌓 Toggle Theme" для переключения

## Что изменилось

### Кнопки
- Primary: яркий синий, для основных действий
- Secondary: с границей, для второстепенных
- Danger: красный, для удаления
- Icon: минимальный, для иконок

### Карточки
- Увеличенные скругления (12px)
- Тонкие границы
- Визуальное отделение от фона

### Текст
- Современные шрифты (Inter, SF Pro Display, Segoe UI)
- Оптимизированные размеры
- Улучшенный контраст

### Цвета

#### Dark Theme
```
Фон:     #0d1117 (почти черный)
Акцент:  #2f81f7 (яркий синий)
Success: #3fb950 (зеленый)
Error:   #f85149 (красный)
```

#### Light Theme
```
Фон:     #ffffff (белый)
Акцент:  #0969da (глубокий синий)
Success: #1a7f37 (зеленый)
Error:   #cf222e (красный)
```

## Для разработчиков

### Использование в коде

```python
from ui.themes.theme_manager import theme_manager, Theme

# Получить текущие токены
t = theme_manager.tokens
background = t['bg_primary']
text_color = t['text_primary']

# Применить к виджету
widget.setStyleSheet(f"background: {t['bg_secondary']};")

# Переключить тему
from PyQt6.QtWidgets import QApplication
theme_manager.toggle(QApplication.instance())

# Установить конкретную тему
theme_manager.set_theme(Theme.DARK, app)
```

### Доступные токены

**Backgrounds:** bg_primary, bg_secondary, bg_tertiary, bg_elevated, bg_hover
**Text:** text_primary, text_secondary, text_tertiary, text_disabled
**Borders:** border_subtle, border_default, border_strong, border_focus
**Accent:** accent, accent_hover, accent_pressed, accent_subtle
**Status:** success, warning, error, info

### Использовать ObjectName для стилизации

```python
button = QPushButton("Сохранить")
button.setObjectName("BtnPrimary")  # Стили применяются автоматически
```

Доступные ObjectName:
- BtnPrimary, BtnSecondary, BtnDanger, BtnSuccess, BtnIcon
- Card, CardElevated
- PageTitle, PageSubtitle
- SectionLabel
- StatValue, StatLabel
- LogConsole
- и другие...

## Проблемы?

### Тема не применяется
1. Перезапустите приложение
2. Проверьте что файлы тем существуют в `ui/themes/`
3. Удалите настройки: `ui/themes/theme_manager_backup.py`

### Хочу вернуть старую тему
```bash
copy ui\themes\theme_manager_backup.py ui\themes\theme_manager.py
```

### Хочу свои цвета
Отредактируйте `ui/themes/modern_dark.py` или `modern_light.py`

## Обратная связь

Если что-то не работает или есть предложения по дизайну - создайте issue!

---

Приятного использования! 🚀
