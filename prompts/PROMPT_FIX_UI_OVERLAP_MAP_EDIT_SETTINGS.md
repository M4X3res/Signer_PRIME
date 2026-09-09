# PROMPT: UI-наложение видеоплеера, редактируемое положение знака на карте, сортировка в редакторе ошибок, кнопка "Показать на карте", рекомендуемые настройки

## Контекст

Проект: RoadScanner (Signer PRIME) — PyQt6-приложение для детекции дорожных знаков на видео с
GPS-треком. Карта реализована как Flask-сервер (`server/map_server.py`) + Leaflet-страница
(`templates/map.html`), встроенная в `QWebEngineView` (`ui/widgets/map_page.py`). Редактор ошибок —
нативная Qt-страница (`ui/widgets/error_editor_page.py`). Настройки — `configs/settings.py` +
`ui/widgets/settings_page.py`.

Ниже — пять независимых задач. Делай их по порядку (P0 → P1 → P2 → P3 → P4), после каждой
задачи проверяй критерии приёмки, указанные в конце соответствующего раздела. Не смешивай правки
разных задач в одном логическом блоке кода — это должно быть легко ревьюить по отдельности.

**Общие правила:**
- Пиши на русском (как весь остальной код/комментарии в проекте).
- Не удаляй существующий функционал (диагностику кодеков, полноэкранный режим, popup-окно
  видео, троттлинг превью и т.д.) — только чини и добавляй.
- Не трогай архитектуру Process Pool/Pipeline — они уже отключены (Task E из истории проекта),
  трогать не нужно.
- Логируй новые ошибки через `logger`/`print` в том же стиле, что и рядом лежащий код файла.
- Если добавляешь новые файлы — минимизируй их количество, предпочитай точечные правки.

---

## ЗАДАЧА 1 (P0): Наложение элементов управления видео на карте

### Проблема

На скриншоте видно: полоса прогресса ffmpeg-транскодирования (чёрная полоса вверху) наезжает на
кнопки "📹 Клип" / "⛶ Весь файл", а сама панель "ЗНАК" (детали выбранного знака,
`#detail-section` в `templates/map.html`) выезжает и перекрывает нижнюю часть блока управления
видео — кнопки скорости воспроизведения и переключения режима обрезаны/наслаиваются друг на
друга. Правая колонка (`#right-panel`, ширина 340px, `templates/map.html`) физически не
резиновая: видео-блок (`#video-section`), контролы (`#video-controls`) и деталка знака
(`#detail-section`) все зафиксированы в `flex-direction: column` без прокрутки и без
достаточного `min-height`, поэтому при узком окне/маленьком экране контролы видео "наезжают"
друг на друга, а `#detail-content` показывается поверх/впритык без отступа.

### Что нужно сделать

Файл: `templates/map.html` (CSS + разметка правой панели).

1. **Сделать `#right-panel` вертикально прокручиваемым как единое целое**, если суммарная высота
   контента (видео + видео-контролы + деталка знака) превышает высоту окна. Сейчас `#right-panel`
   — `display:flex; flex-direction:column`, без `overflow-y`. Добавь `overflow-y: auto` на
   `#right-panel` (или на отдельную обёртку, если видео-блок должен быть "залипающим" сверху —
   тогда сделай video-section `position: sticky; top: 0; z-index: 5;` внутри
   прокручиваемого контейнера, а `#detail-section` — обычным блоком под ним).
2. **Зафиксировать `#video-controls` не сжимаемым**: у него уже `flex-wrap: wrap`, но родительский
   `#video-section` не имеет `flex-shrink: 0` явно проверенного на всех дочерних элементах.
   Убедись, что `#video-container`, `<video id="map-video">`, `#video-controls` не сжимаются ниже
   контента (`flex-shrink: 0` на `#video-controls`; фиксированная `height: 180px` на самом
   `<video>` уже есть — не убирай её).
3. **Полоса прогресса ffmpeg-транскодирования** — на скриншоте это нативный HTML5 `<video>` progress
   bar (браузерный), который отображается поверх/над видео при недогруженных данных, ИЛИ это
   `#video-status` с текстом "Подготовка видео...". Проверь оба случая:
   - Если это нативный buffered-индикатор видео — он не должен требовать доп. фикса (это часть
     `<video controls>`), но убедись, что `<video>` не растягивается за пределы `height: 180px` и
     не наслаивается на `#video-controls` снизу (`overflow: hidden` на `#video-container`, если
     его нет).
   - Если `#video-status` показывается **одновременно** с `<video>` и `#video-controls` (сейчас в
     `loadVideoForSign()`/`switchToFullVideo()` `video.style.display` и `videoStatus.style.display`
     переключаются, но не всегда синхронно — проверь, что при показе статуса `video.style.display`
     гарантированно `"none"`, и наоборот), — это первопричина наложения текста статуса на кнопки.
     Исправь: перед каждым `videoStatus.style.display = "block"` явно ставь
     `video.style.display = "none"`, и наоборот.
4. **Отступ между `#video-controls` и `#detail-section`**: добавь `margin-bottom: 4px` (или
   `border-bottom`) на `#video-controls`, чтобы визуально не сливалось с заголовком "ЗНАК" сразу
   под ним.
