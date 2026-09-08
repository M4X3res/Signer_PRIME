# 🎨 Modern Theme System - README

## Быстрый старт

### 1. Запустите приложение
```bash
python main.py
```

### 2. Переключите тему
Откройте **Настройки** → **Интерфейс** → Выберите **Тёмная** или **Светлая**

### 3. Протестируйте компоненты
```bash
python test_modern_theme.py
```

## Примеры использования

### Базовое использование токенов

```python
from ui.themes.theme_manager import theme_manager

# Получить токены текущей темы
tokens = theme_manager.tokens

# Применить к виджету
widget.setStyleSheet(f"""
    background-color: {tokens['bg_secondary']};
    color: {tokens['text_primary']};
    border: 1px solid {tokens['border_default']};
    border-radius: 8px;
""")
```

### Использование objectName (рекомендуется)

```python
from PyQt6.QtWidgets import QPushButton

# Создать кнопку
button = QPushButton("Сохранить")
button.setObjectName("BtnPrimary")  # Стили применятся автоматически

# Доступные ObjectName:
# BtnPrimary, BtnSecondary, BtnDanger, BtnSuccess, BtnIcon
# Card, CardElevated
# PageTitle, PageSubtitle
# StatValue, StatLabel
# и другие...
```

### Программное переключение темы

```python
from PyQt6.QtWidgets import QApplication
from ui.themes.theme_manager import theme_manager, Theme

app = QApplication.instance()

# Переключить Dark ⇄ Light
theme_manager.toggle(app)

# Установить конкретную тему
theme_manager.set_theme(Theme.DARK, app)
theme_manager.set_theme(Theme.LIGHT, app)

# Проверить текущую тему
if theme_manager.is_dark:
    print("Используется темная тема")
```

### Подписка на изменения темы

```python
from ui.themes.theme_manager import theme_manager

class MyWidget(QWidget):
    def __init__(self):
        super().__init__()
        
        # Подписаться на изменения
        theme_manager.theme_changed.connect(self.on_theme_changed)
    
    def on_theme_changed(self, theme_name: str):
        print(f"Тема изменена на: {theme_name}")
        # Обновить кастомные элементы
        self.update_custom_graphics()
```

### Создание стилизованной карточки

```python
from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from ui.themes.theme_manager import theme_manager

card = QWidget()
card.setObjectName("Card")  # Автоматическая стилизация

layout = QVBoxLayout(card)
layout.setContentsMargins(16, 14, 16, 14)

# Заголовок
title = QLabel("СТАТИСТИКА")
title.setObjectName("CardTitle")
layout.addWidget(title)

# Значение
value = QLabel("1,234")
value.setObjectName("StatValue")
layout.addWidget(value)

# Подпись
label = QLabel("КАДРОВ ОБРАБОТАНО")
label.setObjectName("StatLabel")
layout.addWidget(label)
```

### Условная стилизация по теме

```python
from ui.themes.theme_manager import theme_manager

tokens = theme_manager.tokens

if theme_manager.is_dark:
    # Темная тема - используем светлые иконки
    icon_path = "icons/light/icon.png"
else:
    # Светлая тема - используем темные иконки
    icon_path = "icons/dark/icon.png"

# Динамическая стилизация
widget.setStyleSheet(f"""
    QLabel {{
        color: {tokens['text_primary']};
        background: {tokens['bg_secondary']};
    }}
""")
```

### Создание кастомных статусных элементов

```python
from PyQt6.QtWidgets import QLabel
from ui.themes.theme_manager import theme_manager

def create_status_badge(text: str, status: str = "success"):
    """
    Создает badge со статусом
    status: 'success', 'warning', 'error', 'info'
    """
    tokens = theme_manager.tokens
    
    colors = {
        "success": (tokens['success'], tokens.get('success_bg', tokens['bg_tertiary'])),
        "warning": (tokens['warning'], tokens.get('warning_bg', tokens['bg_tertiary'])),
        "error": (tokens['error'], tokens.get('error_bg', tokens['bg_tertiary'])),
        "info": (tokens['info'], tokens.get('info_bg', tokens['bg_tertiary'])),
    }
    
    color, bg = colors.get(status, colors['info'])
    
    badge = QLabel(text)
    badge.setStyleSheet(f"""
        background-color: {bg};
        color: {color};
        border-radius: 12px;
        padding: 4px 12px;
        font-size: 11px;
        font-weight: 600;
    """)
    
    return badge

# Использование
success_badge = create_status_badge("Готово", "success")
error_badge = create_status_badge("Ошибка", "error")
```

