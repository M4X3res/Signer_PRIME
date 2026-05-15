from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QSpinBox, QDoubleSpinBox,
    QFrame, QCheckBox, QComboBox, QScrollArea,
    QSizePolicy, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal
from ui.themes.theme_manager import theme_manager, Theme
from configs import config


def _separator():
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
    return sep


class SettingsRow(QWidget):
    """Одна строка настройки: лейбл + описание | контрол."""
    def __init__(self, label: str, hint: str, control: QWidget, parent=None):
        super().__init__(parent)
        self.setStyleSheet("background: transparent;")
        self.setFixedHeight(56)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 0, 20, 0)
        layout.setSpacing(12)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        lbl = QLabel(label)
        lbl.setObjectName("SettingsLabel")

        hint_lbl = QLabel(hint)
        hint_lbl.setObjectName("SettingsHint")

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

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

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
        self._theme_combo.setCurrentIndex(
            0 if theme_manager.current == Theme.DARK else 1
        )
        self._theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        ui_group.add_row(
            "Тема оформления",
            "Тёмная или светлая тема приложения",
            self._theme_combo,
        )

        content_layout.addWidget(ui_group)

        # ── Group: Обработка ────────────────────────────────────
        proc_group = SettingsGroup("Обработка видео")

        self._frame_step_spin = QSpinBox()
        self._frame_step_spin.setRange(1, 60)
        self._frame_step_spin.setValue(config.FRAME_STEP)
        self._frame_step_spin.setFixedWidth(90)
        self._frame_step_spin.setSuffix("  кадров")
        self._frame_step_spin.valueChanged.connect(
            lambda v: setattr(config, "FRAME_STEP", v)
        )
        proc_group.add_row(
            "Шаг кадра",
            "Каждый N-й кадр отправляется в детектор",
            self._frame_step_spin,
        )

        self._conf_spin = QDoubleSpinBox()
        self._conf_spin.setRange(0.1, 1.0)
        self._conf_spin.setSingleStep(0.05)
        self._conf_spin.setDecimals(2)
        self._conf_spin.setValue(0.50)
        self._conf_spin.setFixedWidth(90)
        proc_group.add_row(
            "Порог уверенности",
            "Минимальная уверенность модели (conf threshold)",
            self._conf_spin,
        )

        self._iou_spin = QDoubleSpinBox()
        self._iou_spin.setRange(0.1, 1.0)
        self._iou_spin.setSingleStep(0.05)
        self._iou_spin.setDecimals(2)
        self._iou_spin.setValue(0.10)
        self._iou_spin.setFixedWidth(90)
        proc_group.add_row(
            "IoU порог",
            "Non-Maximum Suppression: порог перекрытия боксов",
            self._iou_spin,
        )

        content_layout.addWidget(proc_group)

        # ── Group: GPS ──────────────────────────────────────────
        gps_group = SettingsGroup("GPS и координаты")

        self._dup_radius_spin = QSpinBox()
        self._dup_radius_spin.setRange(5, 200)
        self._dup_radius_spin.setValue(40)
        self._dup_radius_spin.setSuffix("  м")
        self._dup_radius_spin.setFixedWidth(90)
        gps_group.add_row(
            "Радиус дедупликации",
            "Два знака одного типа в этом радиусе считаются дублем",
            self._dup_radius_spin,
        )

        content_layout.addWidget(gps_group)

        # ── Group: Логирование ──────────────────────────────────
        log_group = SettingsGroup("Логирование")

        self._log_toggle = ToggleButton(True)
        log_group.add_row(
            "Подробный лог",
            "Выводить информацию о каждом обнаруженном знаке",
            self._log_toggle,
        )

        self._save_frames_toggle = ToggleButton(False)
        log_group.add_row(
            "Сохранять кадры ошибок",
            "Записывать кадры с неуверенными детекциями в ./errorData",
            self._save_frames_toggle,
        )

        content_layout.addWidget(log_group)

        content_layout.addStretch()

        # ── Reset + Save buttons ────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        reset_btn = QPushButton("Сбросить")
        reset_btn.setObjectName("BtnSecondary")
        reset_btn.setFixedHeight(36)
        reset_btn.setMinimumWidth(100)
        reset_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        reset_btn.clicked.connect(self._reset)

        save_btn = QPushButton("Сохранить")
        save_btn.setObjectName("BtnPrimary")
        save_btn.setFixedHeight(36)
        save_btn.setMinimumWidth(100)
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.clicked.connect(self._save)

        btn_row.addWidget(reset_btn)
        btn_row.addSpacing(8)
        btn_row.addWidget(save_btn)
        content_layout.addLayout(btn_row)

        scroll.setWidget(content)
        outer.addWidget(scroll)

    # ── Slots ──────────────────────────────────────────────────

    def _on_theme_changed(self, index: int):
        from PyQt6.QtWidgets import QApplication
        t = Theme.DARK if index == 0 else Theme.LIGHT
        theme_manager.set_theme(t, QApplication.instance())
        self.theme_changed.emit(t.value)

    def _reset(self):
        self._frame_step_spin.setValue(5)
        self._conf_spin.setValue(0.50)
        self._iou_spin.setValue(0.10)
        self._dup_radius_spin.setValue(40)
        self._log_toggle.set_checked(True)
        self._save_frames_toggle.set_checked(False)

    def _save(self):
        config.FRAME_STEP = self._frame_step_spin.value()
        # Остальные параметры применяются на лету через valueChanged

    # Public getters
    def conf_threshold(self) -> float:
        return self._conf_spin.value()

    def iou_threshold(self) -> float:
        return self._iou_spin.value()

    def dup_radius(self) -> int:
        return self._dup_radius_spin.value()

    def verbose_log(self) -> bool:
        return self._log_toggle.is_checked()

    def save_error_frames(self) -> bool:
        return self._save_frames_toggle.is_checked()