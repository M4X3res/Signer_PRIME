# Промпт: Исправление обрезанных кнопок, комбобоксов и переименование в "Signer v2"

Скопируй этот файл как `prompts/PROMPT_FIX_UI_BUTTONS_AND_COMBOBOXES.md` и запусти агента с ним
(например: `kiro chat "Выполни prompts/PROMPT_FIX_UI_BUTTONS_AND_COMBOBOXES.md"`).

---

## Контекст

По скриншотам обнаружены визуальные баги в PyQt6-приложении (RoadScanner/Signer):

1. Кнопки "📹 Клип" / "⛶ Весь файл" в видеоплеере на карте (`templates/map.html`) —
   текст обрезается по правому краю кнопки.
2. Кнопки "↺ Перезагрузить" / "⬡ В браузере" на топбаре карты (`ui/widgets/map_page.py`) —
   текст обрезается.
3. Кнопки "↑ Загрузить GeoJSON" / "✓ Сохранить" на топбаре редактора ошибок
   (`ui/widgets/error_editor_page.py`) — текст обрезается, особенно "Загрузить GeoJSON".
4. Кнопки "← Пред." / "След. →" в редакторе ошибок (`ui/widgets/error_editor_page.py`) —
   текст обрезается/переносится криво.
5. Фильтр-комбобокс "Все" в редакторе ошибок (`ui/widgets/error_editor_page.py`,
   `self._filter_combo`) — рядом с текстом уродливый серый прямоугольник (артефакт
   отрисовки `::drop-down` в Fusion-стиле).
6. Кнопка "Сохранить" на странице настроек (`ui/widgets/settings_page.py`, объект
   `BtnPrimary`) — в disabled-состоянии текст "Сохранить" невидим (белый/светлый текст
   на светлом фоне). Причина: в `ui/themes/modern_styles.py` в правиле
   `#BtnPrimary:disabled` используется свойство `opacity: 0.6;`, которое **не
   поддерживается Qt Style Sheets** для этого контекста и может ломать остальные
   объявления в блоке, из-за чего реальный цвет текста не применяется.
7. Выпадающий список "Бэкенд CPU-инференса" (PyTorch / ONNX Runtime / OpenVINO) в
   настройках выглядит плоско и не современно — нужно освежить дизайн попапа
   `QComboBox QAbstractItemView` в `ui/themes/modern_styles.py`.

Плюс общие пожелания:
- Переименовать название программы на **"Signer"**, добавить **"v2"** / **"v2.0"** везде,
  где сейчас может остаться "RoadScanner".
- Точечно модернизировать UI (без изменения архитектуры), если видишь другие явные
  огрехи такого же рода (обрезанные подписи, конфликт `setFixedWidth()` с
  `min-width` в QSS и т.п.).

---

## Причина обрезания текста на кнопках (важно понять перед правкой)

В `ui/themes/modern_styles.py` глобально заданы:

```css
#BtnPrimary, #BtnSecondary {
    padding: 10px 24px;
    min-width: 120px;
    min-height: 36px;
}
```

А в коде виджетов многие кнопки жёстко фиксируются через `setFixedWidth(100)`,
`setFixedWidth(150)`, `setFixedWidth(180)` — то есть **меньше**, чем
`min-width: 120px` из QSS, либо ровно на грани с учётом padding 24px с каждой
стороны (48px только на padding). Из-за этого конфликта Qt обрезает текст по
границе виджета вместо того, чтобы кнопка выросла под содержимое.

Правильное решение — исправить в **двух местах одновременно**:
1. Уменьшить горизонтальный padding в общем QSS (освобождает место для текста
   во всех уже выставленных `setFixedWidth`).
2. Увеличить те `setFixedWidth(...)`, что заведомо теснее контента.

---

## Задача 1 — `ui/themes/modern_styles.py`: базовый QSS кнопок

Найди блоки `#BtnPrimary` и `#BtnSecondary` (в функции `build_modern_qss`). Замени
горизонтальный padding с `10px 24px` на `10px 16px` в обоих правилах:

```diff
 #BtnPrimary {
     background-color: {t['accent']};
     color: {t['text_on_accent']};
     border: none;
     border-radius: 8px;
-    padding: 10px 24px;
+    padding: 10px 16px;
     font-size: 14px;
     font-weight: 600;
     min-width: 120px;
     min-height: 36px;
     letter-spacing: 0.2px;
 }
```

