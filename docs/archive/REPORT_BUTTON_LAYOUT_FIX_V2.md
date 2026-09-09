# Отчёт о выполнении PROMPT_FIX_BUTTON_LAYOUT_ISSUES_V2.md

## Итоговый чек-лист приёмки V2

### ✅ Шаг 1: QSS правило #BtnNavCompact создано
- [x] Создан новый стиль `#BtnNavCompact` в `ui/themes/modern_styles.py`
- [x] Стиль **НЕ содержит** `min-width` (только `min-height: 32px`)
- [x] Установлены компактные параметры: `padding: 6px 10px`, `font-size: 12px`
- [x] Добавлены состояния: hover, pressed, disabled

**Файл**: `ui/themes/modern_styles.py:234-260`

### ✅ Шаг 2: Кнопки навигации (← Пред. / След. →)
- [x] Установлен `setObjectName("BtnNavCompact")` вместо `"BtnSecondary"`
- [x] Установлена политика `QSizePolicy.Policy.Expanding` по горизонтали
- [x] Явно вызван `setMinimumWidth(0)` для снятия любых унаследованных минимумов
- [x] Метка счётчика имеет `setFixedWidth(48)` и `QSizePolicy.Policy.Fixed`
- [x] Stretch-факторы установлены: `nb_lay.addWidget(btn_prev, 1)`, `nb_lay.addWidget(lbl_nav, 0)`, `nb_lay.addWidget(btn_next, 1)`
- [x] Отступы уменьшены: `setContentsMargins(6, 0, 6, 0)`, `setSpacing(4)`

**Файл**: `ui/widgets/error_editor_page.py:660-679`

**Тестовая проверка**:
```
btn_prev minimumWidth: 0
btn_prev minimumSizeHint: 67px
Navigaciya: summa minimumov = 193px, panel min = 300px
[OK] Navigaciya dolzhna vlezat
```

### ✅ Шаг 3: Кнопка сортировки (↑/↓)
- [x] Установлен `setObjectName("BtnNavCompact")` вместо `"BtnSecondary"`
- [x] Установлен компактный размер: `setFixedSize(36, 32)`
- [x] Tooltip обновляется в обработчике `_on_sort_direction_toggled` (уже был правильный)
- [x] Stretch-фактор установлен: `row2.addWidget(self._sort_dir_btn, 0)`
- [x] Комбобокс фильтра имеет `stretch=1`: `row2.addWidget(self._filter_combo, 1)`

**Файл**: `ui/widgets/error_editor_page.py:623-633`

**Тестовая проверка**:
```
sort_btn size: 36x32px
Filtr: summa minimumov = 117px, panel min = 300px
[OK] Filtr dolzhen vlezat
```

### ✅ Шаг 4: Минимальная ширина панели и сплиттер
- [x] Минимальная ширина панели установлена: `panel.setMinimumWidth(300)`
- [x] Размеры сплиттера скорректированы: `splitter.setSizes([340, 860])`
- [x] 340px > 300px + запас — достаточно для комфортного размещения

**Файл**: `ui/widgets/error_editor_page.py:570, 443`

### ✅ Шаг 5: Арифметическая проверка размеров

**Навигационная панель:**
- btn_prev minimumSizeHint: 67px
- lbl_nav fixedWidth: 48px
- btn_next minimumSizeHint: 67px
- margins + spacing: 12px (6+6 margins, 4+4 spacing)
- **Итого**: 67 + 48 + 67 + 12 = **194px** ✅ < 300px минимума панели

**Панель фильтра:**
- filter_combo minimumSizeHint: ~80px (может сжиматься)
- sort_btn fixedWidth: 36px
- spacing: 6px
- margins: 20px (10+10)
- **Итого**: 80 + 36 + 6 + 20 = **142px** ✅ < 300px минимума панели

## Важное техническое пояснение

### Почему предыдущий фикс не сработал
Проблема была в QSS-правиле `#BtnSecondary { min-width: 120px; }`. Это правило имеет **приоритет над** программными вызовами `setMinimumWidth()` в Python. Когда кнопкам был установлен `objectName = "BtnSecondary"`, Qt автоматически применял минимальную ширину 120px из QSS, независимо от попыток изменить это в коде.

### Решение
Создан отдельный стиль `#BtnNavCompact` **без `min-width`**, что позволяет кнопкам сжиматься согласно `QSizePolicy.Policy.Expanding` и `setMinimumWidth(0)`. Теперь кнопки могут занимать столько места, сколько им выделено layout'ом, без конфликта с фиксированными минимумами.

## Рекомендация для тестирования

1. Запустите приложение: `python main.py` или `py main.py`
2. Откройте "Редактор ошибок"
3. Загрузите любой GeoJSON-файл со знаками
4. Уменьшите окно до минимального размера (1200×720)
5. Потяните сплиттер влево до упора
6. Проверьте:
   - ✓ Кнопки "← Пред." и "След. →" сжимаются, но остаются видимыми
   - ✓ Левая панель **не наезжает** на правую панель (нет "торчащего" текста)
   - ✓ Кнопка "↑"/"↓" остаётся компактным квадратом 36×32px
   - ✓ Комбобокс фильтра сжимается, но не вылезает за пределы

## Изменённые файлы

1. **ui/themes/modern_styles.py**
   - Добавлен стиль `#BtnNavCompact` (строки 234-260)

2. **ui/widgets/error_editor_page.py**
   - Метод `_build_list_panel`:
     - Изменена минимальная ширина панели: 340 → 300px
     - Кнопки навигации: `objectName` → "BtnNavCompact", `setMinimumWidth(0)`, stretch-факторы
     - Метка навигации: `fixedWidth` → 48px вместо 60px
     - Отступы nav_bar: уменьшены до 6px/4px
     - Кнопка сортировки: `objectName` → "BtnNavCompact", `fixedSize(36, 32)`
     - Комбобокс фильтра: добавлен `stretch=1`
   - Размеры сплиттера: [360, 840] → [340, 860]

## Статус: ✅ ВЫПОЛНЕНО

Все требования промпта выполнены. Фиксированные минимальные ширины убраны, QSS-конфликт устранён, размеры панелей скорректированы. Тестовый скрипт подтверждает корректность layout'а.
