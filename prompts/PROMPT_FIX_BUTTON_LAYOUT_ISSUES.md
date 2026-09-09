# Промпт для AI-агента: исправить некрасивые/обрезанные кнопки в 4 местах UI

Скопируй весь текст ниже и отдай его агенту (Kiro/Claude Code/аналогу) целиком.

---

## Контекст

Проект: RoadScanner (Signer PRIME) — PyQt6-приложение + встроенная веб-страница карты
(Flask + `templates/map.html`, отображается через `QWebEngineView`).

Есть 4 конкретные проблемы с кнопками, подтверждённые скриншотами. Нужно исправить
**именно эти 4 места**, не трогая остальной UI, если явно не требуется для фикса.

---

## БАГ 1 — Некрасивые/неровные кнопки видеоплеера на карте

**Файл:** `templates/map.html`, блок `#video-controls` (внутри `#video-section`).

**Текущий код (для ориентира, могло немного отличаться после промежуточных правок):**
```html
<div id="video-controls" style="padding: 6px; background: var(--bg2); border-top: 1px solid var(--border);">
  <!-- Строка 1 -->
  <div style="display: flex; gap: 4px; margin-bottom: 4px;">
    <button class="tb-btn accent" id="btn-clip-mode" onclick="switchToClipMode()" title="Короткий клип">📹</button>
    <button class="tb-btn" id="btn-full-mode" onclick="switchToFullVideo()" title="Полное видео">⛶</button>
    <div style="width: 1px; background: var(--border); margin: 0 4px;"></div>
    <button class="tb-btn" onclick="setPlaybackSpeed(0.5)" title="0.5x">0.5x</button>
    <button class="tb-btn accent" id="btn-speed-1" onclick="setPlaybackSpeed(1)" title="1x">1x</button>
    <button class="tb-btn" onclick="setPlaybackSpeed(2)" title="2x">2x</button>
    <button class="tb-btn" onclick="setPlaybackSpeed(5)" title="5x">5x</button>
  </div>
  <!-- Строка 2 -->
  <div style="display: flex; gap: 4px;">
    <button class="tb-btn" onclick="setPlaybackSpeed(0.25)" title="0.25x">0.25x</button>
    <button class="tb-btn" onclick="setPlaybackSpeed(10)" title="10x">10x</button>
    <div style="width: 1px; background: var(--border); margin: 0 4px;"></div>
    <button class="tb-btn" onclick="toggleFullscreen()" title="Полный экран">⛶</button>
    <button class="tb-btn" onclick="openVideoWindow()" title="В окне">⧉</button>
  </div>
</div>
```

**Что не так (см. скриншот 1):** кнопки разной ширины, разной высоты, "залипают" друг к
другу без единого визуального ритма, синяя (`.accent`) кнопка режима клипа выглядит
инородно рядом с иконочной кнопкой `⛶`, вертикальный разделитель `<div style="width:1px">`
делает верстку рваной. Всё выглядит неаккуратно и не поместилось по высоте/ширине панели
(`#right-panel` имеет `width: 340px`, см. CSS в том же файле).

**Что нужно сделать:**
1. Переверстать `#video-controls` в **единую сетку** (используй CSS Grid или flex-wrap),
   а не в 2 руками сверстанные строки с разными наборами кнопок.
2. Разделить кнопки на 3 логические группы с явными подписями-секциями или хотя бы
   визуальными группами (через `gap` и общий контейнер с `border-radius`/фоном), НЕ через
   `<div style="width:1px">` разделители:
   - Группа "Источник": 📹 Клип / ⛶ Полное видео (переключатель режима — 2 кнопки одинаковой
     ширины, растянутые на 50/50 всей доступной ширины).
   - Группа "Скорость": 0.25x, 0.5x, 1x, 2x, 5x, 10x — **шесть одинаковых по размеру
     кнопок-пилюль** в одну строку (используй `flex: 1 1 0` на каждой, чтобы они делили
     ширину контейнера поровну, а не были каждая своей ширины). Активная скорость
     подсвечивается классом `.accent`.
   - Группа "Окно": ⛶ Полный экран / ⧉ В отдельном окне — тоже 2 кнопки 50/50.
3. Все кнопки в `#video-controls` должны иметь **одинаковую высоту** (например
   `min-height: 30px`) и одинаковый вертикальный `padding`, независимо от того, это
   иконка или текст "0.25x".
4. Добавь `border-radius` и небольшой `gap: 6px` между группами (используй пустое
   пространство/`margin-top`, а не `<div style="width:1px">`).
5. Проверь, что при ширине панели 340px (см. `#right-panel { width: 340px; }`) все кнопки
   помещаются без переноса текста и без горизонтального скролла.
6. Не меняй `id` кнопок и имена JS-функций (`switchToClipMode`, `switchToFullVideo`,
   `setPlaybackSpeed`, `toggleFullscreen`, `openVideoWindow`, `btn-clip-mode`,
   `btn-full-mode`, `btn-speed-1`) — на них завязана логика в `<script>` в конце файла.

---

## БАГ 2 — Кнопки "↺ Перезагрузить" / "⬡ В браузере" на странице карты чуть-чуть не влезают