5. **Кнопка "✕" (закрыть деталь знака)** в `.panel-head-with-close` — проверь, что она не
   перекрывается заголовком "ЗНАК" при длинных названиях знаков (маловероятно, но добавь
   `white-space: nowrap` на `.panel-head-title`, если её нет).
6. Проверь адаптивность кнопок в `#video-controls` на маленькой ширине панели (340px): если ряд
   кнопок скорости (`0.25x…10x`) с `flex-wrap: wrap` переносится на вторую строку — это ожидаемо и
   нормально, просто убедись, что после переноса высота `#video-controls` растёт (не `overflow:
   hidden` с фиксированной высотой), а не обрезает кнопки.

### Критерии приёмки

- При выборе знака с последующей загрузкой клипа: кнопки "📹 Клип"/"⛶ Весь файл", ряд скорости,
  "[ ]" и "+" не наслаиваются друг на друга и не обрезаются ни при каком порядке событий
  (загрузка клипа → показ статуса → повторный выбор другого знака).
- Панель "ЗНАК" (детали) начинается строго под видео-контролами с видимым отступом/разделителем,
  никогда не накладывается на кнопки видео.
- Если высота правой панели не помещается в окно — появляется вертикальный скролл всей панели
  (или как минимум секции деталей), а не визуальное наложение.
- Изменение окна приложения (resize) не ломает раскладку правой панели.

---

## ЗАДАЧА 2 (P1): Возможность двигать (перетаскивать) знак на карте

### Что нужно сделать

Backend (`server/map_server.py`) уже поддерживает обновление координат: `PATCH /api/sign/<id>`
принимает `lat`, `lon`, опционально `azimuth`, пересчитывает вторую точку `LineString` (см.
существующий код обработчика `api_sign_update`). **Не переписывай backend с нуля** — только
проверь, что он действительно принимает `lat`/`lon` (он уже это делает), и используй как есть.

Нужно реализовать **frontend**-часть в `templates/map.html`:

1. **Сделать маркеры знаков перетаскиваемыми.** Сейчас в `renderMarkers()` маркеры создаются как
   `L.marker([sign.lat, sign.lon], { icon }).on("click", ...)` без `draggable`. Добавь:
   ```js
   const m = L.marker([sign.lat, sign.lon], { icon, draggable: true })
     .on("click", () => selectSign(sign.id))
     .on("dragstart", () => { /* опционально: визуальная индикация начала drag */ })
     .on("dragend", (e) => onMarkerDragEnd(sign.id, e.target.getLatLng()));
   ```
   Не делай перетаскиваемыми маркеры внутри кластера просто "на всякий случай" — учти, что
   `markerCluster` (Leaflet.markercluster) может перехватывать drag-события внутри кластера. Если
   `MarkerClusterGroup` мешает перетаскиванию (маркер визуально "прыгает" обратно в кластер),
   сделай выбранный/раскрытый знак временно исключаемым из кластера на время drag: при клике на
   маркер (`selectSign`) можно опционально убирать его из `markerCluster` и добавлять как
   отдельный `L.marker` поверх карты (`m.addTo(map)`) пока он выбран, а при снятии выбора —
   возвращать обратно в кластер. Это самый надёжный способ избежать конфликтов drag+cluster.
2. **Обработчик `onMarkerDragEnd(id, latlng)`**:
   ```js
   async function onMarkerDragEnd(id, latlng) {
     try {
       const r = await fetch(`${API}/sign/${id}`, {
         method: "PATCH",
         headers: { "Content-Type": "application/json" },
         body: JSON.stringify({ lat: latlng.lat, lon: latlng.lng }),
       });
       if (!r.ok) throw new Error(`HTTP ${r.status}`);
       const result = await r.json();
       if (result.error) throw new Error(result.error);

       // Обновляем локальный кэш координат, чтобы renderMarkers()/повторный выбор
       // не откатили маркер на старую позицию
       const idx = signsData.findIndex(s => s.id === id);
       if (idx !== -1) {
         signsData[idx].lat = latlng.lat;
         signsData[idx].lon = latlng.lng;
       }
       toast("Положение знака обновлено", "ok");

       // Если сейчас открыта деталка именно этого знака — не перезагружай видео/данные,
       // просто оставь панель как есть (координаты не отображаются как обязательное поле).
     } catch (err) {
       console.error("Error updating sign position:", err);
       toast("Ошибка сохранения нового положения", "err");
       // Откатываем маркер на прежнее место, раз сервер не подтвердил:
       const orig = signsData.find(s => s.id === id);
       if (orig && markers[id]) {
         markers[id].setLatLng([orig.lat, orig.lon]);
       }
     }
   }
   ```
