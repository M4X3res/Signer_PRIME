from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QFrame, QSizePolicy,
    QGridLayout, QSpacerItem
)
from PyQt6.QtCore import Qt, pyqtSignal, QTimer
from PyQt6.QtGui import QFont
from ui.themes.theme_manager import theme_manager
from configs import config
import os


def _make_separator():
    sep = QFrame()
    sep.setFixedHeight(1)
    sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
    return sep


class FilePickerRow(QWidget):
    """Строка выбора файла/папки с лейблом, путём и кнопкой."""
    changed = pyqtSignal(str)

    def __init__(self, label: str, placeholder: str,
                 mode: str = "file",       # "file" | "dir" | "save"
                 file_filter: str = "",
                 parent=None):
        super().__init__(parent)
        self._mode = mode
        self._filter = file_filter
        self.setStyleSheet("background: transparent;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(5)

        lbl = QLabel(label.upper())
        lbl.setObjectName("FileLabel")

        row = QHBoxLayout()
        row.setSpacing(8)

        self._path_lbl = QLabel(placeholder)
        self._path_lbl.setObjectName("FilePathBox")
        self._path_lbl.setMinimumHeight(32)
        self._path_lbl.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        self._path_lbl.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )

        btn = QPushButton("Выбрать")
        btn.setObjectName("BtnSecondary")
        btn.setFixedWidth(80)
        btn.setFixedHeight(32)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(self._pick)

        row.addWidget(self._path_lbl)
        row.addWidget(btn)

        root.addWidget(lbl)
        root.addLayout(row)

    def _pick(self):
        path = ""
        if self._mode == "file":
            result = QFileDialog.getOpenFileName(
                self, "Выбрать файл", "", self._filter
            )
            path = result[0]
        elif self._mode == "dir":
            path = QFileDialog.getExistingDirectory(self, "Выбрать папку", "")
        elif self._mode == "save":
            result = QFileDialog.getSaveFileName(
                self, "Создать или выбрать файл", "", self._filter
            )
            path = result[0]

        if path:
            self.set_path(path)
            self.changed.emit(path)

    def set_path(self, path: str):
        t = theme_manager.tokens
        display = path if len(path) < 60 else "…" + path[-57:]
        self._path_lbl.setText(display)
        self._path_lbl.setToolTip(path)
        self._path_lbl.setStyleSheet(
            f"background-color: {t['bg_tertiary']}; border: 1px solid {t['border_subtle']};"
            f"border-radius: 6px; padding: 8px 12px; color: {t['text_primary']};"
            "font-size: 11px; font-family: 'Cascadia Code','Consolas',monospace;"
        )

    def path(self) -> str:
        return self._path_lbl.toolTip()