```diff
 #BtnSecondary {
     background-color: transparent;
     color: {t['text_primary']};
     border: 1.5px solid {t['border_default']};
     border-radius: 8px;
-    padding: 10px 24px;
+    padding: 10px 16px;
     font-size: 14px;
     font-weight: 500;
     min-width: 120px;
     min-height: 36px;
 }
```

### Задача 1b — исправить невидимый текст на disabled-кнопке (Скрин 6)

В том же файле найди:

```css
#BtnPrimary:disabled {
    background-color: {t['bg_hover']};
    color: {t['text_primary']};
    border: 1.5px solid {t['border_strong']};
    opacity: 0.6;
}
```

`opacity` не является валидным свойством Qt Style Sheets для этого контекста и должен
быть убран. Замени на:

```css
#BtnPrimary:disabled {
    background-color: {t['bg_hover']};
    color: {t['text_secondary']};
    border: 1.5px solid {t['border_strong']};
}
```

Проверь после правки: на странице «Настройки» нажми «💾 Сохранить» — во время
disabled-состояния (и в варианте «✓ Сохранено») подпись должна быть чётко читаема в
обеих темах (светлой и тёмной).

### Задача 1c — модернизировать попап комбобокса (Скрин 7)

Найди блок `QComboBox QAbstractItemView` и `QComboBox QAbstractItemView::item*` в
`build_modern_qss`. Замени на более современный вид: чуть больше скругление,
лёгкая тень через контрастную рамку, аккуратные отступы, плавный hover:

```css
QComboBox QAbstractItemView {
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    selection-background-color: {t['accent_subtle']};
    selection-color: {t['accent']};
    color: {t['text_primary']};
    border-radius: 10px;
    padding: 6px;
    outline: none;
}

QComboBox QAbstractItemView::item {
    min-height: 34px;
    padding: 7px 14px;
    border-radius: 8px;
    margin: 1px 0px;
}

QComboBox QAbstractItemView::item:hover {
    background-color: {t['bg_hover']};
}

QComboBox QAbstractItemView::item:selected {
    background-color: {t['accent_subtle']};
    color: {t['accent']};
    font-weight: 600;
}
```

Также сузь зону стрелки выпадающего списка, чтобы сама кнопка комбобокса выглядела
компактнее и современнее — в блоке `QComboBox::drop-down` уменьши `width` с `30px`
до `22px`:

```diff
 QComboBox::drop-down {
     border: none;
     background: transparent;
-    width: 30px;
+    width: 22px;
     padding-right: 8px;
 }
```

---

## Задача 2 — `ui/widgets/map_page.py` (Скрин 2)

Найди в конструкторе `MapPage`:

```python
self._reload_btn.setFixedWidth(150)  # ЗАДАЧА 4: Одинаковая ширина для пары
```
и
```python
self._open_btn.setFixedWidth(150)  # ЗАДАЧА 4: Одинаковая ширина для пары
```

Увеличь оба значения до `180`, чтобы текст "↺  Перезагрузить" и "⬡  В браузере" помещался
даже при уменьшенном padding из Задачи 1:

```diff
-        self._reload_btn.setFixedWidth(150)  # ЗАДАЧА 4: Одинаковая ширина для пары
+        self._reload_btn.setFixedWidth(180)  # Увеличено — текст не помещался (см. UI-фикс кнопок)
```
```diff
-        self._open_btn.setFixedWidth(150)  # ЗАДАЧА 4: Одинаковая ширина для пары
+        self._open_btn.setFixedWidth(180)  # Увеличено — текст не помещался (см. UI-фикс кнопок)
```

---

## Задача 3 — `ui/widgets/error_editor_page.py`

### 3a. Кнопки "Загрузить GeoJSON" / "Сохранить" (Скрин 3)

Найди в `_build_topbar()`:

```python
self._btn_load.setFixedWidth(180)  # ЗАДАЧА 4: Одинаковая ширина для пары
...
self._btn_save.setFixedWidth(180)  # ЗАДАЧА 4: Одинаковая ширина для пары
```

Увеличь оба до `220` (текст "↑  Загрузить GeoJSON" самый длинный в паре и определяет
минимально нужную ширину):

```diff
-        self._btn_load.setFixedWidth(180)  # ЗАДАЧА 4: Одинаковая ширина для пары
+        self._btn_load.setFixedWidth(220)  # Увеличено — "Загрузить GeoJSON" обрезался
```
```diff
-        self._btn_save.setFixedWidth(180)  # ЗАДАЧА 4: Одинаковая ширина для пары
+        self._btn_save.setFixedWidth(220)  # Увеличено — держим пару одинаковой ширины
```