3. **Курсор и подсказка**: добавь CSS `.sign-marker { cursor: grab; }` и
   `.sign-marker:active { cursor: grabbing; }`, чтобы было визуально понятно, что маркер
   двигается. Добавь всплывающую подсказку (title атрибут на контейнере иконки или
   `marker.bindTooltip("Перетащите, чтобы изменить положение", {direction: "top"})` при наведении,
   если это не будет слишком навязчиво — не обязательный пункт, но желательный.
4. **Обновление после сохранения через существующий SocketIO `sign_updated`**: `PATCH`-обработчик
   на сервере уже вызывает `socketio.emit("sign_updated", {"id": sign_id})`. У клиента уже есть
   обработчик `socket.on("sign_updated", ...)`, который делает полный `fetch(API/signs)` и
   `renderMarkers()`. Это нормально сработает и после drag — просто следи, чтобы не было двойного
   перерисовывания видимого драгнутого маркера "туда-сюда" (мигание). Если мигание будет
   заметно — можно НЕ дожидаться socket-события для собственного изменения (клиент уже обновил
   `signsData` локально в п.2), а игнорировать `sign_updated` для `id`, который только что сам
   же и отправил (например, хранить `lastLocalUpdateId` с коротким TTL ~1с).
5. **Не ломай существующий клик по маркеру** (`selectSign`) — клик должен по-прежнему открывать
   панель деталей, а drag не должен интерпретироваться как клик (Leaflet разделяет эти события
   сам, но протестируй: короткий клик без сдвига должен вызывать `selectSign`, а движение мышью >
   несколько px с зажатой кнопкой — drag).

### Критерии приёмки

- Знак можно перетащить мышью на новое место на карте; после отпускания кнопки мыши позиция
  сохраняется на сервере (проверяется через повторную загрузку страницы — знак остаётся на новом
  месте).
- При ошибке сети/сервера маркер визуально возвращается на исходную позицию и показывается toast
  с ошибкой.
- Обычный клик (без перетаскивания) по-прежнему открывает панель "ЗНАК" с деталями.
- Перетаскивание работает даже если маркер находится внутри кластера (после разворота
  кластера/зума, либо через временное извлечение маркера из кластера на время выбора — см. п.1).

---

## ЗАДАЧА 3 (P2): Сортировка в редакторе ошибок — добавить сортировку по возрастанию/убыванию

### Текущее состояние

Файл: `ui/widgets/error_editor_page.py`. Список знаков (`SignListModel.load()`) всегда
сортируется **только** по возрастанию `total_confidence` (`sorted(records, key=lambda r:
r.total_confidence)`), а `_filter_combo` умеет только фильтровать по диапазонам уверенности ("Все",
"< 30%", "< 40%", "< 50%", "< 70%", ">= 70%") — это фильтр, не сортировка. Пользователю нужна
явная возможность переключить направление сортировки (сейчас всегда "от наименее уверенных к
наиболее" и это неочевидно/не настраивается).

### Что нужно сделать

1. Добавь в топбар списка (`_build_list_panel()`, рядом с `self._filter_combo`) кнопку-переключатель
   направления сортировки, например `QPushButton` с иконкой `↑`/`↓` и `setCheckable(True)`, либо
   компактный `QComboBox` с двумя пунктами: "По возрастанию", "По убыванию" (используй тот же стиль,
   что и `_filter_combo`, включая `connect_combobox_theme_updates`, если решишь сделать комбобоксом).
   Рекомендуется **кнопка-переключатель** — компактнее и требует меньше места в узкой панели.
   Пример:
   ```python
   self._sort_dir_btn = QPushButton("↑ По возрастанию")
   self._sort_dir_btn.setObjectName("BtnSecondary")
   self._sort_dir_btn.setCheckable(True)
   self._sort_dir_btn.setChecked(False)   # False = по возрастанию (текущее поведение по умолчанию)
   self._sort_dir_btn.setFixedHeight(28)
   self._sort_dir_btn.clicked.connect(self._on_sort_direction_toggled)
   fb_lay.addWidget(self._sort_dir_btn)
   ```
2. Добавь состояние `self._sort_ascending: bool = True` в `__init__`.
3. Обработчик:
   ```python
   def _on_sort_direction_toggled(self) -> None:
       self._sort_ascending = not self._sort_dir_btn.isChecked()
       self._sort_dir_btn.setText("↑ По возрастанию" if self._sort_ascending else "↓ По убыванию")
       self._resort_model()

   def _resort_model(self) -> None:
       """Пересортировывает текущие записи без перезагрузки из файла."""
       records = self._model.all_records()
       self._model.load(records, ascending=self._sort_ascending)
       self._apply_filter()  # переприменяем текущий текст/чипы фильтра после пересортировки
   ```
4. Обнови `SignListModel.load()`, чтобы принимать направление:
   ```python
   def load(self, records: list[SignRecord], ascending: bool = True) -> None:
       self.beginResetModel()
       self._records = sorted(
           records, key=lambda r: r.total_confidence, reverse=not ascending
       )
       self.endResetModel()
   ```
   Не удаляй существующие print-логи диагностики внутри `load()` — просто добавь параметр.
5. В `load_geojson()` при первичной загрузке передавай `self._sort_ascending`:
   `self._model.load(records, ascending=self._sort_ascending)`.
6. Убедись, что после переключения направления сортировки текущий выбранный знак (если был
   выбран) остаётся видимым/выбранным в списке, либо (проще) сбрасывай выбор на первый элемент
   отфильтрованного списка — так же, как это уже происходит при первой загрузке.

### Критерии приёмки

- В редакторе ошибок появилась кнопка/переключатель направления сортировки по уверенности,
  отдельно от существующего фильтра по диапазону уверенности (оба контрола работают независимо и
  одновременно).
- Переключение направления мгновенно пересортировывает список без повторного чтения GeoJSON с
  диска.
- Направление сортировки визуально обозначено (текст кнопки/иконка меняется local).
- Существующий фильтр по диапазону уверенности (`_filter_combo`) продолжает работать корректно
  вместе с новой сортировкой.

---

## ЗАДАЧА 4 (P2): Кнопка "Показать на карте" в редакторе ошибок

### Цель

Пользователь просматривает знак в редакторе ошибок (`ui/widgets/error_editor_page.py`) и хочет
сразу перейти на карту (`ui/widgets/map_page.py` → `templates/map.html`), увидеть именно этот
знак выделенным и, если нужно, подвинуть его (см. Задачу 2) или отредактировать тип — без
необходимости искать знак на карте вручную.

### Что нужно сделать

#### 4.1 — Кнопка в редакторе ошибок

Файл: `ui/widgets/error_editor_page.py`, метод `_build_detail_panel()`, рядом с существующими
кнопками действий (`_btn_jump_frame`, `_btn_apply`, `_btn_delete` в `actions` layout).

1. Добавь новую кнопку:
   ```python
   self._btn_show_on_map = QPushButton("🗺  Показать на карте")
   self._btn_show_on_map.setObjectName("BtnSecondary")
   self._btn_show_on_map.setMinimumHeight(36)
   self._btn_show_on_map.setSizePolicy(
       QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
   )
   self._btn_show_on_map.setCursor(Qt.CursorShape.PointingHandCursor)
   self._btn_show_on_map.setEnabled(False)
   self._btn_show_on_map.clicked.connect(self._on_show_on_map)
   actions.addWidget(self._btn_show_on_map)
   ```
   Добавь `self._btn_show_on_map` в тот же цикл, где включаются/выключаются кнопки при показе
   записи (`_show_record`: `for btn in (self._btn_apply, self._btn_delete, self._btn_jump_frame):`
   → добавь туда же `self._btn_show_on_map`).
2. Добавь новый сигнал класса `ErrorEditorPage`:
   ```python
   show_on_map = pyqtSignal(str)  # sign_id
   ```
3. Обработчик:
   ```python
   def _on_show_on_map(self) -> None:
       if not self._current_rec:
           return
       self.show_on_map.emit(self._current_rec.id)
   ```

#### 4.2 — Проброс сигнала через MainWindow

Файл: `ui/main_window.py`.

1. В `__init__`, рядом с уже существующей подпиской
   `self.page_errors.jump_to_frame.connect(self._on_editor_jump)`, добавь:
   ```python
   self.page_errors.show_on_map.connect(self._on_show_sign_on_map)
   ```
2. Новый метод:
   ```python
   def _on_show_sign_on_map(self, sign_id: str) -> None:
       """
       Переключает на вкладку "Карта" и просит веб-страницу карты выбрать
       и отцентрировать конкретный знак по его id.
       """
       self._switch_page("map")
       self.sidebar.set_page("map")
       # Если сервер карты ещё не запущен (обработка не запускалась в этой сессии,
       # но GeoJSON на диске уже есть) — запускаем его.
       if not self.page_map._server_ready:
           self.page_map.start_server()
       self.page_map.focus_sign(sign_id)
   ```
   Учти сценарий: сервер карты может быть ещё не запущен (например, пользователь только открыл
   приложение и сразу зашёл в редактор ошибок на уже готовый GeoJSON, не нажимая
   "Начать обработку"). В этом случае `start_server()` запустит Flask, но потребуется дождаться
   `_on_server_ready` → `_load_map()` перед тем как звать `focus_sign`. Обработай это так: если
   `_server_ready` ещё `False`, сохрани `sign_id` в `self._pending_focus_sign_id` и вызови
   `focus_sign` из `_on_load_finished()` (см. п.4.3) после успешной загрузки страницы.

#### 4.3 — `focus_sign` в `MapPage`

Файл: `ui/widgets/map_page.py`.

1. Добавь метод:
   ```python
   def focus_sign(self, sign_id: str) -> None:
       """
       Просит веб-страницу карты выбрать и отцентрировать знак по id.
       Если страница ещё не загружена — откладывает вызов до loadFinished.
       """
       if self._webview is None or not self._server_ready:
           self._pending_focus_sign_id = sign_id
           return
       self._pending_focus_sign_id = None
       js = f'if (window.focusSignFromEditor) window.focusSignFromEditor("{sign_id}");'
       self._webview.page().runJavaScript(js)
   ```
2. В `_on_load_finished(self, ok: bool)` — после `self._webview.setVisible(True)` — добавь:
   ```python
   pending = getattr(self, "_pending_focus_sign_id", None)
   if pending:
       self._pending_focus_sign_id = None
       self.focus_sign(pending)
   ```
3. Инициализируй `self._pending_focus_sign_id: Optional[str] = None` в `__init__`.

#### 4.4 — JS-функция `focusSignFromEditor` в `map.html`

Файл: `templates/map.html`.

Добавь глобальную функцию (доступную из `window`), которая:
- находит знак в `signsData` по `id`;
- если знак ещё не загружен (`signsData` пуст, потому что данные ещё грузятся) — ждёт `loadAll()`
  через простой поллинг/промис перед выполнением;
- центрирует карту на этот знак (`map.setView([sign.lat, sign.lon], 17)` либо
  `map.flyTo([...], 17)` для плавности);
- если знак находится в кластере — разворачивает кластер до него
  (`markerCluster.zoomToShowLayer(markers[id], () => { markers[id].openPopup?.(); })` — Leaflet
  MarkerCluster предоставляет `zoomToShowLayer` именно для такого сценария);
- вызывает `selectSign(id)`, чтобы открыть панель деталей знака (переиспользуй существующую
  функцию, не дублируй её логику).

Пример:
```js
window.focusSignFromEditor = async function(signId) {
  // Если данные ещё не загружены (карта только что открылась) — ждём.
  if (!signsData || signsData.length === 0) {
    await loadAll();
  }

  const sign = signsData.find(s => s.id === signId);
  if (!sign) {
    toast("Знак не найден на карте (возможно, GeoJSON устарел)", "err");
    return;
  }

  const marker = markers[signId];
  if (marker && markerCluster && markerCluster.hasLayer(marker)) {
    markerCluster.zoomToShowLayer(marker, () => {
      map.setView([sign.lat, sign.lon], Math.max(map.getZoom(), 17));
      selectSign(signId);
    });
  } else {
    map.setView([sign.lat, sign.lon], 17);
    selectSign(signId);
  }
};
```

### Критерии приёмки

- В редакторе ошибок, при выбранном знаке, кнопка "🗺 Показать на карте" активна.
- Клик по ней переключает вкладку на "Карта", запускает сервер карты при необходимости, и
  открывает/выделяет именно тот знак (панель "ЗНАК" открывается с его деталями, карта
  центрируется на нём, при необходимости кластер разворачивается).
- Если сервер карты ещё не был запущен в этой сессии — переход всё равно срабатывает (не
  требует повторного клика).
- Существующая навигация по карте (клик по маркеру вручную, фильтры, live-режим) не сломана.

---

## ЗАДАЧА 5 (P1): Рекомендуемые значения в расширенных настройках + кнопка "Использовать рекомендуемые настройки"

### 5.1 — Обоснованные "оптимальные" значения по умолчанию

Файл: `configs/settings.py`. Пересмотри текущие дефолты `AppSettings` и приведи их к более
безопасным/сбалансированным значениям, ориентируясь на диапазоны, которые уже описаны в
тултипах `ui/widgets/settings_page.py` (там для каждого порога уже есть комментарии "рекомендуется
X-Y") — то есть эти рекомендации уже сформулированы в коде, но дефолты полям `AppSettings` им не
всегда соответствуют. Приведи в соответствие:

| Поле | Текущий дефолт | Рекомендуемое значение | Обоснование (см. тултип в settings_page.py) |
|---|---|---|---|
| `conf_side` | 0.50 | 0.55 | Тултип рекомендует 0.4-0.7; 0.55 — безопасная середина |
| `conf_rube` | 0.70 | 0.70 | Уже в рекомендованном диапазоне 0.6-0.8 — не менять |
| `conf_cnn` | 0.60 | 0.60 | Уже в диапазоне 0.5-0.7 — не менять |
| `iou_threshold` | 0.10 | 0.15 | Тултип рекомендует 0.1-0.2; 0.15 — середина |
| `dedup_radius_track_m` | 8.0 | 10.0 | Тултип рекомендует 8-15м |
| `dedup_radius_final_m` | 20.0 | 20.0 | Уже в диапазоне 15-30 — не менять |
| `dedup_azimuth_deg` | 45.0 | 40.0 | Небольшое ужесточение для меньшего числа ложных мержей |
| `camera_hfov_deg` | 120.0 | 120.0 | Значение по умолчанию для типичных экшн-камер/dashcam — не менять |
| `turn_ray_max_distance_m` | 40.0 | 40.0 | Уже в рекомендованном диапазоне 35-50 — не менять |
| `lane_conf_detect` | 0.65 | 0.65 | Не менять |
| `lane_conf_segment` | 0.65 | 0.65 | Не менять |
| `preview_fps_limit` | 12.0 | 10.0 | Небольшое снижение нагрузки на UI-поток при слабом CPU |
| `ocr_throttle_interval_frames` | 8 | 8 | Не менять |
| `ocr_max_calls_per_sign` | 6 | 6 | Не менять |

**Не меняй** значения, для которых в таблице указано "не менять" — они уже в рекомендованном
диапазоне и трогать их без необходимости не нужно (риск регрессии точности без явного
измеримого выигрыша).

Обнови значения по умолчанию прямо в датаклассе `AppSettings` (поля `conf_side`, `iou_threshold`,
`dedup_radius_track_m`, `dedup_azimuth_deg`, `preview_fps_limit`), чтобы **новые** пользователи
сразу получали рекомендованные значения. Это не то же самое, что кнопка "Использовать
рекомендуемые" из следующего пункта — эта кнопка нужна для **уже существующих** пользователей с
кастомными/несбалансированными значениями, чтобы одним кликом вернуться к рекомендованному
профилю (по сути то же самое, что и новые дефолты, но не требует полного сброса `_reset()`,
который также трогает тему интерфейса, режим UI и т.д. — кнопка "Рекомендуемые" должна касаться
**только** производительности/качества детекции и backend'а, не трогая тему/язык/UI-режим).

### 5.2 — Логика выбора backend (CUDA → ONNX/OpenVINO → PyTorch fallback)

Добавь новый модуль `configs/hardware_recommend.py` с функцией:

```python
"""
configs/hardware_recommend.py
Определение рекомендуемого backend инференса на основе доступного железа.
"""
from __future__ import annotations
import logging
import platform

logger = logging.getLogger(__name__)


def detect_recommended_backend() -> dict:
    """
    Определяет рекомендуемые настройки вычислений на основе доступного железа.

    Returns:
        dict с ключами:
            use_cuda: bool
            cpu_inference_backend: "torch" | "onnx" | "openvino"
            reason: str — человекочитаемое объяснение выбора (для UI/лога)
    """
    # ── Шаг 1: проверяем CUDA ──────────────────────────────────────
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            return {
                "use_cuda": True,
                "cpu_inference_backend": "torch",  # неважно, CUDA использует torch-путь
                "reason": f"Обнаружена CUDA-видеокарта: {gpu_name}. "
                          f"Используется GPU-ускорение (PyTorch + CUDA).",
            }
    except Exception as e:
        logger.warning(f"[hardware_recommend] Ошибка проверки CUDA: {e}")

    # ── Шаг 2: CUDA недоступна — выбираем между OpenVINO и ONNX ────
    cpu_info = _detect_cpu_vendor()

    if cpu_info == "intel":
        # OpenVINO даёт наибольший выигрыш именно на Intel CPU (родная библиотека Intel,
        # использует AVX/AVX512, MKL-DNN оптимизации специфичные для Intel).
        backend = "openvino"
        reason = (
            "CUDA недоступна. Обнаружен процессор Intel — рекомендуется OpenVINO "
            "(наилучшая производительность на Intel CPU)."
        )
    else:
        # AMD, ARM (Apple Silicon под Rosetta/нативно), неизвестный вендор —
        # ONNX Runtime более универсален и одинаково хорошо работает везде,
        # тогда как OpenVINO оптимизирован именно под Intel и может не дать
        # выигрыша (или быть недоступен) на других архитектурах.
        backend = "onnx"
        reason = (
            "CUDA недоступна. Процессор не Intel (или не удалось определить) — "
            "рекомендуется ONNX Runtime (универсальный CPU-бэкенд)."
        )

    return {
        "use_cuda": False,
        "cpu_inference_backend": backend,
        "reason": reason,
    }


def _detect_cpu_vendor() -> str:
    """
    Пытается определить производителя CPU: "intel", "amd" или "unknown".
    Работает кроссплатформенно с graceful fallback.
    """
    try:
        # platform.processor() на Windows обычно возвращает что-то вроде
        # "Intel64 Family 6 Model 158 Stepping 10, GenuineIntel"
        proc_info = platform.processor().lower()
        if "intel" in proc_info or "genuineintel" in proc_info:
            return "intel"
        if "amd" in proc_info or "authenticamd" in proc_info:
            return "amd"
    except Exception:
        pass

    # Fallback для Windows: WMI/реестр через cpuinfo, если platform.processor() пуст
    # (случается на некоторых сборках Python на Windows).
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "cpu", "get", "manufacturer"],
            capture_output=True, text=True, timeout=3,
        )
        output = result.stdout.lower()
        if "intel" in output:
            return "intel"
        if "amd" in output:
            return "amd"
    except Exception:
        pass

    # Дополнительный fallback через py-cpuinfo, если установлен (не обязательная зависимость —
    # оборачиваем в try/except, чтобы не требовать новый пакет).
    try:
        import cpuinfo  # type: ignore
        brand = cpuinfo.get_cpu_info().get("brand_raw", "").lower()
        if "intel" in brand:
            return "intel"
        if "amd" in brand:
            return "amd"
    except Exception:
        pass

    return "unknown"
```

**Не добавляй** `py-cpuinfo` в `requirements.txt` как обязательную зависимость — используй её
только опционально (через `try/except ImportError`), т.к. `platform.processor()` +
`wmic`-фоллбек на Windows покрывают большинство случаев без новых зависимостей.

### 5.3 — Проверка готовности выбранного backend

Прежде чем **применить** рекомендованный `cpu_inference_backend` в UI, проверь его реальную
готовность, переиспользуя уже существующую логику `_check_backend_readiness()` из
`ui/widgets/settings_page.py` (не дублируй её). Если рекомендованный backend (`onnx`/`openvino`)
не готов (пакет не установлен и/или модели не экспортированы) — кнопка "Использовать
рекомендуемые настройки" всё равно должна **выставить** выбор в UI (чтобы пользователь видел
рекомендацию), но сразу показать то же предупреждение, что показывает `_check_backend_readiness()`
при сохранении, поясняющее что нужно сделать (установить пакет / экспортировать модели), и
явно сказать, что до тех пор реально будет использоваться PyTorch (fallback уже реализован в
`_LazyModel._load()`, трогать не нужно).

### 5.4 — Кнопка "Использовать рекомендуемые настройки" в UI

Файл: `ui/widgets/settings_page.py`.

1. Добавь кнопку в группу `compute_group` ("Вычисления (CPU / GPU)"), сразу после кнопки
   "🔍 Проверить GPU" (эта группа уже всегда видима в простом режиме — рекомендованные настройки
   тоже должны быть доступны там же, не только в расширенном режиме):
   ```python
   recommend_btn = QPushButton("✨  Использовать рекомендуемые настройки")
   recommend_btn.setObjectName("BtnSecondary")
   recommend_btn.setMinimumHeight(36)
   recommend_btn.setMinimumWidth(260)
   recommend_btn.setCursor(Qt.CursorShape.PointingHandCursor)
   recommend_btn.clicked.connect(self._apply_recommended_settings)

   recommend_layout = QVBoxLayout()
   recommend_layout.setSpacing(8)
   recommend_layout.addWidget(recommend_btn)

   self._recommend_status_label = QLabel("")
   self._recommend_status_label.setObjectName("SettingsHint")
   self._recommend_status_label.setWordWrap(True)
   recommend_layout.addWidget(self._recommend_status_label)

   recommend_widget = QWidget()
   recommend_widget.setStyleSheet("background: transparent;")
   recommend_widget.setLayout(recommend_layout)

   compute_group.add_row(
       "Рекомендуемые настройки",
       "Автоматически определяет оптимальный backend (CUDA/ONNX/OpenVINO) "
       "и выставляет сбалансированные пороги качества/производительности",
       recommend_widget,
   )
   ```
2. Метод `_apply_recommended_settings`:
   ```python
   def _apply_recommended_settings(self) -> None:
       """
       BLOCK RECOMMEND: применяет рекомендованный backend (на основе железа)
       и сбалансированные пороги качества/производительности к текущему UI
       (без немедленного сохранения — пользователь может передумать и не
       нажать "Сохранить", как и с любыми другими изменениями в форме).
       """
       from configs.hardware_recommend import detect_recommended_backend

       try:
           rec = detect_recommended_backend()

           # ── Backend / CUDA ──────────────────────────────────────
           if hasattr(self, '_cuda_toggle'):
               self._cuda_toggle.set_checked(rec["use_cuda"])
           if hasattr(self, '_cpu_backend_combo'):
               backend_map_rev = {"torch": 0, "onnx": 1, "openvino": 2}
               self._cpu_backend_combo.setCurrentIndex(
                   backend_map_rev.get(rec["cpu_inference_backend"], 0)
               )
               # update_backend_enabled() уже подключён к toggled_state CUDA-тумблера,
               # но сработает только если состояние тумблера реально ИЗМЕНИЛОСЬ —
               # принудительно синхронизируем enabled-состояние комбобокса:
               self._cpu_backend_combo.setEnabled(not rec["use_cuda"])

           # ── Рекомендованные пороги качества/производительности ──
           # (значения см. в PROMPT_FIX_UI_OVERLAP_MAP_EDIT_SETTINGS.md, раздел 5.1)
           if hasattr(self, '_conf_side_spin'):
               self._conf_side_spin.setValue(0.55)
           if hasattr(self, '_iou_spin'):
               self._iou_spin.setValue(0.15)
           if hasattr(self, '_dedup_track_spin'):
               self._dedup_track_spin.setValue(10)
           if hasattr(self, '_dedup_azimuth_spin'):
               self._dedup_azimuth_spin.setValue(40)
           # preview_fps_limit пока не вынесен в UI как отдельный виджет —
           # если такого виджета нет, применяй значение напрямую к self._settings
           # и сохраняй его в _collect_settings() наравне с остальными полями.
           self._settings.preview_fps_limit = 10.0

           # ── Статус для пользователя ──────────────────────────────
           status_lines = [rec["reason"]]

           # Если рекомендован не-PyTorch backend, но он не готов — предупреждаем сразу
           if rec["cpu_inference_backend"] != "torch" and not rec["use_cuda"]:
               readiness_issue = self._get_backend_readiness_issue(rec["cpu_inference_backend"])
               if readiness_issue:
                   status_lines.append(f"⚠️ {readiness_issue}")

           self._recommend_status_label.setText("\n".join(status_lines))
           self._recommend_status_label.setStyleSheet(
               f"color: {theme_manager.tokens['text_secondary']}; font-size: 11px;"
           )

           print(f"[SettingsPage] Рекомендуемые настройки применены: {rec}")

       except Exception as e:
           print(f"[SettingsPage] Ошибка применения рекомендуемых настроек: {e}")
           import traceback
           traceback.print_exc()
           self._recommend_status_label.setText(f"Ошибка определения рекомендаций: {e}")
           self._recommend_status_label.setStyleSheet(
               f"color: {theme_manager.tokens['error']}; font-size: 11px;"
           )
   ```
3. Вынеси проверку готовности backend'а из `_check_backend_readiness()` (которая сейчас и
   проверяет, и сразу показывает `QMessageBox`) в отдельный метод, возвращающий **текст проблемы
   без показа диалога**, чтобы переиспользовать его и в `_apply_recommended_settings`, и в
   существующем `_check_backend_readiness()` (которая теперь просто оборачивает этот текст в
   `QMessageBox`, если он не пустой):
   ```python
   def _get_backend_readiness_issue(self, backend_name: str) -> str:
       """
       Возвращает текстовое описание проблемы готовности backend'а
       ("" если всё готово). Не показывает никаких диалогов —
       чистая проверка для переиспользования в разных местах UI.
       """
       import glob

       issues = []
       try:
           if backend_name == "onnx":
               import onnx       # noqa: F401
               import onnxruntime  # noqa: F401
           elif backend_name == "openvino":
               import openvino  # noqa: F401
       except ImportError as e:
           missing_pkg = str(e).split("'")[1] if "'" in str(e) else "неизвестный пакет"
           issues.append(f"пакет '{missing_pkg}' не установлен")

       exported_files_exist = False
       patterns = {
           "onnx": ["CNN_side/*.onnx", "small_models/*.onnx", "lane_guidance_models/*.onnx"],
           "openvino": [
               "CNN_side/*_openvino_model",
               "small_models/*_openvino_model",
               "lane_guidance_models/*_openvino_model",
           ],
       }.get(backend_name, [])
       for pattern in patterns:
           if glob.glob(pattern):
               exported_files_exist = True
               break
       if not exported_files_exist:
           issues.append(f"модели не экспортированы в формат {backend_name.upper()}")

       if not issues:
           return ""
       return (
           f"Backend '{backend_name.upper()}' выбран, но не готов: {', '.join(issues)}. "
           f"До экспорта моделей/установки пакета обработка будет использовать PyTorch."
       )
   ```
   Обнови существующий `_check_backend_readiness()`, чтобы он вызывал
   `self._get_backend_readiness_issue(backend_name)` вместо дублирования логики проверки пакетов
   и файлов (сохрани его текущее поведение — показ `QMessageBox.warning` при сохранении, просто
   убери дублирующийся код проверки, заменив его вызовом нового метода).

### Критерии приёмки

- В группе "Вычисления (CPU / GPU)" (видна и в Простом, и в Расширенном режиме настроек)
  появилась кнопка "✨ Использовать рекомендуемые настройки".
- На машине с доступной CUDA клик по кнопке включает `use_cuda=True` и показывает название GPU в
  статусе.
- На машине без CUDA клик по кнопке выключает `use_cuda`, выбирает `openvino` на Intel CPU и
  `onnx` на остальных, показывает объяснение выбора.
- Если выбранный CPU-backend не готов (нет пакета/моделей) — статус под кнопкой показывает явное
  предупреждение без блокирующего диалога (диалог остаётся только при нажатии "Сохранить", как и
  раньше).
- Изменения, внесённые кнопкой, не сохраняются автоматически — требуется отдельное нажатие
  "💾 Сохранить" (как и любые другие изменения на странице настроек), кроме случая переключателя
  режима "Простой/Расширенный", который по проекту сохраняется мгновенно (это поведение не
  трогать).
- Значения по умолчанию для новых пользователей (`AppSettings`) обновлены согласно таблице в
  п.5.1.

---

## Порядок сдачи

1. Задача 1 (P0, вёрстка) — можно проверить визуально без обработки видео, просто открыв карту
   с уже готовым GeoJSON и выбрав знак с видео.
2. Задача 2 (P1, drag&drop знака) — тестировать перетаскиванием нескольких знаков, включая знаки
   внутри кластера.
3. Задача 5 (P1, рекомендуемые настройки) — тестировать на машине и с CUDA, и без неё (можно
   временно симулировать отсутствие CUDA, если реальной GPU-машины нет, через мок
   `torch.cuda.is_available()` в юнит-тесте, а не патчить сам код).
4. Задачи 3 и 4 (P2, редактор ошибок) — тестировать связку: отсортировать по убыванию, найти
   слабый знак, нажать "Показать на карте", убедиться что карта открылась на нужном знаке, потом
   подвинуть его (проверка интеграции задач 2+4).

Для каждой задачи добавь минимум один ручной сценарий проверки в комментарии к PR/коммиту, а
если в проекте уже есть `tests/` для похожего функционала (например,
`tests/test_deduplication.py`, `tests/test_onnx_backend.py`) — по возможности добавь unit-тест
для `configs/hardware_recommend.py::detect_recommended_backend()` с моком `torch.cuda.is_available()`
на `True`/`False` и моком `platform.processor()` для проверки ветки Intel/AMD/unknown.