**Файл:** `ui/widgets/map_page.py`, класс `MapPage.__init__`, блок топбара (`self._topbar`).

**Текущий код:**
```python
self._reload_btn = QPushButton("↺  Перезагрузить")
self._reload_btn.setObjectName("BtnSecondary")
self._reload_btn.setFixedWidth(180)
self._reload_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
...
self._open_btn = QPushButton("⬡  В браузере")
self._open_btn.setObjectName("BtnSecondary")
self._open_btn.setFixedWidth(180)
self._open_btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
```

QSS для `#BtnSecondary` (файл `ui/themes/modern_styles.py`) задаёт
`padding: 10px 16px; font-size: 14px; min-width: 120px; min-height: 36px;`.

**Что не так (см. скриншот 2):** при текущем шрифте/паддинге текст кнопок обрезается
буквально на пару пикселей справа — `setFixedWidth(180)` слишком тесен для реального
рендера текста + иконки + внутреннего padding в 16px с каждой стороны.

**Что нужно сделать:**
1. Замени `setFixedWidth(180)` на автоматический расчёт ширины по содержимому:
   ```python
   from PyQt6.QtWidgets import QSizePolicy
   self._reload_btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
   self._reload_btn.setMinimumWidth(190)  # с запасом
   ```
   Сделай то же самое для `self._open_btn`. Ширину подбери так, чтобы
   `button.fontMetrics().horizontalAdvance(button.text())` + `padding*2` + запас
   ~12-16px точно помещались (ориентировочно 190–200px вместо 180px хватит,
   но подбери и проверь визуально, что текст не обрезается ни в тёмной, ни в
   светлой теме, и ни на Windows, ни при увеличенном системном DPI).
2. Альтернативный (предпочтительный) вариант: вообще убрать `setFixedWidth`/
   `QSizePolicy.Policy.Fixed` и оставить только `setMinimumWidth(...)` с
   `QSizePolicy.Policy.Minimum`, чтобы Qt сам считал нужную ширину под текст и
   шрифт — это надёжнее любого захардкоженного числа.
3. Убедись, что после фикса обе кнопки по-прежнему выровнены по высоте
   (`minimumHeight`/QSS `min-height: 36px` не трогать) и одинаковой высоты между собой.

---

## БАГ 3 — В "Редакторе ошибок" обрезается поле поиска и не влезает кнопка сортировки

**Файл:** `ui/widgets/error_editor_page.py`, метод `ErrorEditorPage._build_list_panel`.

**Текущий код (панель фильтров списка знаков):**
```python
panel.setMinimumWidth(280)
...
self._search = QLineEdit()
self._search.setPlaceholderText("Поиск по типу…")
self._search.setObjectName("FilePathBox")
self._search.setMinimumHeight(32)
fb_lay.addWidget(self._search)

self._filter_combo = QComboBox()
self._filter_combo.setObjectName("FilterChipCombo")
self._filter_combo.addItems(["Все", "< 30%", "< 40%", "< 50%", "< 70%", ">= 70%"])
fb_lay.addWidget(self._filter_combo)

self._sort_dir_btn = QPushButton("↑ По возрастанию")
self._sort_dir_btn.setObjectName("BtnSecondary")
self._sort_dir_btn.setCheckable(True)
self._sort_dir_btn.setFixedHeight(28)
self._sort_dir_btn.setMinimumWidth(140)
fb_lay.addWidget(self._sort_dir_btn)
```
Все три виджета (`_search`, `_filter_combo`, `_sort_dir_btn`) лежат **в одном
горизонтальном ряду** `fb_lay = QHBoxLayout(filter_bar)` внутри панели с
`setMinimumWidth(280)` — при такой узкой ширине панели три элемента физически
не помещаются: см. скриншот 3, где поле поиска "По..." обрезано до пары букв, а
кнопка "↑ По возрастанию" тоже не помещается целиком.

**Что нужно сделать:**
1. Перестрой `filter_bar` в **два ряда** вместо одного:
   - Ряд 1: `self._search` (растянут на всю ширину, `QSizePolicy.Expanding`).
   - Ряд 2: `self._filter_combo` + `self._sort_dir_btn`, оба с
     `QSizePolicy.Policy.Expanding` по горизонтали и одинаковым `stretch`, чтобы
     делить ширину панели 50/50, ИЛИ сократи текст кнопки сортировки до иконки
     (например `↑`/`↓` с тултипом "По возрастанию"/"По убыванию" через
     `setToolTip(...)`), чтобы она гарантированно помещалась в одну строку с
     комбобоксом даже при узкой панели.
2. Увеличь высоту `filter_bar` (`setMinimumHeight`/`setMaximumHeight`), так как
   теперь в ней два ряда вместо одного — сейчас `setMinimumHeight(44)` /
   `setMaximumHeight(52)`, нужно расширить примерно вдвое (например 78–86px) с
   учётом двух рядов по ~32-34px + внутренние отступы.
