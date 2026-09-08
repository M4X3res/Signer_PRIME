import os

from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QDoubleSpinBox,
    QFrame, QCheckBox, QComboBox, QScrollArea,
    QSizePolicy, QSpacerItem, QLineEdit
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.themes.theme_manager import theme_manager, Theme
from ui.widgets.utils import connect_combobox_theme_updates  # ЗАДАЧА 1
from configs import config


def _separator():
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")

    def _update_sep_color(_theme=None):
        sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")

    theme_manager.theme_changed.connect(_update_sep_color)
    return sep


class SettingsRow(QWidget):
    """Одна строка настройки: лейбл + описание | контрол."""
    def __init__(self, label: str, hint: str, control: QWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setMinimumHeight(56)  # Минимальная высота вместо фиксированной

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl = QLabel(label)
        lbl.setObjectName("SettingsLabel")
        lbl.setWordWrap(True)  # Перенос текста

        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("SettingsHint")
        hint_lbl.setWordWrap(True)  # Перенос текста

        text_col.addWidget(lbl)
        text_col.addWidget(hint_lbl)

        layout.addLayout(text_col)
        layout.addStretch()
        layout.addWidget(control)


class SettingsGroup(QWidget):
    """Группа настроек с заголовком и строками."""
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self.setObjectName("SettingsGroup")

        self._root = QVBoxLayout(self)
        self._root.setContentsMargins(0, 14, 0, 8)
        self._root.setSpacing(0)

        title_lbl = QLabel(title.upper())
        title_lbl.setObjectName("CardTitle")
        title_lbl.setContentsMargins(20, 0, 20, 10)
        self._root.addWidget(title_lbl)
        self._root.addWidget(_separator())
        self._first = True

    def add_row(self, label: str, hint: str, control: QWidget):
        if not self._first:
            self._root.addWidget(_separator())
        self._first = False
        self._root.addWidget(SettingsRow(label, hint, control))
        return self


class ToggleButton(QPushButton):
    """Минималистичный переключатель вместо QCheckBox."""
    toggled_state = pyqtSignal(bool)

    def __init__(self, initial: bool = False, parent=None):
        super().__init__(parent)
        self._checked = initial
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(self._toggle)
        self._repaint()

    def _toggle(self):
        self._checked = not self._checked
        self._repaint()
        self.toggled_state.emit(self._checked)

    def _repaint(self):
        t = theme_manager.tokens
        if self._checked:
            bg = t["accent"]
            circle_pos = "right: 2px;"
        else:
            bg = t["bg_hover"]
            circle_pos = "left: 2px;"
        self.setStyleSheet(
            f"QPushButton {{"
            f"  background: {bg}; border: none;"
            f"  border-radius: 12px;"
            f"}}"
        )
        self.setText("●" if self._checked else "○")

    def is_checked(self) -> bool:
        return self._checked

    def set_checked(self, v: bool):
        self._checked = v
        self._repaint()


class SettingsPage(QWidget):
    theme_changed = pyqtSignal(str)
    settings_changed = pyqtSignal()  # Новый сигнал для уведомления об изменениях

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")
        
        try:
            # Загружаем настройки
            from configs.settings import get_app_settings
            self._settings = get_app_settings()
            print("[SettingsPage] Настройки загружены успешно")
        except Exception as e:
            print(f"[SettingsPage] ОШИБКА загрузки настроек: {e}")
            # Создаём дефолтные настройки
            from configs.settings import AppSettings
            self._settings = AppSettings()
            print("[SettingsPage] Используются дефолтные настройки")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(32, 28, 32, 28)
        outer.setSpacing(0)

        # ── Header ─────────────────────────────────────────────
        title = QLabel("Настройки")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Конфигурация приложения")
        subtitle.setObjectName("PageSubtitle")
        outer.addWidget(title)
        outer.addSpacing(4)
        outer.addWidget(subtitle)
        outer.addSpacing(24)
        
        # ── Переключатель Простой/Расширенный (BLOCK SETTINGS-UX) ───
        mode_row = QHBoxLayout()
        mode_row.setSpacing(6)

        self._btn_mode_simple = QPushButton("Простой режим")
        self._btn_mode_advanced = QPushButton("Расширенный режим")
        for b in (self._btn_mode_simple, self._btn_mode_advanced):
            b.setObjectName("BtnSecondary")
            b.setCheckable(True)
            b.setMinimumHeight(34)
            b.setCursor(Qt.CursorShape.PointingHandCursor)

        self._btn_mode_simple.clicked.connect(lambda: self._set_ui_mode("simple"))
        self._btn_mode_advanced.clicked.connect(lambda: self._set_ui_mode("advanced"))

        mode_row.addWidget(self._btn_mode_simple)
        mode_row.addWidget(self._btn_mode_advanced)
        mode_row.addStretch()

        outer.addLayout(mode_row)
        outer.addSpacing(16)

        # ── Scrollable content ──────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        content = QWidget()
        content.setStyleSheet("background: transparent;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(16)

        # ── Group: Интерфейс ────────────────────────────────────
        ui_group = SettingsGroup("Интерфейс")

        self._theme_combo = QComboBox()
        self._theme_combo.setFixedWidth(140)
        self._theme_combo.addItems(["Тёмная", "Светлая"])
        # BLOCK STAB-6: читаем ЖИВОЕ состояние ThemeManager, а не
        # AppSettings.theme — это два независимых хранилища (см. диагноз
        # в PROMPT_FIX_UX_STABILITY_THEME.md, задача 4), и после фикса
        # main.py именно theme_manager.current отражает реально применённую
        # сейчас тему.
        self._theme_combo.setCurrentIndex(
            0 if theme_manager.current == Theme.DARK else 1
        )
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        # ЗАДАЧА 1: Стилизация popup для корректного отображения темы
        connect_combobox_theme_updates(self._theme_combo)
        
        ui_group.add_row(
            "Тема оформления",
            "Тёмная или светлая тема приложения",
            self._theme_combo,
        )

        content_layout.addWidget(ui_group)

        # ── Group: Карта (BLOCK MAP-TILES) ─────────────────────────
        map_group = SettingsGroup("Карта")

        self._map_tile_url_edit = QLineEdit()
        self._map_tile_url_edit.setFixedWidth(400)
        self._map_tile_url_edit.setText(self._settings.map_tile_url)
        self._map_tile_url_edit.setPlaceholderText("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png")
        map_group.add_row(
            "URL тайлов",
            "Шаблон подложки карты: {s}=сервер, {z}=zoom, {x}/{y}=координаты тайла",
            self._map_tile_url_edit,
        )

        self._map_attribution_edit = QLineEdit()
        self._map_attribution_edit.setFixedWidth(300)
        self._map_attribution_edit.setText(self._settings.map_tile_attribution)
        self._map_attribution_edit.setPlaceholderText("© OpenStreetMap")
        map_group.add_row(
            "Атрибуция",
            "Указание источника данных карты (обязательно для большинства тайловых серверов)",
            self._map_attribution_edit,
        )

        self._map_max_zoom_spin = QSpinBox()
        self._map_max_zoom_spin.setRange(1, 22)
        self._map_max_zoom_spin.setValue(self._settings.map_tile_max_zoom)
        self._map_max_zoom_spin.setFixedWidth(80)
        map_group.add_row(
            "Макс. зум",
            "Максимальный уровень приближения карты (для OSM обычно 19)",
            self._map_max_zoom_spin,
        )

        content_layout.addWidget(map_group)

        # ── Task E: Группа "Режим обработки" УДАЛЕНА ────
        # Всегда используется single_thread (WHY_SINGLE_THREAD_FASTER.md).
        # Pipeline/Process Pool не дают выигрыша на CPU и удалены из UI.

        # ── Group: Обработка видео ──────────────────────────────────
        proc_group = SettingsGroup("Обработка видео")

        # Frame step mode
        self._frame_mode_combo = QComboBox()
        self._frame_mode_combo.setFixedWidth(140)
        self._frame_mode_combo.addItems(["Авто", "Вручную"])
        self._frame_mode_combo.setCurrentIndex(
            0 if self._settings.frame_step_mode == "auto" else 1
        )
        # ЗАДАЧА 1: Стилизация popup для корректного отображения темы
        connect_combobox_theme_updates(self._frame_mode_combo)
        
        proc_group.add_row(
            "Режим шага кадра",
            "Авто: адаптивно от скорости. Вручную: фиксированный шаг",
            self._frame_mode_combo,
        )
        
        self._frame_step_spin = QSpinBox()
        self._frame_step_spin.setRange(1, 60)
        self._frame_step_spin.setValue(self._settings.frame_step_manual)
        self._frame_step_spin.setFixedWidth(90)
        self._frame_step_spin.setSuffix("  кадров")
        self._frame_step_spin.setEnabled(self._settings.frame_step_mode == "manual")
        self._frame_mode_combo.currentIndexChanged.connect(
            lambda idx: self._frame_step_spin.setEnabled(idx == 1)
        )
        proc_group.add_row(
            "Шаг кадра (вручную)",
            "Каждый N-й кадр. Используется только в ручном режиме",
            self._frame_step_spin,
        )
        
        # Confidence thresholds
        self._conf_side_spin = QDoubleSpinBox()
        self._conf_side_spin.setRange(0.1, 0.95)
        self._conf_side_spin.setSingleStep(0.05)
        self._conf_side_spin.setDecimals(2)
        self._conf_side_spin.setValue(self._settings.conf_side)
        self._conf_side_spin.setFixedWidth(90)
        self._conf_side_spin.setToolTip(
            "Минимальная уверенность YOLO для первичной детекции знака.\n"
            "⚠️ < 0.3: много ложных срабатываний\n"
            "⚠️ > 0.9: можно пропустить реальные знаки\n"
            "Рекомендуется: 0.4-0.7"
        )
        self._conf_side_spin.valueChanged.connect(self._validate_confidence)
        proc_group.add_row(
            "Уверенность (Side Detect)",
            "YOLO side-detect: начальная детекция знака в кадре",
            self._conf_side_spin,
        )
        
        self._conf_rube_spin = QDoubleSpinBox()
        self._conf_rube_spin.setRange(0.1, 0.95)
        self._conf_rube_spin.setSingleStep(0.05)
        self._conf_rube_spin.setDecimals(2)
        self._conf_rube_spin.setValue(self._settings.conf_rube)
        self._conf_rube_spin.setFixedWidth(90)
        self._conf_rube_spin.setToolTip(
            "Минимальная уверенность для грубой категоризации знака.\n"
            "⚠️ < 0.5: большое количество неточных классификаций\n"
            "⚠️ > 0.9: пропуск сложных случаев\n"
            "Рекомендуется: 0.6-0.8"
        )
        self._conf_rube_spin.valueChanged.connect(self._validate_confidence)
        proc_group.add_row(
            "Уверенность (Rube)",
            "YOLO rube: грубая классификация категории знака",
            self._conf_rube_spin,
        )
        
        self._conf_cnn_spin = QDoubleSpinBox()
        self._conf_cnn_spin.setRange(0.1, 0.95)
        self._conf_cnn_spin.setSingleStep(0.05)
        self._conf_cnn_spin.setDecimals(2)
        self._conf_cnn_spin.setValue(self._settings.conf_cnn)
        self._conf_cnn_spin.setFixedWidth(90)
        self._conf_cnn_spin.setToolTip(
            "Минимальная уверенность CNN для точной классификации типа.\n"
            "Влияет на метрику conf_cnn = cnn_count / observation_count.\n"
            "⚠️ < 0.4: много ошибочных типов\n"
            "⚠️ > 0.9: очень строгий фильтр\n"
            "Рекомендуется: 0.5-0.7"
        )
        self._conf_cnn_spin.valueChanged.connect(self._validate_confidence)
        proc_group.add_row(
            "Уверенность (CNN)",
            "CNN fine: точная классификация типа знака",
            self._conf_cnn_spin,
        )

        self._iou_spin = QDoubleSpinBox()
        self._iou_spin.setRange(0.05, 0.5)
        self._iou_spin.setSingleStep(0.05)
        self._iou_spin.setDecimals(2)
        self._iou_spin.setValue(self._settings.iou_threshold)
        self._iou_spin.setFixedWidth(90)
        self._iou_spin.setToolTip(
            "Non-Maximum Suppression: порог перекрытия bounding boxes.\n"
            "Убирает дубликаты детекций одного знака.\n"
            "⚠️ < 0.05: может убрать близкие, но разные знаки\n"
            "⚠️ > 0.3: много дубликатов одного знака\n"
            "Рекомендуется: 0.1-0.2"
        )
        self._iou_spin.valueChanged.connect(self._validate_iou)
        proc_group.add_row(
            "IoU порог (NMS)",
            "Non-Maximum Suppression: порог перекрытия боксов",
            self._iou_spin,
        )

        content_layout.addWidget(proc_group)

        # ── Group: GPS ──────────────────────────────────────────
        gps_group = SettingsGroup("GPS и координаты")

        self._dedup_track_spin = QSpinBox()
        self._dedup_track_spin.setRange(2, 50)
        self._dedup_track_spin.setValue(int(self._settings.dedup_radius_track_m))
        self._dedup_track_spin.setSuffix("  м")
        self._dedup_track_spin.setFixedWidth(90)
        self._dedup_track_spin.setToolTip(
            "Радиус объединения повторяющихся знаков при трекинге.\n"
            "Знаки ближе этого расстояния считаются одним и тем же.\n"
            "⚠️ < 5м: один знак может раздвоиться\n"
            "⚠️ > 30м: разные знаки могут склеиться\n"
            "Рекомендуется: 8-15м"
        )
        self._dedup_track_spin.valueChanged.connect(self._validate_dedup_radius)
        gps_group.add_row(
            "Дедупликация (трекинг)",
            "Радиус объединения знаков при трекинге",
            self._dedup_track_spin,
        )
        
        self._dedup_final_spin = QSpinBox()
        self._dedup_final_spin.setRange(5, 200)
        self._dedup_final_spin.setValue(int(self._settings.dedup_radius_final_m))
        self._dedup_final_spin.setSuffix("  м")
        self._dedup_final_spin.setFixedWidth(90)
        self._dedup_final_spin.setToolTip(
            "Радиус финального объединения при сохранении в GeoJSON.\n"
            "Применяется после OSM snap к дороге.\n"
            "⚠️ < 10м: дубликаты на карте\n"
            "⚠️ > 100м: знаки с разных участков склеятся\n"
            "Рекомендуется: 15-30м"
        )
        self._dedup_final_spin.valueChanged.connect(self._validate_dedup_radius)
        gps_group.add_row(
            "Дедупликация (финальная)",
            "Радиус объединения при сохранении GeoJSON",
            self._dedup_final_spin,
        )
        
        self._dedup_azimuth_spin = QSpinBox()
        self._dedup_azimuth_spin.setRange(15, 90)
        self._dedup_azimuth_spin.setValue(int(self._settings.dedup_azimuth_deg))
        self._dedup_azimuth_spin.setSuffix("  °")
        self._dedup_azimuth_spin.setFixedWidth(90)
        gps_group.add_row(
            "Разница азимутов",
            "Минимальная разница направлений для дедупликации",
            self._dedup_azimuth_spin,
        )

        content_layout.addWidget(gps_group)

        # ── Task E: Группа "Многопоточность" УДАЛЕНА ────
        # Process Pool и Pipeline больше не выбираются, всегда используется single_thread.
        # _workers_spin, _ocr_use_pool_toggle, _ocr_workers_spin удалены из UI.

        # ── Group: Разметка полос движения (lane detection) ──────
        lane_group = SettingsGroup("Разметка полос движения")

        self._lane_conf_detect_spin = QDoubleSpinBox()
        self._lane_conf_detect_spin.setRange(0.1, 0.95)
        self._lane_conf_detect_spin.setSingleStep(0.05)
        self._lane_conf_detect_spin.setDecimals(2)
        self._lane_conf_detect_spin.setValue(self._settings.lane_conf_detect)
        self._lane_conf_detect_spin.setFixedWidth(90)
        self._lane_conf_detect_spin.setToolTip(
            "Порог уверенности YOLO для model_lane_detect (поиск стрелок разметки).\n"
            "Влияет на распознавание знаков 4.1.x/6.3.1 через LaneDetector.\n"
            "Рекомендуется: 0.5-0.75"
        )
        lane_group.add_row(
            "Уверенность (Lane Detect)",
            "Детекция стрелок разметки полос",
            self._lane_conf_detect_spin,
        )

        self._lane_conf_segment_spin = QDoubleSpinBox()
        self._lane_conf_segment_spin.setRange(0.1, 0.95)
        self._lane_conf_segment_spin.setSingleStep(0.05)
        self._lane_conf_segment_spin.setDecimals(2)
        self._lane_conf_segment_spin.setValue(self._settings.lane_conf_segment)
        self._lane_conf_segment_spin.setFixedWidth(90)
        self._lane_conf_segment_spin.setToolTip(
            "Порог уверенности YOLO для model_lane_segment (сегментация стрелок).\n"
            "Рекомендуется: 0.5-0.75"
        )
        lane_group.add_row(
            "Уверенность (Lane Segment)",
            "Сегментация направления стрелок разметки",
            self._lane_conf_segment_spin,
        )

        content_layout.addWidget(lane_group)

        # ── Group: Логирование ──────────────────────────────────
        log_group = SettingsGroup("Логирование")

        self._log_toggle = ToggleButton(self._settings.verbose_log)
        log_group.add_row(
            "Подробный лог",
            "Выводить информацию о каждом обнаруженном знаке",
            self._log_toggle,
        )

        self._save_frames_toggle = ToggleButton(self._settings.save_error_frames)
        log_group.add_row(
            "Сохранять кадры ошибок",
            "Записывать кадры с низкой уверенностью в ./errorData",
            self._save_frames_toggle,
        )

        content_layout.addWidget(log_group)
        
        # ── Group: Геометрия перекрёстков (BLOCK H) ─────────────
        turn_group = SettingsGroup("Перекрёстки и повороты")
        
        self._turn_use_bearing_toggle = ToggleButton(self._settings.turn_use_bearing_geometry)
        self._turn_use_bearing_toggle.setToolTip(
            "Экспериментальная функция: точная привязка знаков на поворотах.\n\n"
            "✅ Включено (рекомендуется):\n"
            "  • Геометрическое определение стороны через bearing + OSM\n"
            "  • Работает на T-образных перекрёстках, кольцах, скошенных примыканиях\n"
            "  • Устойчиво к шуму GPS через агрегацию наблюдений\n\n"
            "❌ Выключено (legacy):\n"
            "  • Эвристика через изменение размера bbox\n"
            "  • Может ошибаться на нетиповых перекрёстках\n\n"
            "⚡ Производительность: одинаковая в обоих режимах (batch OSM)"
        )
        turn_group.add_row(
            "Геометрическая привязка",
            "Точное определение стороны знака на перекрёстках",
            self._turn_use_bearing_toggle,
        )
        
        self._camera_fov_spin = QDoubleSpinBox()
        self._camera_fov_spin.setRange(60.0, 150.0)
        self._camera_fov_spin.setSingleStep(5.0)
        self._camera_fov_spin.setDecimals(1)
        self._camera_fov_spin.setValue(self._settings.camera_hfov_deg)
        self._camera_fov_spin.setSuffix("  °")
        self._camera_fov_spin.setFixedWidth(90)
        self._camera_fov_spin.setToolTip(
            "Горизонтальный угол обзора (FOV) вашей камеры/видеорегистратора.\n\n"
            "Типовые значения:\n"
            "  • GoPro Hero: ~120°\n"
            "  • Обычные dashcam: 90-110°\n"
            "  • Узкоугольные камеры: 60-80°\n\n"
            "⚠️ Неправильный FOV даёт ошибку в bearing → знак привяжется\n"
            "к неправильной стороне перекрёстка!\n\n"
            "💡 Как измерить:\n"
            "  1. Снимите кадр с дверным проёмом (~90см ширины)\n"
            "  2. Посчитайте сколько проёмов помещается по ширине\n"
            "  3. FOV ≈ 2 * atan(ширина_сенсора / (2 * фокусное_расстояние))"
        )
        turn_group.add_row(
            "FOV камеры",
            "Горизонтальный угол обзора (GoPro ~120°, dashcam ~100°)",
            self._camera_fov_spin,
        )
        
        self._turn_ray_dist_spin = QSpinBox()
        self._turn_ray_dist_spin.setRange(20, 100)
        self._turn_ray_dist_spin.setValue(int(self._settings.turn_ray_max_distance_m))
        self._turn_ray_dist_spin.setSuffix("  м")
        self._turn_ray_dist_spin.setFixedWidth(90)
        self._turn_ray_dist_spin.setToolTip(
            "Максимальная дистанция поиска дороги от знака на перекрёстке.\n\n"
            "Луч бросается от машины по азимуту на знак.\n"
            "Если дорога не найдена в этом радиусе → fallback на legacy.\n\n"
            "⚠️ < 30м: может не найти дорогу на крупных перекрёстках\n"
            "⚠️ > 80м: может попасть в неправильную дорогу\n\n"
            "Рекомендуется: 35-50м"
        )
        turn_group.add_row(
            "Дистанция луча",
            "Максимальная дистанция raycast к дороге",
            self._turn_ray_dist_spin,
        )
        
        # BLOCK N.3: turn_detection_radius_m удалён (дублирует turn_ray_max_distance_m)
        
        content_layout.addWidget(turn_group)
        
        # ── Group: Диагностика ──────────────────────────────────
        # ── Group: Вычисления (CPU/GPU) — ALWAYS VISIBLE ──────────
        compute_group = SettingsGroup("Вычисления (CPU / GPU)")
        
        # CUDA toggle
        self._cuda_toggle = ToggleButton(self._settings.use_cuda)
        compute_group.add_row(
            "Использовать CUDA",
            "Включить GPU-ускорение для моделей YOLO и распознавания текста (OCR), если доступна",
            self._cuda_toggle,
        )
        
        # GPU check button
        gpu_check_btn = QPushButton("🔍  Проверить GPU")
        gpu_check_btn.setObjectName("BtnSecondary")
        gpu_check_btn.setMinimumHeight(36)
        gpu_check_btn.setMinimumWidth(160)
        gpu_check_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        gpu_check_btn.clicked.connect(self._check_gpu)
        
        gpu_layout = QVBoxLayout()
        gpu_layout.setSpacing(8)
        gpu_layout.addWidget(gpu_check_btn)
        
        self._gpu_status_label = QLabel("")
        self._gpu_status_label.setObjectName("SettingsHint")
        self._gpu_status_label.setWordWrap(True)
        gpu_layout.addWidget(self._gpu_status_label)
        
        gpu_widget = QWidget()
        gpu_widget.setStyleSheet("background: transparent;")
        gpu_widget.setLayout(gpu_layout)
        
        compute_group.add_row(
            "Проверка CUDA/GPU",
            "Доступность GPU-ускорения для YOLO и других моделей",
            gpu_widget,
        )
        
        # ── CPU-инференс (BLOCK M) ──────────────────────────────
        self._cpu_backend_combo = QComboBox()
        self._cpu_backend_combo.addItems([
            "PyTorch (по умолчанию)",
            "ONNX Runtime",
            "OpenVINO"
        ])
        # Устанавливаем текущее значение
        backend_map = {"torch": 0, "onnx": 1, "openvino": 2}
        self._cpu_backend_combo.setCurrentIndex(
            backend_map.get(self._settings.cpu_inference_backend, 0)
        )
        self._cpu_backend_combo.setMinimumHeight(36)
        self._cpu_backend_combo.setMinimumWidth(200)
        # ЗАДАЧА 1: Стилизация popup для корректного отображения темы
        connect_combobox_theme_updates(self._cpu_backend_combo)
        
        # Связываем активность с CUDA toggle
        def update_backend_enabled():
            enabled = not self._cuda_toggle.is_checked()
            self._cpu_backend_combo.setEnabled(enabled)
        
        self._cuda_toggle.toggled_state.connect(lambda _: update_backend_enabled())
        update_backend_enabled()  # Применяем начальное состояние
        
        compute_group.add_row(
            "Бэкенд CPU-инференса",
            "Используется только при выключенном CUDA. Требует экспорта моделей (см. Расширенный режим).",
            self._cpu_backend_combo,
        )
        
        content_layout.addWidget(compute_group)
        
        # ── Group: Диагностика (расширенная) — ADVANCED ONLY ──────
        diag_group_advanced = SettingsGroup("Диагностика системы (расширенная)")
        
        # ── CPU-инференс: потоки ONNX Runtime (BLOCK CPU-5) ──────
        self._cpu_onnx_intra_spin = QSpinBox()
        self._cpu_onnx_intra_spin.setRange(0, 64)
        self._cpu_onnx_intra_spin.setValue(self._settings.cpu_onnx_intra_threads)
        self._cpu_onnx_intra_spin.setSuffix(" потоков")
        self._cpu_onnx_intra_spin.setSpecialValueText("0 (авто)")
        self._cpu_onnx_intra_spin.setMinimumHeight(36)
        self._cpu_onnx_intra_spin.setMinimumWidth(150)
        
        diag_group_advanced.add_row(
            "Потоки ONNX intra_op",
            "Число потоков для ONNX Runtime intra_op (параллелизм внутри операции).\n"
            "0 = автоматический расчёт с учётом количества воркеров Process Pool.\n"
            "Рекомендуется оставить 0 для автоматической оптимизации.",
            self._cpu_onnx_intra_spin,
        )
        
        # ── CPU-инференс: потоки OpenVINO (BLOCK CPU-5) ──────────
        self._cpu_openvino_threads_spin = QSpinBox()
        self._cpu_openvino_threads_spin.setRange(0, 64)
        self._cpu_openvino_threads_spin.setValue(self._settings.cpu_openvino_threads)
        self._cpu_openvino_threads_spin.setSuffix(" потоков")
        self._cpu_openvino_threads_spin.setSpecialValueText("0 (авто)")
        self._cpu_openvino_threads_spin.setMinimumHeight(36)
        self._cpu_openvino_threads_spin.setMinimumWidth(150)
        
        diag_group_advanced.add_row(
            "Потоки OpenVINO",
            "Число потоков для OpenVINO INFERENCE_NUM_THREADS.\n"
            "0 = автоматический расчёт с учётом количества воркеров Process Pool.\n"
            "Рекомендуется оставить 0 для автоматической оптимизации.",
            self._cpu_openvino_threads_spin,
        )
        
        # Кнопка экспорта моделей
        export_models_btn = QPushButton("📦  Экспортировать модели для CPU")
        export_models_btn.setObjectName("BtnSecondary")
        export_models_btn.setMinimumHeight(36)
        export_models_btn.setMinimumWidth(220)
        export_models_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_models_btn.clicked.connect(self._export_models)
        
        export_models_layout = QVBoxLayout()
        export_models_layout.setSpacing(8)
        export_models_layout.addWidget(export_models_btn)
        
        self._export_models_status = QLabel("")
        self._export_models_status.setObjectName("SettingsHint")
        self._export_models_status.setWordWrap(True)
        export_models_layout.addWidget(self._export_models_status)
        
        export_models_widget = QWidget()
        export_models_widget.setStyleSheet("background: transparent;")
        export_models_widget.setLayout(export_models_layout)
        
        diag_group_advanced.add_row(
            "Экспорт моделей",
            "Конвертация .pt моделей в ONNX/OpenVINO для ускорения CPU-инференса",
            export_models_widget,
        )
        
        content_layout.addWidget(diag_group_advanced)
        
        # ── Group: Экспорт/Импорт ───────────────────────────────
        export_group = SettingsGroup("Резервное копирование")
        
        export_import_layout = QHBoxLayout()
        export_import_layout.setSpacing(8)
        
        export_btn = QPushButton("📤  Экспорт")
        export_btn.setObjectName("BtnSecondary")
        export_btn.setMinimumHeight(36)
        export_btn.setMinimumWidth(120)
        export_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        export_btn.clicked.connect(self._export_settings)
        
        import_btn = QPushButton("📥  Импорт")
        import_btn.setObjectName("BtnSecondary")
        import_btn.setMinimumHeight(36)
        import_btn.setMinimumWidth(120)
        import_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        import_btn.clicked.connect(self._import_settings)
        
        export_import_layout.addWidget(export_btn)
        export_import_layout.addWidget(import_btn)
        export_import_layout.addStretch()
        
        export_widget = QWidget()
        export_widget.setStyleSheet("background: transparent;")
        export_widget.setLayout(export_import_layout)
        
        export_group.add_row(
            "Настройки в файл",
            "Экспорт/импорт всех настроек в JSON для переноса между машинами",
            export_widget,
        )
        
        content_layout.addWidget(export_group)
        
        content_layout.addStretch()

        # ── Reset + Save buttons ────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        reset_btn = QPushButton("↻  Сбросить")
        reset_btn.setObjectName("BtnSecondary")
        reset_btn.setMinimumHeight(40)
        reset_btn.setMinimumWidth(120)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset)

        save_btn = QPushButton("💾  Сохранить")
        save_btn.setObjectName("BtnPrimary")
        save_btn.setMinimumHeight(40)
        save_btn.setMinimumWidth(120)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)

        btn_row.addWidget(reset_btn)
        btn_row.addSpacing(12)
        btn_row.addWidget(save_btn)
        content_layout.addLayout(btn_row)

        scroll.setWidget(content)
        outer.addWidget(scroll)
        
        # BLOCK SETTINGS-UX: список групп, скрываемых в Простом режиме
        self._advanced_only_widgets = [
            ui_group,              # Интерфейс / тема
            proc_group,            # Обработка видео
            gps_group,             # GPS и координаты
            # mt_group УДАЛЕНА (Task E) - группа "Многопоточность" больше не существует
            lane_group,            # Разметка полос движения
            log_group,             # Логирование
            turn_group,            # Перекрёстки и повороты
            diag_group_advanced,   # Расширенная диагностика
            export_group,          # Резервное копирование
        ]
        
        # BLOCK SETTINGS-UX: применить сохранённый режим при открытии страницы
        self._set_ui_mode(self._settings.settings_ui_mode)

        # Переприменяем валидационные стили при смене темы (warning-цвет зависит от темы)
        theme_manager.theme_changed.connect(self._revalidate_all_controls)

    # ── Slots ──────────────────────────────────────────────────

    def _on_theme_changed(self, index: int):
        """Обработчик изменения темы."""
        from PyQt6.QtWidgets import QApplication
        theme_str = "dark" if index == 0 else "light"
        t = Theme.DARK if index == 0 else Theme.LIGHT
        theme_manager.set_theme(t, QApplication.instance())
        self.theme_changed.emit(theme_str)
    
    def _set_ui_mode(self, mode: str) -> None:
        """
        BLOCK SETTINGS-UX: переключение между простым и расширенным режимом.
        
        Args:
            mode: "simple" или "advanced"
        """
        is_advanced = (mode == "advanced")
        
        # Показать/скрыть расширенные группы
        for widget in self._advanced_only_widgets:
            widget.setVisible(is_advanced)
        
        # Обновить состояние кнопок
        self._btn_mode_simple.setChecked(not is_advanced)
        self._btn_mode_advanced.setChecked(is_advanced)
        self._restyle_mode_buttons()
        
        # Сохраняем выбор немедленно (аналогично мгновенному применению темы),
        # чтобы режим не сбрасывался при закрытии без "Сохранить"
        self._settings.settings_ui_mode = mode
        try:
            self._settings.save()
        except Exception as e:
            print(f"[SettingsPage] Не удалось сохранить режим настроек: {e}")
    
    def _restyle_mode_buttons(self) -> None:
        """Обновляет визуальное выделение активной кнопки режима."""
        t = theme_manager.tokens
        for btn, active in (
            (self._btn_mode_simple, self._btn_mode_simple.isChecked()),
            (self._btn_mode_advanced, self._btn_mode_advanced.isChecked()),
        ):
            if active:
                btn.setStyleSheet(
                    f"background:{t['accent']}; color:{t['text_on_accent']}; "
                    f"border-radius:8px; padding: 8px 16px;"
                )
            else:
                btn.setStyleSheet("")  # Вернуться к стилю BtnSecondary
    
    def _collect_settings(self):
        """
        Task E: Собирает текущие значения из UI в объект настроек.
        processing_mode, process_pool_workers, ocr_* больше не собираются (удалены из UI).
        """
        try:
            # Frame step
            mode_idx = self._frame_mode_combo.currentIndex()
            self._settings.frame_step_mode = "auto" if mode_idx == 0 else "manual"
            self._settings.frame_step_manual = self._frame_step_spin.value()
            
            # Confidence
            self._settings.conf_side = self._conf_side_spin.value()
            self._settings.conf_rube = self._conf_rube_spin.value()
            self._settings.conf_cnn = self._conf_cnn_spin.value()
            self._settings.iou_threshold = self._iou_spin.value()
            
            # Deduplication
            self._settings.dedup_radius_track_m = float(self._dedup_track_spin.value())
            self._settings.dedup_radius_final_m = float(self._dedup_final_spin.value())
            self._settings.dedup_azimuth_deg = float(self._dedup_azimuth_spin.value())
            
            # Task E: processing_mode, process_pool_workers, ocr_* УДАЛЕНЫ (не собираем из UI)
            # processing_mode всегда будет "single_thread" (устанавливается в ProcessingController)
            
            # Map tile configuration (BLOCK MAP-TILES)
            if hasattr(self, '_map_tile_url_edit'):
                self._settings.map_tile_url = self._map_tile_url_edit.text().strip()
            if hasattr(self, '_map_attribution_edit'):
                self._settings.map_tile_attribution = self._map_attribution_edit.text().strip()
            if hasattr(self, '_map_max_zoom_spin'):
                self._settings.map_tile_max_zoom = self._map_max_zoom_spin.value()
            
            # CUDA settings
            if hasattr(self, '_cuda_toggle'):
                self._settings.use_cuda = self._cuda_toggle.is_checked()
            
            # CPU-инференс (BLOCK M)
            if hasattr(self, '_cpu_backend_combo'):
                backend_map = {0: "torch", 1: "onnx", 2: "openvino"}
                self._settings.cpu_inference_backend = backend_map.get(
                    self._cpu_backend_combo.currentIndex(), "torch"
                )
            
            # CPU-инференс: потоки (BLOCK CPU-5)
            if hasattr(self, '_cpu_onnx_intra_spin'):
                self._settings.cpu_onnx_intra_threads = self._cpu_onnx_intra_spin.value()
            if hasattr(self, '_cpu_openvino_threads_spin'):
                self._settings.cpu_openvino_threads = self._cpu_openvino_threads_spin.value()
            
            # Lane detection thresholds (BLOCK M-FIX: BUG-5)
            if hasattr(self, '_lane_conf_detect_spin'):
                self._settings.lane_conf_detect = self._lane_conf_detect_spin.value()
            if hasattr(self, '_lane_conf_segment_spin'):
                self._settings.lane_conf_segment = self._lane_conf_segment_spin.value()
            
            # Logging
            self._settings.verbose_log = self._log_toggle.is_checked()
            self._settings.save_error_frames = self._save_frames_toggle.is_checked()
            
            # Turn Geometry (BLOCK H) - с проверкой наличия виджетов
            if hasattr(self, '_turn_use_bearing_toggle'):
                self._settings.turn_use_bearing_geometry = self._turn_use_bearing_toggle.is_checked()
            if hasattr(self, '_camera_fov_spin'):
                self._settings.camera_hfov_deg = self._camera_fov_spin.value()
            if hasattr(self, '_turn_ray_dist_spin'):
                self._settings.turn_ray_max_distance_m = float(self._turn_ray_dist_spin.value())
            # BLOCK N.3: turn_radius_spin удалён
            
            # Theme
            theme_idx = self._theme_combo.currentIndex()
            self._settings.theme = "dark" if theme_idx == 0 else "light"
            
        except Exception as e:
            print(f"[SettingsPage] ОШИБКА в _collect_settings: {e}")
            import traceback
            traceback.print_exc()

    def _save(self):
        """Сохранить настройки."""
        sender = self.sender()
        original_text = sender.text() if sender else None
        
        # Task B: Используем try/finally для гарантированного восстановления кнопки
        try:
            # Показываем визуальную обратную связь сразу
            if sender:
                sender.setEnabled(False)
            
            self._collect_settings()
            
            # BLOCK FIX-4.2: Проверка готовности backend перед сохранением
            self._check_backend_readiness()
            
            self._settings.save()
            
            # Визуальная обратная связь об успешном сохранении
            if sender:
                sender.setText("✓  Сохранено")
                
                from PyQt6.QtCore import QTimer
                def restore():
                    if original_text:
                        sender.setText(original_text)
                    sender.setEnabled(True)
                
                QTimer.singleShot(1500, restore)
            
            # Уведомляем о изменении
            self.settings_changed.emit()
            print("[SettingsPage] Настройки сохранены успешно")
            
        except Exception as e:
            print(f"[SettingsPage] КРИТИЧЕСКАЯ ОШИБКА при сохранении: {e}")
            import traceback
            traceback.print_exc()
            
            # Показываем ошибку пользователю
            from PyQt6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self,
                "Ошибка сохранения",
                f"Не удалось сохранить настройки:\n{str(e)}\n\nПроверьте логи для деталей."
            )
            
            # Task B: В блоке finally гарантированно восстанавливаем кнопку
            # Но при ошибке возвращаем сразу, без 1.5-секундной задержки
            if sender and original_text:
                sender.setText(original_text)
                sender.setEnabled(True)

    def _check_backend_readiness(self):
        """
        BLOCK FIX-4.2: Проверяет готовность выбранного CPU backend к использованию.
        Если backend не готов (отсутствуют зависимости или экспортированные файлы),
        показывает предупреждение пользователю. НЕ блокирует сохранение настроек.
        """
        from PyQt6.QtWidgets import QMessageBox
        import os
        import glob
        
        # Проверяем только если CUDA выключен и выбран не-PyTorch backend
        if hasattr(self, '_cuda_toggle') and self._cuda_toggle.is_checked():
            return  # CUDA включён, CPU backend не используется
        
        backend_idx = self._cpu_backend_combo.currentIndex()
        if backend_idx == 0:  # PyTorch (по умолчанию)
            return  # PyTorch всегда доступен
        
        backend_name = {1: "onnx", 2: "openvino"}[backend_idx]
        backend_display = {1: "ONNX Runtime", 2: "OpenVINO"}[backend_idx]
        issues = []
        
        # Проверка 1: установлен ли необходимый пакет?
        try:
            if backend_name == "onnx":
                import onnx
                import onnxruntime
            elif backend_name == "openvino":
                import openvino
        except ImportError as e:
            missing_pkg = str(e).split("'")[1] if "'" in str(e) else "неизвестный пакет"
            issues.append(f"• Пакет '{missing_pkg}' не установлен")
        
        # Проверка 2: есть ли экспортированные файлы?
        exported_files_exist = False
        if backend_name == "onnx":
            # Ищем хотя бы один .onnx файл
            onnx_patterns = [
                "CNN_side/*.onnx",
                "small_models/*.onnx",
                "lane_guidance_models/*.onnx"
            ]
            for pattern in onnx_patterns:
                if glob.glob(pattern):
                    exported_files_exist = True
                    break
        elif backend_name == "openvino":
            # Ищем хотя бы одну директорию *_openvino_model
            openvino_patterns = [
                "CNN_side/*_openvino_model",
                "small_models/*_openvino_model",
                "lane_guidance_models/*_openvino_model"
            ]
            for pattern in openvino_patterns:
                if glob.glob(pattern):
                    exported_files_exist = True
                    break
        
        if not exported_files_exist:
            issues.append(f"• Модели не экспортированы в формат {backend_name.upper()}")
        
        # Если есть проблемы — показываем предупреждение
        if issues:
            issue_text = "\n".join(issues)
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("Backend не готов к использованию")
            msg.setText(
                f"Вы выбрали backend '{backend_display}', но он не готов к использованию:\n\n"
                f"{issue_text}\n\n"
                f"Обработка будет использовать PyTorch (fallback), пока вы не:\n"
                f"  1. Установите зависимости: pip install -r requirements.txt\n"
                f"  2. Экспортируете модели: кнопка '📦 Экспортировать модели для CPU'\n\n"
                f"Настройки будут сохранены, но backend может не работать."
            )
            msg.setStandardButtons(QMessageBox.StandardButton.Ok)
            msg.exec()

    def _reset(self):
        """Сбросить к значениям по умолчанию."""
        try:
            from configs.settings import AppSettings
            defaults = AppSettings()
            
            # Применяем defaults к UI (с проверкой существования виджетов)
            if hasattr(self, '_frame_mode_combo'):
                self._frame_mode_combo.setCurrentIndex(0 if defaults.frame_step_mode == "auto" else 1)
            if hasattr(self, '_frame_step_spin'):
                self._frame_step_spin.setValue(defaults.frame_step_manual)
            if hasattr(self, '_conf_side_spin'):
                self._conf_side_spin.setValue(defaults.conf_side)
            if hasattr(self, '_conf_rube_spin'):
                self._conf_rube_spin.setValue(defaults.conf_rube)
            if hasattr(self, '_conf_cnn_spin'):
                self._conf_cnn_spin.setValue(defaults.conf_cnn)
            if hasattr(self, '_iou_spin'):
                self._iou_spin.setValue(defaults.iou_threshold)
            if hasattr(self, '_dedup_track_spin'):
                self._dedup_track_spin.setValue(int(defaults.dedup_radius_track_m))
            if hasattr(self, '_dedup_final_spin'):
                self._dedup_final_spin.setValue(int(defaults.dedup_radius_final_m))
            if hasattr(self, '_dedup_azimuth_spin'):
                self._dedup_azimuth_spin.setValue(int(defaults.dedup_azimuth_deg))
            
            # Task E: processing_mode, workers, ocr_* виджеты УДАЛЕНЫ (пропускаем)
            
            # CUDA settings
            if hasattr(self, '_cuda_toggle'):
                self._cuda_toggle.set_checked(defaults.use_cuda)
            
            # CPU-инференс бэкенд (BLOCK M-FIX: BUG-3)
            if hasattr(self, '_cpu_backend_combo'):
                backend_map_rev = {"torch": 0, "onnx": 1, "openvino": 2}
                self._cpu_backend_combo.setCurrentIndex(
                    backend_map_rev.get(defaults.cpu_inference_backend, 0)
                )
            
            # CPU-инференс: потоки (BLOCK CPU-5)
            if hasattr(self, '_cpu_onnx_intra_spin'):
                self._cpu_onnx_intra_spin.setValue(defaults.cpu_onnx_intra_threads)
            if hasattr(self, '_cpu_openvino_threads_spin'):
                self._cpu_openvino_threads_spin.setValue(defaults.cpu_openvino_threads)
            
            # Пороги lane detection (BLOCK M-FIX: BUG-5, виджеты создаются ниже)
            if hasattr(self, '_lane_conf_detect_spin'):
                self._lane_conf_detect_spin.setValue(defaults.lane_conf_detect)
            if hasattr(self, '_lane_conf_segment_spin'):
                self._lane_conf_segment_spin.setValue(defaults.lane_conf_segment)
            
            if hasattr(self, '_log_toggle'):
                self._log_toggle.set_checked(defaults.verbose_log)
            if hasattr(self, '_save_frames_toggle'):
                self._save_frames_toggle.set_checked(defaults.save_error_frames)
            
            # Turn Geometry (BLOCK H)
            if hasattr(self, '_turn_use_bearing_toggle'):
                self._turn_use_bearing_toggle.set_checked(defaults.turn_use_bearing_geometry)
            if hasattr(self, '_camera_fov_spin'):
                self._camera_fov_spin.setValue(defaults.camera_hfov_deg)
            if hasattr(self, '_turn_ray_dist_spin'):
                self._turn_ray_dist_spin.setValue(int(defaults.turn_ray_max_distance_m))
            # BLOCK N.3: turn_radius_spin удалён
            
            if hasattr(self, '_theme_combo'):
                self._theme_combo.setCurrentIndex(0 if defaults.theme == "dark" else 1)
            
            print("[SettingsPage] Настройки сброшены к defaults")
            
            # BLOCK SETTINGS-UX: восстанавливаем режим по умолчанию
            self._set_ui_mode(defaults.settings_ui_mode)
            
        except Exception as e:
            print(f"[SettingsPage] Ошибка в _reset: {e}")
            import traceback
            traceback.print_exc()
    
    def _validate_confidence(self, value: float):
        """Валидация порогов уверенности с визуальным предупреждением."""
        sender = self.sender()
        
        # Определяем тип confidence
        if sender == self._conf_side_spin:
            name = "Side Detect"
            warn_low, warn_high = 0.3, 0.9
        elif sender == self._conf_rube_spin:
            name = "Rube"
            warn_low, warn_high = 0.5, 0.9
        else:  # CNN
            name = "CNN"
            warn_low, warn_high = 0.4, 0.9
        
        # Проверка на рискованные значения
        if value < warn_low:
            sender.setStyleSheet(f"QDoubleSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}")
            print(f"[SettingsPage] ⚠️ Внимание: {name} confidence {value} < {warn_low} - много ложных срабатываний!")
        elif value > warn_high:
            sender.setStyleSheet(f"QDoubleSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}")
            print(f"[SettingsPage] ⚠️ Внимание: {name} confidence {value} > {warn_high} - можно пропустить знаки!")
        else:
            sender.setStyleSheet("")  # Сброс к нормальному виду
    
    def _validate_iou(self, value: float):
        """Валидация IoU порога."""
        if value < 0.05:
            self._iou_spin.setStyleSheet(f"QDoubleSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}")
            print(f"[SettingsPage] ⚠️ Внимание: IoU {value} слишком низкий - могут склеиться разные знаки!")
        elif value > 0.3:
            self._iou_spin.setStyleSheet(f"QDoubleSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}")
            print(f"[SettingsPage] ⚠️ Внимание: IoU {value} слишком высокий - много дубликатов!")
        else:
            self._iou_spin.setStyleSheet("")
    
    def _validate_dedup_radius(self, value: int):
        """Валидация радиусов дедупликации."""
        sender = self.sender()
        
        if sender == self._dedup_track_spin:
            name = "Трекинг"
            warn_low, warn_high = 5, 30
        else:  # Final
            name = "Финальная"
            warn_low, warn_high = 10, 100
        
        if value < warn_low:
            sender.setStyleSheet(f"QSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}")
            print(f"[SettingsPage] ⚠️ Внимание: {name} радиус {value}м слишком мал - дубликаты!")
        elif value > warn_high:
            sender.setStyleSheet(f"QSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}")
            print(f"[SettingsPage] ⚠️ Внимание: {name} радиус {value}м слишком велик - склеивание!")
        else:
            sender.setStyleSheet("")

    def _revalidate_all_controls(self, _theme=None) -> None:
        """Переприменяет валидацию ко всем spinbox'ам при смене темы.

        Inline-стили с warning-цветом содержат конкретное hex-значение,
        которое отличается для тёмной и светлой тем. Этот метод
        эмулирует изменение значения для каждого спинбокса, чтобы
        _validate_* пересчитали цвет с актуальными токенами.
        """
        for spin in (
            self._conf_side_spin,
            self._conf_rube_spin,
            self._conf_cnn_spin,
        ):
            self._validate_confidence_for(spin, spin.value())

        self._validate_iou_for(self._iou_spin.value())

        for spin in (self._dedup_track_spin, self._dedup_final_spin):
            self._validate_dedup_radius_for(spin, spin.value())

    # ── Internal helpers for validation (accept explicit widget + value) ──

    def _validate_confidence_for(self, widget: QWidget, value: float) -> None:
        """Валидация одного confidence-спинбокса без опоры на sender()."""
        if widget == self._conf_side_spin:
            warn_low, warn_high = 0.3, 0.9
        elif widget == self._conf_rube_spin:
            warn_low, warn_high = 0.5, 0.9
        else:
            warn_low, warn_high = 0.4, 0.9

        if value < warn_low or value > warn_high:
            widget.setStyleSheet(
                f"QDoubleSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}"
            )
        else:
            widget.setStyleSheet("")

    def _validate_iou_for(self, value: float) -> None:
        """Валидация IoU-спинбокса без опоры на sender()."""
        if value < 0.05 or value > 0.3:
            self._iou_spin.setStyleSheet(
                f"QDoubleSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}"
            )
        else:
            self._iou_spin.setStyleSheet("")

    def _validate_dedup_radius_for(self, widget: QWidget, value: int) -> None:
        """Валидация одного radius-спинбокса без опоры на sender()."""
        if widget == self._dedup_track_spin:
            warn_low, warn_high = 5, 30
        else:
            warn_low, warn_high = 10, 100

        if value < warn_low or value > warn_high:
            widget.setStyleSheet(
                f"QSpinBox {{ border: 2px solid {theme_manager.tokens['warning']}; }}"
            )
        else:
            widget.setStyleSheet("")

    def _check_gpu(self):
        """Проверка доступности GPU/CUDA."""
        try:
            import torch
            cuda_available = torch.cuda.is_available()
            
            if cuda_available:
                device_name = torch.cuda.get_device_name(0)
                device_count = torch.cuda.device_count()
                cuda_version = torch.version.cuda
                
                status_text = (
                    f"✅ CUDA доступна\n"
                    f"GPU: {device_name}\n"
                    f"Устройств: {device_count}\n"
                    f"CUDA версия: {cuda_version}"
                )
                self._gpu_status_label.setStyleSheet(
                    f"color: {theme_manager.tokens['success']}; font-size: 11px;"
                )
            else:
                status_text = (
                    "⚠️ CUDA недоступна\n"
                    "Обработка будет использовать CPU.\n"
                    "Для GPU-ускорения установите CUDA Toolkit и PyTorch с поддержкой CUDA."
                )
                self._gpu_status_label.setStyleSheet(
                    f"color: {theme_manager.tokens['warning']}; font-size: 11px;"
                )
            
            self._gpu_status_label.setText(status_text)
            print(f"[SettingsPage] GPU check: {status_text}")
            
        except Exception as e:
            status_text = f"❌ Ошибка проверки: {str(e)}"
            self._gpu_status_label.setText(status_text)
            self._gpu_status_label.setStyleSheet(
                f"color: {theme_manager.tokens['error']}; font-size: 11px;"
            )
            print(f"[SettingsPage] GPU check error: {e}")
    
    def _export_models(self):
        """Экспорт моделей в ONNX/OpenVINO форматы (BLOCK M)."""
        from PyQt6.QtCore import QThread, pyqtSignal
        import subprocess
        import sys
        
        # Определяем формат на основе выбранного backend
        backend_map = {0: "torch", 1: "onnx", 2: "openvino"}
        backend = backend_map.get(self._cpu_backend_combo.currentIndex(), "onnx")
        
        if backend == "torch":
            self._export_models_status.setText(
                "ℹ️ PyTorch не требует экспорта моделей"
            )
            self._export_models_status.setStyleSheet(
                f"color: {theme_manager.tokens['text_muted']}; font-size: 11px;"
            )
            return
        
        # Worker для фонового экспорта
        class ExportWorker(QThread):
            finished = pyqtSignal(bool, str)  # success, message
            
            def __init__(self, backend_format):
                super().__init__()
                self.backend_format = backend_format
            
            def run(self):
                try:
                    # Запускаем скрипт экспорта
                    result = subprocess.run(
                        [sys.executable, "scripts/export_models_onnx.py", 
                         "--format", self.backend_format],
                        capture_output=True,
                        text=True,
                        timeout=600  # 10 минут максимум
                    )
                    
                    if result.returncode == 0:
                        self.finished.emit(True, "✅ Экспорт завершён успешно")
                    else:
                        error_msg = result.stderr if result.stderr else result.stdout
                        self.finished.emit(False, f"❌ Ошибка экспорта:\n{error_msg[:200]}")
                
                except subprocess.TimeoutExpired:
                    self.finished.emit(False, "❌ Превышено время ожидания (10 мин)")
                except Exception as e:
                    self.finished.emit(False, f"❌ Ошибка: {str(e)}")
        
        # Обновляем статус
        self._export_models_status.setText(
            f"⏳ Экспорт в {backend.upper()}... (это может занять несколько минут)"
        )
        self._export_models_status.setStyleSheet(
            f"color: {theme_manager.tokens['text_muted']}; font-size: 11px;"
        )
        
        # Запускаем worker
        self._export_worker = ExportWorker(backend)
        self._export_worker.finished.connect(self._on_export_finished)
        self._export_worker.start()
    
    def _on_export_finished(self, success: bool, message: str):
        """Обработка завершения экспорта моделей."""
        self._export_models_status.setText(message)
        
        if success:
            self._export_models_status.setStyleSheet(
                f"color: {theme_manager.tokens['success']}; font-size: 11px;"
            )
        else:
            self._export_models_status.setStyleSheet(
                f"color: {theme_manager.tokens['error']}; font-size: 11px;"
            )
    
    def _export_settings(self):
        """Экспорт настроек в JSON файл."""
        from PyQt6.QtWidgets import QFileDialog
        import json
        from datetime import datetime
        
        # Собираем текущие настройки
        self._collect_settings()
        
        # Диалог сохранения файла
        default_name = f"roadscan_settings_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Экспорт настроек",
            default_name,
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            # Экспортируем настройки используя to_dict() для полноты (BLOCK 3.6)
            settings_dict = self._settings.to_dict()
            settings_dict["exported_at"] = datetime.now().isoformat()
            settings_dict["version"] = "2.0"
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(settings_dict, f, indent=2, ensure_ascii=False)
            
            print(f"[SettingsPage] Настройки экспортированы в: {file_path}")
            
            # Визуальная обратная связь
            from PyQt6.QtCore import QTimer
            btn = self.sender()
            original_text = btn.text()
            btn.setText("✓  Экспортировано")
            btn.setEnabled(False)
            
            def restore():
                btn.setText(original_text)
                btn.setEnabled(True)
            
            QTimer.singleShot(1500, restore)
            
        except Exception as e:
            print(f"[SettingsPage] Ошибка экспорта настроек: {e}")
            self._show_error_message(f"Ошибка экспорта: {str(e)}")
    
    def _import_settings(self):
        """Импорт настроек из JSON файла."""
        from PyQt6.QtWidgets import QFileDialog, QMessageBox
        import json
        
        # Диалог открытия файла
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Импорт настроек",
            "",
            "JSON Files (*.json);;All Files (*)"
        )
        
        if not file_path:
            return
        
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                settings_dict = json.load(f)
            
            # Проверка версии (опционально)
            if settings_dict.get("version") != "2.0":
                reply = QMessageBox.question(
                    self,
                    "Несовпадение версий",
                    "Версия настроек не совпадает с текущей версией приложения.\n"
                    "Продолжить импорт?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                )
                if reply != QMessageBox.StandardButton.Yes:
                    return
            
            # Применяем настройки к UI
            frame_mode = settings_dict.get("frame_step_mode", "auto")
            self._frame_mode_combo.setCurrentIndex(0 if frame_mode == "auto" else 1)
            self._frame_step_spin.setValue(settings_dict.get("frame_step_manual", 5))
            
            self._conf_side_spin.setValue(settings_dict.get("conf_side", 0.5))
            self._conf_rube_spin.setValue(settings_dict.get("conf_rube", 0.7))
            self._conf_cnn_spin.setValue(settings_dict.get("conf_cnn", 0.6))
            self._iou_spin.setValue(settings_dict.get("iou_threshold", 0.1))
            
            self._dedup_track_spin.setValue(int(settings_dict.get("dedup_radius_track_m", 8)))
            self._dedup_final_spin.setValue(int(settings_dict.get("dedup_radius_final_m", 20)))
            self._dedup_azimuth_spin.setValue(int(settings_dict.get("dedup_azimuth_deg", 45)))
            
            # Task E: processing_mode, workers, ocr_* виджеты УДАЛЕНЫ (пропускаем с hasattr)
            if hasattr(self, '_processing_mode_combo'):
                proc_mode = settings_dict.get("processing_mode", "single_thread")
                mode_idx = {"single_thread": 0, "pipeline": 1, "process_pool": 2}.get(proc_mode, 0)
                self._processing_mode_combo.setCurrentIndex(mode_idx)
            
            if hasattr(self, '_workers_spin'):
                self._workers_spin.setValue(settings_dict.get("process_pool_workers", 0))
            
            # OCR settings (BLOCK 3.6)
            if hasattr(self, '_ocr_use_pool_toggle'):
                self._ocr_use_pool_toggle.set_checked(settings_dict.get("ocr_use_process_pool", True))
            if hasattr(self, '_ocr_workers_spin'):
                self._ocr_workers_spin.setValue(settings_dict.get("ocr_pool_workers", 1))
            
            # CUDA settings
            if hasattr(self, '_cuda_toggle'):
                self._cuda_toggle.set_checked(settings_dict.get("use_cuda", True))
            
            # Turn Geometry (BLOCK 3.6)
            if hasattr(self, '_turn_use_bearing_toggle'):
                self._turn_use_bearing_toggle.set_checked(settings_dict.get("turn_use_bearing_geometry", True))
            if hasattr(self, '_camera_fov_spin'):
                self._camera_fov_spin.setValue(settings_dict.get("camera_hfov_deg", 120.0))
            if hasattr(self, '_turn_ray_dist_spin'):
                self._turn_ray_dist_spin.setValue(int(settings_dict.get("turn_ray_max_distance_m", 40)))
            # BLOCK N.3: turn_radius_spin удалён
            
            self._log_toggle.set_checked(settings_dict.get("verbose_log", True))
            self._save_frames_toggle.set_checked(settings_dict.get("save_error_frames", False))
            
            theme = settings_dict.get("theme", "dark")
            self._theme_combo.setCurrentIndex(0 if theme == "dark" else 1)
            
            # CPU-инференс бэкенд (BLOCK M-FIX: BUG-4)
            if hasattr(self, '_cpu_backend_combo'):
                backend_map_rev = {"torch": 0, "onnx": 1, "openvino": 2}
                imported_backend = settings_dict.get("cpu_inference_backend", "torch")
                self._cpu_backend_combo.setCurrentIndex(
                    backend_map_rev.get(imported_backend, 0)
                )
            
            # Пороги lane detection (BLOCK M-FIX: BUG-5)
            if hasattr(self, '_lane_conf_detect_spin'):
                self._lane_conf_detect_spin.setValue(
                    settings_dict.get("lane_conf_detect", 0.65)
                )
            if hasattr(self, '_lane_conf_segment_spin'):
                self._lane_conf_segment_spin.setValue(
                    settings_dict.get("lane_conf_segment", 0.65)
                )
            
            print(f"[SettingsPage] Настройки импортированы из: {file_path}")
            
            # Сразу сохраняем импортированные настройки
            self._save()
            
            # Визуальная обратная связь
            from PyQt6.QtCore import QTimer
            btn = self.sender()
            original_text = btn.text()
            btn.setText("✓  Импортировано")
            btn.setEnabled(False)
            
            def restore():
                btn.setText(original_text)
                btn.setEnabled(True)
            
            QTimer.singleShot(1500, restore)
            
        except Exception as e:
            print(f"[SettingsPage] Ошибка импорта настроек: {e}")
            self._show_error_message(f"Ошибка импорта: {str(e)}")
    
    def _show_error_message(self, message: str):
        """Показать сообщение об ошибке."""
        from PyQt6.QtWidgets import QMessageBox
        msg_box = QMessageBox(self)
        msg_box.setIcon(QMessageBox.Icon.Warning)
        msg_box.setWindowTitle("Ошибка")
        msg_box.setText(message)
        msg_box.exec()