## Доступные токены

### Backgrounds
```python
bg_primary      # Основной фон
bg_secondary    # Карточки, панели
bg_tertiary     # Инпуты, вторичные элементы
bg_elevated     # Elevated элементы (dropdown, modal)
bg_hover        # Hover состояние
bg_active       # Active/pressed состояние
bg_accent_subtle # Тонкий акцентный фон
```

### Text
```python
text_primary    # Основной текст
text_secondary  # Вторичный текст
text_tertiary   # Третичный текст (hints)
text_disabled   # Отключенный текст
text_link       # Ссылки
text_on_accent  # Текст на акценте (обычно белый)
```

### Borders
```python
border_subtle   # Едва заметные границы
border_default  # Стандартные границы
border_strong   # Выделенные границы
border_focus    # Граница в фокусе
```

### Accent
```python
accent          # Основной акцент
accent_hover    # Hover акцент
accent_pressed  # Pressed акцент
accent_subtle   # Тонкий акцентный фон
accent_muted    # Приглушенный акцент
```

### Status
```python
success         # Зеленый (успех)
success_hover   # Hover зеленый
success_bg      # Фон успеха

warning         # Оранжевый (предупреждение)
warning_hover   # Hover оранжевый
warning_bg      # Фон предупреждения

error           # Красный (ошибка)
error_hover     # Hover красный
error_bg        # Фон ошибки

info            # Синий (инфо)
info_hover      # Hover синий
info_bg         # Фон инфо
```

### Special
```python
shadow_sm       # Маленькая тень
shadow_md       # Средняя тень
shadow_lg       # Большая тень
shadow_accent   # Тень с акцентом
```

## Цветовые значения

### Dark Theme
```python
"bg_primary":    "#0d1117"  # Глубокий темный
"accent":        "#2f81f7"  # Яркий синий
"success":       "#3fb950"  # Зеленый
"error":         "#f85149"  # Красный
"warning":       "#d29922"  # Оранжевый
```

### Light Theme
```python
"bg_primary":    "#ffffff"  # Белый
"accent":        "#0969da"  # Глубокий синий
"success":       "#1a7f37"  # Зеленый
"error":         "#cf222e"  # Красный
"warning":       "#9a6700"  # Оранжевый
```

## Советы

### ✅ Хорошие практики

```python
# ✅ Используйте токены
t = theme_manager.tokens
widget.setStyleSheet(f"color: {t['text_primary']};")

# ✅ Используйте objectName
button.setObjectName("BtnPrimary")

# ✅ Слушайте изменения темы
theme_manager.theme_changed.connect(self.update_ui)
```

### ❌ Избегайте

```python
# ❌ Хардкод цветов
widget.setStyleSheet("color: #f0f0f0;")

# ❌ Прямая стилизация без токенов
widget.setStyleSheet("background: #1c1c1c;")

# ❌ Игнорирование изменений темы
# (виджет не обновится при переключении)
```

## Файлы

```
ui/themes/
├── modern_dark.py              # Токены темной темы
├── modern_light.py             # Токены светлой темы
├── modern_styles.py            # QSS генератор
├── theme_manager.py            # Менеджер тем
└── theme_manager_backup.py     # Backup старой версии

test_modern_theme.py            # Тестовое приложение
show_colors.py                  # Визуализация палитры
MODERN_DESIGN.md                # Полная документация
THEME_QUICKSTART.md             # Быстрый старт
CHANGELOG_DESIGN.md             # Список изменений
```

## Проблемы?

### Тема не применяется
1. Убедитесь что файлы тем существуют
2. Перезапустите приложение
3. Проверьте консоль на ошибки импорта

### Хочу вернуть старую тему
```bash
copy ui\themes\theme_manager_backup.py ui\themes\theme_manager.py
```

### Хочу свои цвета
Отредактируйте `ui/themes/modern_dark.py` или `modern_light.py`

---

**Документация**: MODERN_DESIGN.md  
**Быстрый старт**: THEME_QUICKSTART.md  
**Changelog**: CHANGELOG_DESIGN.md