3. Убери жёсткий `self._sort_dir_btn.setMinimumWidth(140)`, если переходишь на
   вариант с иконкой — вместо этого используй `setFixedWidth` под размер иконки
   (~36-40px) или оставь `Expanding`, если сохраняешь текстовый вариант во втором ряду.
4. Не меняй `self._filter_combo.currentTextChanged` / `self._search.textChanged`
   коннекты и логику `_apply_filter()` — трогай только layout/размеры виджетов.
5. Проверь, что при `splitter.setSizes([320, 880])` (см. `ErrorEditorPage.__init__`)
   всё содержимое левой панели помещается без горизонтальной обрезки текста ни в
   поле поиска, ни в кнопке сортировки.

---

## БАГ 4 — Кнопки "← Пред." / "След. →" в редакторе ошибок не влезают

**Файл:** `ui/widgets/error_editor_page.py`, метод `ErrorEditorPage._build_list_panel`,
блок `nav_bar` (навигация внизу списка знаков).

**Текущий код:**
```python
self._btn_prev = QPushButton("← Пред.")
self._btn_next = QPushButton("След. →")
for btn in (self._btn_prev, self._btn_next):
    btn.setObjectName("BtnSecondary")
    btn.setFixedWidth(130)
    btn.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
...
self._lbl_nav = QLabel("—")
self._lbl_nav.setObjectName("EditorNavLabel")
self._lbl_nav.setAlignment(Qt.AlignmentFlag.AlignCenter)

nb_lay.addWidget(self._btn_prev)
nb_lay.addWidget(self._lbl_nav)
nb_lay.addWidget(self._btn_next)
```
`nav_bar` лежит в той же левой панели с `panel.setMinimumWidth(280)`, а
`nb_lay.setContentsMargins(8, 0, 8, 0)` + `nb_lay.setSpacing(6)`. Простой расчёт:
`130 + 130 + spacing*2 + margins(16) + label` уже превышает 280px — отсюда
обрезание/съезжание кнопок на скриншоте 4.

**Что нужно сделать:**
1. Уменьши `setFixedWidth(130)` до значения, которое реально влезает в
   `panel.minimumWidth()` вместе с меткой `self._lbl_nav` и отступами — либо
   уменьши текст кнопок до "← Пред" / "След →" без точки, либо уменьши фиксированную
   ширину примерно до 100–110px **и одновременно** увеличь
   `panel.setMinimumWidth(280)` до значения, при котором весь ряд гарантированно
   помещается (посчитай: 2×110 + 6×2(spacing) + 16(margins) + ширина `_lbl_nav`
   (дай ей `setMinimumWidth(50)`) ⇒ панели нужно минимум ~340px).
2. Предпочтительный вариант: замени `QSizePolicy.Policy.Fixed` на
   `QSizePolicy.Policy.Expanding` для обеих кнопок и дай `_lbl_nav` фиксированную
   узкую ширину по центру (`setFixedWidth(60)`), чтобы кнопки сами растягивались и
   занимали всё оставшееся место без обрезки — это устойчивее к изменению ширины
   сплиттера пользователем.
3. Если увеличиваешь `panel.setMinimumWidth(...)`, синхронно проверь
   `splitter.setSizes([320, 880])` в `__init__` — при необходимости увеличь первое
   число, чтобы сумма не пересчитывалась Qt в ущерб левой панели при первом
   открытии страницы.
4. Не трогай сигналы `self._btn_prev.clicked.connect(self._go_prev)` /
   `self._btn_next.clicked.connect(self._go_next)`.

---

## Общие требования ко всем 4 фиксам

- Не ломай существующую функциональность (клики, id, имена функций, коннекты сигналов).
- Изменения должны одинаково корректно выглядеть **и в тёмной, и в светлой теме**
  (`ui/themes/modern_dark.py` / `ui/themes/modern_light.py` — токены не трогать, только
  геометрию/layout).
- После правок нужно **вручную** (или через скриншот-тест, если он есть в проекте)
  убедиться, что при стандартном размере окна 1400×860 (см. `MainWindow.resize(1400, 860)`)
  ни один текст ни на одной из 4 кнопочных панелей не обрезается и не съезжает.
- Не переписывай архитектуру страниц целиком — правь только геометрию/CSS/layout в
  указанных блоках.
- Если для бага 3/4 меняешь `panel.setMinimumWidth(...)` — обнови это значение только
  один раз и в одном месте, не дублируй магические числа.

## Итоговый чек-лист приёмки

- [ ] Скрин 1 (видеоплеер на карте): кнопки визуально ровные, сгруппированы в 3
      логических блока, ни одна не обрезана, между группами явный отступ, а не тонкая
      серая полоска.
- [ ] Скрин 2: текст "↺ Перезагрузить" и "⬡ В браузере" помещается в кнопки полностью,
      без обрезки последней буквы/иконки.
- [ ] Скрин 3: поле поиска показывает полный placeholder "Поиск по типу…" при пустом
      значении и не обрезано; кнопка сортировки и комбобокс "Все" оба видны полностью.
- [ ] Скрин 4: "← Пред." / "След. →" видны полностью вместе со счётчиком "N / M"
      посередине, ничего не обрезано и не съехало за пределы панели.