class StatCard(QWidget):
    """Маленькая карточка с числовым показателем."""
    def __init__(self, value: str, label: str, accent: bool = False, parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.setFixedHeight(90)

        t = theme_manager.tokens
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(2)

        # Accent top line
        if accent:
            bar = QFrame()
            bar.setObjectName("AccentLine")
            bar.setFixedHeight(2)
            bar.setStyleSheet(f"background: {t['accent']}; border-radius: 1px;")
            root.addWidget(bar)

        val_lbl = QLabel(value)
        val_lbl.setObjectName("StatValue")

        lbl_lbl = QLabel(label.upper())
        lbl_lbl.setObjectName("StatLabel")

        root.addWidget(val_lbl)
        root.addWidget(lbl_lbl)

        self._val = val_lbl

    def set_value(self, v: str):
        self._val.setText(v)


class DashboardPage(QWidget):
    # Сигналы для ButtonsHandler
    start_requested = pyqtSignal()
    multiple_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        # ── Page header
        header = QHBoxLayout()
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")

        subtitle = QLabel("Настройте источники данных и запустите обработку")
        subtitle.setObjectName("PageSubtitle")

        header_texts = QVBoxLayout()
        header_texts.setSpacing(2)
        header_texts.addWidget(title)
        header_texts.addWidget(subtitle)
        header.addLayout(header_texts)
        header.addStretch()

        self.btn_start = QPushButton("▷   Начать обработку")
        self.btn_start.setObjectName("BtnPrimary")
        self.btn_start.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self.btn_start.setMinimumHeight(38)
        self.btn_start.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self.start_requested)

        self.btn_multi = QPushButton("⊞   Массовая обработка")
        self.btn_multi.setObjectName("BtnSecondary")
        self.btn_multi.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self.btn_multi.setMinimumHeight(38)
        self.btn_multi.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_multi.clicked.connect(self.multiple_requested)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        btn_row.addWidget(self.btn_multi)
        btn_row.addWidget(self.btn_start)

        header.addLayout(btn_row)
        root.addLayout(header)
        root.addSpacing(24)

        # ── Stat cards row
        stats_row = QHBoxLayout()
        stats_row.setSpacing(12)

        self._stat_videos = StatCard("—", "видео файлов", accent=True)
        self._stat_gpx    = StatCard("—", "GPS точек")
        self._stat_ready  = StatCard("—", "готово к запуску")

        stats_row.addWidget(self._stat_videos)
        stats_row.addWidget(self._stat_gpx)
        stats_row.addWidget(self._stat_ready)
        root.addLayout(stats_row)
        root.addSpacing(24)

        # ── Files section
        files_card = QWidget()
        files_card.setObjectName("Card")
        files_layout = QVBoxLayout(files_card)
        files_layout.setContentsMargins(20, 16, 20, 20)
        files_layout.setSpacing(16)

        files_title = QLabel("ИСТОЧНИКИ ДАННЫХ")
        files_title.setObjectName("CardTitle")

        files_layout.addWidget(files_title)
        files_layout.addWidget(_make_separator())

        # Video folder
        self._pick_video = FilePickerRow(
            "Папка с видео",
            "Путь не выбран…",
            mode="dir",
        )
        self._pick_video.changed.connect(self._on_video_changed)

        # GPX
        self._pick_gpx = FilePickerRow(
            "GPX трек",
            "Путь не выбран…",
            mode="file",
            file_filter="GPX файлы (*.gpx)",
        )
        self._pick_gpx.changed.connect(self._on_gpx_changed)

        # GeoJSON
        self._pick_geojson = FilePickerRow(
            "GeoJSON (создать или выбрать)",
            "Путь не выбран…",
            mode="save",
            file_filter="GeoJSON (*.geojson)",
        )
        self._pick_geojson.changed.connect(self._on_geojson_changed)

        # Extra layer (optional)
        self._pick_extra = FilePickerRow(
            "Дополнительный слой (опционально)",
            "Не выбран",
            mode="file",
            file_filter="GeoJSON / JSON (*.geojson *.json)",
        )
        self._pick_extra.changed.connect(self._on_extra_changed)

        files_layout.addWidget(self._pick_video)
        files_layout.addWidget(self._pick_gpx)
        files_layout.addWidget(self._pick_geojson)
        files_layout.addWidget(self._pick_extra)

        root.addWidget(files_card)
        root.addSpacing(16)

        # ── Status line
        self._status_lbl = QLabel("Выберите все необходимые файлы для начала работы")
        self._status_lbl.setObjectName("PageSubtitle")
        root.addWidget(self._status_lbl)

        root.addStretch()

        # ── Restore paths from config if already set
        QTimer.singleShot(100, self._restore_from_config)

    # ── Internal helpers ───────────────────────────────────────

    def _restore_from_config(self):
        if config.PATH_TO_VIDEO:
            self._pick_video.set_path(config.PATH_TO_VIDEO)
        if config.PATH_TO_GPX:
            self._pick_gpx.set_path(config.PATH_TO_GPX)
        if config.PATH_TO_GEOJSON:
            self._pick_geojson.set_path(config.PATH_TO_GEOJSON)
        self._update_stats()
        self._check_ready()

    def _on_video_changed(self, path: str):
        config.PATH_TO_VIDEO = path.replace("/", "\\") + "\\"
        try:
            config.VIDEOS = [
                f for f in os.listdir(config.PATH_TO_VIDEO)
                if f.lower().endswith(".mp4")
            ]
        except Exception:
            config.VIDEOS = []
        self._update_stats()
        self._check_ready()

    def _on_gpx_changed(self, path: str):
        config.PATH_TO_GPX = path.replace("/", "\\")
        self._update_stats()
        self._check_ready()

    def _on_geojson_changed(self, path: str):
        if not path.endswith(".geojson"):
            path += ".geojson"
        config.PATH_TO_GEOJSON = path
        self._check_ready()

    def _on_extra_changed(self, path: str):
        config.PATH_TO_EXTRA_LAYERS = path.replace("/", "\\")

    def _update_stats(self):
        video_count = len(config.VIDEOS) if config.VIDEOS else 0
        self._stat_videos.set_value(str(video_count) if video_count else "—")

        gpx_pts = "—"
        if config.PATH_TO_GPX and os.path.exists(config.PATH_TO_GPX):
            try:
                import gpxpy
                with open(config.PATH_TO_GPX, "r") as f:
                    gpx = gpxpy.parse(f)
                pts = sum(
                    len(seg.points)
                    for trk in gpx.tracks
                    for seg in trk.segments
                )
                gpx_pts = f"{pts:,}".replace(",", " ")
            except Exception:
                gpx_pts = "err"
        self._stat_gpx.set_value(gpx_pts)

    def _check_ready(self):
        ok = (
            len(config.PATH_TO_VIDEO) > 3
            and len(config.PATH_TO_GPX) > 3
            and len(config.PATH_TO_GEOJSON) > 3
        )
        self.btn_start.setEnabled(ok)
        t = theme_manager.tokens
        if ok:
            self._status_lbl.setText("✓  Все файлы выбраны — можно запускать обработку")
            self._status_lbl.setStyleSheet(f"color: {t['success']}; font-size: 12px;")
            self._stat_ready.set_value("✓")
        else:
            self._status_lbl.setText("Выберите все необходимые файлы для начала работы")
            self._status_lbl.setStyleSheet(f"color: {t['text_secondary']}; font-size: 12px;")
            self._stat_ready.set_value("—")

    def set_processing_active(self, active: bool):
        """Вызывается когда обработка запущена/завершена."""
        self.btn_start.setEnabled(not active)
        self.btn_multi.setEnabled(not active)
        self._pick_video.setEnabled(not active)
        self._pick_gpx.setEnabled(not active)
        self._pick_geojson.setEnabled(not active)