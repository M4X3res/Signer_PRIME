from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QLabel, QStackedWidget, QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtGui import QPixmap

from ui.themes.theme_manager import theme_manager
from ui.widgets.sidebar import Sidebar
from ui.widgets.dashboard_page import DashboardPage
from ui.widgets.processing_page import ProcessingPage
from ui.widgets.settings_page import SettingsPage
from ui.widgets.placeholder_pages import MapPage, ErrorEditorPage


class StatusBar(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("StatusBar")
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 0, 16, 0)
        layout.setSpacing(16)

        self._status = QLabel("Готов к работе")
        self._status.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']}; font-size: 11px;"
            "background: transparent;"
        )

        self._dot = QLabel("●")
        self._dot.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']}; font-size: 8px;"
            "background: transparent;"
        )

        self._right = QLabel("Signer")
        self._right.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']}; font-size: 11px;"
            "background: transparent;"
        )

        layout.addWidget(self._dot)
        layout.addWidget(self._status)
        layout.addStretch()
        layout.addWidget(self._right)

    def set_status(self, text: str, color: str = ""):
        t = theme_manager.tokens
        c = color or t["text_tertiary"]
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {c}; font-size: 11px; background: transparent;"
        )
        self._dot.setStyleSheet(
            f"color: {c}; font-size: 8px; background: transparent;"
        )


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Signer")
        self.setMinimumSize(1200, 720)
        self.resize(1400, 860)

        # ── Central widget ──────────────────────────────────────
        central = QWidget()
        self.setCentralWidget(central)
        root = QHBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Sidebar ─────────────────────────────────────────────
        self.sidebar = Sidebar()
        self.sidebar.page_changed.connect(self._switch_page)
        root.addWidget(self.sidebar)

        # ── Right side: stacked pages + status bar ──────────────
        right = QWidget()
        right.setObjectName("ContentArea")
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Pages
        self._pages = QStackedWidget()
        self._pages.setObjectName("ContentArea")

        self.page_dashboard   = DashboardPage()
        self.page_processing  = ProcessingPage()
        self.page_map         = MapPage()
        self.page_errors      = ErrorEditorPage()
        self.page_settings    = SettingsPage()

        self._pages.addWidget(self.page_dashboard)   # index 0
        self._pages.addWidget(self.page_processing)  # index 1
        self._pages.addWidget(self.page_map)          # index 2
        self._pages.addWidget(self.page_errors)       # index 3
        self._pages.addWidget(self.page_settings)     # index 4

        self._page_map = {
            "dashboard":  0,
            "processing": 1,
            "map":        2,
            "errors":     3,
            "settings":   4,
        }

        right_layout.addWidget(self._pages)

        # Thin separator above status bar
        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
        right_layout.addWidget(sep)

        # Status bar
        self.status_bar = StatusBar()
        right_layout.addWidget(self.status_bar)

        root.addWidget(right)

        # ── Wire dashboard signals ──────────────────────────────
        self.page_dashboard.start_requested.connect(self._on_start)
        self.page_dashboard.multiple_requested.connect(self._on_multiple)
        self.page_processing.finish_requested.connect(self._on_finish)

        # ── Apply theme ─────────────────────────────────────────
        from PyQt6.QtWidgets import QApplication
        theme_manager.apply(QApplication.instance())

    # ── Page switching ─────────────────────────────────────────

    def _switch_page(self, page_id: str):
        idx = self._page_map.get(page_id, 0)
        self._pages.setCurrentIndex(idx)

    # ── Processing wiring (to be connected to ButtonsHandler) ──

    def _on_start(self):
        """Вызывается когда пользователь нажимает 'Начать обработку'."""
        self._switch_page("processing")
        self.sidebar.set_page("processing")
        self.page_processing.set_active(True)
        self.page_dashboard.set_processing_active(True)
        t = theme_manager.tokens
        self.status_bar.set_status("Обработка запущена…", t["accent"])
        self.page_processing.log("Обработка запущена", "success")
        # Здесь будет вызов start_processing() из ButtonsHandler

    def _on_multiple(self):
        """Массовая обработка."""
        self._switch_page("processing")
        self.sidebar.set_page("processing")
        self.page_processing.set_active(True)
        self.page_dashboard.set_processing_active(True)
        t = theme_manager.tokens
        self.status_bar.set_status("Массовая обработка…", t["accent"])
        self.page_processing.log("Массовая обработка запущена", "success")

    def _on_finish(self):
        """Завершение обработки."""
        self.page_processing.set_active(False)
        self.page_dashboard.set_processing_active(False)
        t = theme_manager.tokens
        self.status_bar.set_status("Обработка завершена", t["success"])
        self.page_processing.log("Обработка завершена — результат сохранён в GeoJSON", "success")
        self.page_processing.set_progress(100)

    # ── Public API for PlayerHandler integration ────────────────

    def update_frame(self, pixmap: QPixmap):
        self.page_processing.set_frame(pixmap)

    def update_progress(self, value: int, eta: str = ""):
        self.page_processing.set_progress(value, eta)

    def update_stats(self, frames: int, signs: int, fps: float,
                     video_idx: int, video_total: int):
        self.page_processing.set_stats(frames, signs, fps, video_idx, video_total)

    def log(self, msg: str, level: str = "info"):
        self.page_processing.log(msg, level)

    def set_status(self, text: str, color: str = ""):
        self.status_bar.set_status(text, color)