### 3b. Кнопки "← Пред." / "След. →" (Скрин 4)

Найди в `_build_list_panel()`:

```python
self._btn_prev = QPushButton("← Пред.")
self._btn_next = QPushButton("След. →")
for btn in (self._btn_prev, self._btn_next):
    btn.setObjectName("BtnSecondary")
    # ЗАДАЧА 4: Убираем setMinimumHeight - используем QSS (36px)
    btn.setFixedWidth(100)  # ЗАДАЧА 4: Одинаковая ширина для пары
```

`100px` меньше, чем `min-width: 120px` в QSS для `#BtnSecondary` — это и есть источник
конфликта/обрезания. Увеличь до `130`:

```diff
-    btn.setFixedWidth(100)  # ЗАДАЧА 4: Одинаковая ширина для пары
+    btn.setFixedWidth(130)  # Увеличено — 100px было < min-width(120px) из QSS, текст резался
```

### 3c. Фильтр-комбобокс "Все" — убрать уродливый прямоугольник (Скрин 5)

Найди определение `self._filter_combo` в `_build_list_panel()`:

```python
self._filter_combo = QComboBox()
self._filter_combo.addItems([
    "Все", "< 30%", "< 40%", "< 50%", "< 70%", ">= 70%"
])
self._filter_combo.setStyleSheet(
    f"color: {t['text_secondary']}; font-size: 11px; background: {t['bg_tertiary']};"
    f"border: 1px solid {t['border_subtle']}; border-radius: 4px; padding: 4px 8px;"
)
```

Дай комбобоксу `objectName` и убери у него отрисовку блока стрелки (subcontrol
`::drop-down`), чтобы получился чистый «чип» без серого прямоугольника, плюс сделай
его визуально приятнее (скруглённая «таблетка»):

```diff
 self._filter_combo = QComboBox()
+self._filter_combo.setObjectName("FilterChipCombo")
 self._filter_combo.addItems([
     "Все", "< 30%", "< 40%", "< 50%", "< 70%", ">= 70%"
 ])
 self._filter_combo.setStyleSheet(
-    f"color: {t['text_secondary']}; font-size: 11px; background: {t['bg_tertiary']};"
-    f"border: 1px solid {t['border_subtle']}; border-radius: 4px; padding: 4px 8px;"
+    f"QComboBox#FilterChipCombo {{"
+    f"  color: {t['text_secondary']}; font-size: 11px; background: {t['bg_tertiary']};"
+    f"  border: 1px solid {t['border_subtle']}; border-radius: 12px; padding: 5px 12px;"
+    f"}}"
+    f"QComboBox#FilterChipCombo:hover {{ border-color: {t['border_strong']}; }}"
+    f"QComboBox#FilterChipCombo::drop-down {{ width: 0px; border: none; }}"
+    f"QComboBox#FilterChipCombo::down-arrow {{ width: 0px; height: 0px; image: none; }}"
 )
```

Есть и второе место с идентичным блоком — метод `_restyle_list_panel()`
(вызывается при смене темы). Примени тот же diff там же, чтобы стиль не терялся
после переключения темы:

```python
def _restyle_list_panel(self) -> None:
    ...
    self._filter_combo.setStyleSheet(
        f"color: {t['text_secondary']}; font-size: 11px; background: {t['bg_tertiary']};"
        f"border: 1px solid {t['border_subtle']}; border-radius: 4px; padding: 4px 8px;"
    )
```
→ замени этот вызов `setStyleSheet` на такой же `QComboBox#FilterChipCombo {...}` блок,
как выше.

(Клик по комбобоксу по-прежнему открывает список — Qt открывает попап по клику в любом
месте `QComboBox`, а не только по стрелке, так что функциональность не теряется.)

---

## Задача 4 — `templates/map.html` (Скрин 1)

Найди в блоке видео-контролов (внутри `#video-controls`):

```html
<div style="display: flex; gap: 4px; flex: 1; min-width: 200px;">
  <button class="tb-btn accent" id="btn-clip-mode" onclick="switchToClipMode()" title="Короткий клип вокруг знака" style="flex: 1; font-size: 9px;">📹 Клип</button>
  <button class="tb-btn" id="btn-full-mode" onclick="switchToFullVideo()" title="Полное видео (может быть медленным)" style="flex: 1; font-size: 9px;">⛶ Весь файл</button>
</div>
```

`min-width: 200px` слишком мало для двух кнопок с таким текстом и padding
(`.tb-btn` даёт `padding: 4px 10px`) — правая кнопка "⛶ Весь файл" обрезается. Увеличь
`min-width` контейнера и слегка увеличь читаемость шрифта:

```diff
-<div style="display: flex; gap: 4px; flex: 1; min-width: 200px;">
-  <button class="tb-btn accent" id="btn-clip-mode" onclick="switchToClipMode()" title="Короткий клип вокруг знака" style="flex: 1; font-size: 9px;">📹 Клип</button>
-  <button class="tb-btn" id="btn-full-mode" onclick="switchToFullVideo()" title="Полное видео (может быть медленным)" style="flex: 1; font-size: 9px;">⛶ Весь файл</button>
-</div>
+<div style="display: flex; gap: 4px; flex: 1; min-width: 240px;">
+  <button class="tb-btn accent" id="btn-clip-mode" onclick="switchToClipMode()" title="Короткий клип вокруг знака" style="flex: 1; font-size: 10px; padding: 4px 6px; white-space: nowrap;">📹 Клип</button>
+  <button class="tb-btn" id="btn-full-mode" onclick="switchToFullVideo()" title="Полное видео (может быть медленным)" style="flex: 1; font-size: 10px; padding: 4px 6px; white-space: nowrap;">⛶ Весь файл</button>
+</div>
```

Оставшийся в этой же строке блок со скоростями воспроизведения (`0.25x … 10x`) трогать
не нужно.

---

## Задача 5 — Переименование "RoadScanner" → "Signer v2"

Найди все пользовательские (не лог/комментарий) строки с "RoadScanner" и замени.

### 5a. `ui/main_window.py`

```diff
-        self.setWindowTitle("RoadScanner")
+        self.setWindowTitle("Signer v2")
```

и в классе `StatusBar`:

```diff
-        self._right = QLabel("RoadScanner v2.0")
+        self._right = QLabel("Signer v2.0")
```

### 5b. Проверка остального

`ui/widgets/sidebar.py` уже показывает `"Signer"` и `"v2.0"` в логотипе сайдбара —
трогать не нужно, но проверь при ревью, что нигде рядом не осталось "RoadScanner".

Сделай `grep -rn "RoadScanner"` по `ui/`, `templates/`, `main.py` — в **пользовательских
строках** (заголовки окон, лейблы, HTML `<title>`) везде должно быть "Signer"/"Signer v2"/
"Signer v2.0". В комментариях кода, логах (`logger.info(...)`) и в путях/именах файлов
(`roadscan.log`, `RoadScanner`/`Signer` в QSettings organization/app name) — **не трогать**,
это внутренние идентификаторы, не связанные с текстом на экране. Обрати особое внимание
на `templates/map.html`, там есть `<title>RoadScanner — Карта</title>` — замени на
`<title>Signer v2 — Карта</title>`.

---

## Общая инструкция по модернизации (по желанию, не критично)

Если видишь другие похожие места, где `setFixedWidth(N)` в Qt-виджете меньше, чем
`min-width` соответствующего objectName-стиля в `modern_styles.py` — это тот же баг,
почини его так же (подними `N` минимум до значения из QSS + запас на текст).

Не трогай архитектуру, только визуальные исправления из этого промпта.

---

## Критерии приёмки

- [ ] Кнопки "📹 Клип" / "⛶ Весь файл" на карте — текст виден полностью, ничего не обрезано.
- [ ] Кнопки "↺ Перезагрузить" / "⬡ В браузере" на карте — текст виден полностью.
- [ ] Кнопки "↑ Загрузить GeoJSON" / "✓ Сохранить" в редакторе ошибок — текст виден полностью.
- [ ] Кнопки "← Пред." / "След. →" в редакторе ошибок — текст виден полностью, без переносов.
- [ ] Фильтр "Все" в редакторе ошибок — либо аккуратная "таблетка" без стрелки, либо
      современно оформленная стрелка; уродливого серого прямоугольника нет.
- [ ] Кнопка "Сохранить" в Настройках — подпись читаема в обычном и disabled состоянии,
      в обеих темах (светлой и тёмной).
- [ ] Выпадающий список "Бэкенд CPU-инференса" (и остальные комбобоксы) — попап выглядит
      современно: скруглённые углы, аккуратные отступы, понятный hover/selected.
- [ ] Заголовок окна приложения и статус-бар показывают "Signer v2" / "Signer v2.0"
      вместо "RoadScanner".
- [ ] `<title>` страницы карты — "Signer v2 — Карта".
- [ ] Ничего из функциональности (обработка видео, карта, редактор) не сломано —
      это чисто визуальные/стилевые правки.
