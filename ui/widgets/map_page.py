"""
MapPage — страница карты.
Запускает Flask-сервер в ServerThread,
рендерит map.html через QWebEngineView.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QFrame
)
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWebEngineCore import QWebEngineSettings
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from ui.themes.theme_manager import theme_manager

MAP_PORT = 3000


class MapPage(QWidget):
    # Сигнал → MainWindow → VideoPlayer: прыгнуть к секунде
    jump_to_second = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

        self._server_thread = None
        self._server_ready  = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ─────────────────────────────────────────────
        topbar = QWidget()
        topbar.setFixedHeight(44)
        topbar.setStyleSheet(
            f"background: {theme_manager.tokens['bg_secondary']};"
            f"border-bottom: 1px solid {theme_manager.tokens['border_subtle']};"
        )
        tb_layout = QHBoxLayout(topbar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(10)

        tb_title = QLabel("КАРТА")
        tb_title.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 11px; font-weight: 700; letter-spacing: 1.4px;"
            "background: transparent;"
        )
        tb_layout.addWidget(tb_title)
        tb_layout.addStretch()

        self._reload_btn = QPushButton("↺  Перезагрузить")
        self._reload_btn.setObjectName("BtnSecondary")
        self._reload_btn.setFixedHeight(30)
        self._reload_btn.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.clicked.connect(self._reload_map)
        self._reload_btn.setEnabled(False)

        self._open_btn = QPushButton("⬡  В браузере")
        self._open_btn.setObjectName("BtnSecondary")
        self._open_btn.setFixedHeight(30)
        self._open_btn.setSizePolicy(
            QSizePolicy.Policy.MinimumExpanding, QSizePolicy.Policy.Fixed
        )
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_in_browser)
        self._open_btn.setEnabled(False)

        tb_layout.addWidget(self._reload_btn)
        tb_layout.addWidget(self._open_btn)
        root.addWidget(topbar)

        # ── Content: WebView или placeholder ───────────────────
        self._stack = QVBoxLayout()
        self._stack.setContentsMargins(0, 0, 0, 0)

        # Placeholder пока сервер не готов
        self._placeholder = _MapPlaceholder()
        self._stack.addWidget(self._placeholder)

        # WebEngineView
        self._webview = QWebEngineView()
        self._webview.setVisible(False)
        settings = self._webview.settings()
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.JavascriptEnabled, True
        )
        settings.setAttribute(
            QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
        )
        self._stack.addWidget(self._webview)

        root.addLayout(self._stack)

    # ── Server ─────────────────────────────────────────────────

    def start_server(self):
        """Вызывается из MainWindow когда данные готовы."""
        if self._server_thread and self._server_thread.isRunning():
            self._reload_map()
            return

        from server.server_thread import ServerThread
        self._server_thread = ServerThread(port=MAP_PORT, parent=self)
        self._server_thread.started_ok.connect(self._on_server_ready)
        self._server_thread.error.connect(self._on_server_error)

        # Подключаем колбэки для сервера
        try:
            from server.map_server import set_callbacks
            set_callbacks(
                on_jump=lambda s: self.jump_to_second.emit(s),
            )
        except Exception:
            pass

        self._placeholder.set_status("Запуск сервера карты…")
        self._server_thread.start()

    def _on_server_ready(self, port: int):
        self._server_ready = True
        self._placeholder.set_status("Загрузка карты…")
        # Небольшая задержка чтобы Flask успел поднять все роуты
        QTimer.singleShot(800, self._load_map)

    def _on_server_error(self, msg: str):
        self._placeholder.set_status(f"Ошибка сервера: {msg}", error=True)

    def _load_map(self):
        url = QUrl(f"http://127.0.0.1:{MAP_PORT}/")
        self._webview.setUrl(url)
        self._webview.loadFinished.connect(self._on_load_finished)

    def _on_load_finished(self, ok: bool):
        if ok:
            self._placeholder.setVisible(False)
            self._webview.setVisible(True)
            self._reload_btn.setEnabled(True)
            self._open_btn.setEnabled(True)
        else:
            self._placeholder.set_status("Не удалось загрузить карту", error=True)

    def _reload_map(self):
        self._webview.reload()

    def _open_in_browser(self):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{MAP_PORT}/")

    # ── Public API ──────────────────────────────────────────────

    def notify_new_sign(self, sign_dict: dict):
        """Вызывается из FinalHandler когда появился новый знак."""
        try:
            from server.map_server import emit_new_sign
            emit_new_sign(sign_dict)
        except Exception:
            pass

    def update_position(self, seconds: int):
        """Вызывается из VideoThread для обновления позиции на карте."""
        try:
            from server.map_server import emit_position
            emit_position(seconds)
        except Exception:
            pass


class _MapPlaceholder(QWidget):
    """Заглушка с анимированным статусом пока карта грузится."""

    def __init__(self, parent=None):
        super().__init__(parent)
        t = theme_manager.tokens

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self._icon = QLabel("◎")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 40px; background: transparent;"
        )

        self._title = QLabel("Карта")
        self._title.setObjectName("PageTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._status = QLabel("Запустите обработку для активации карты")
        self._status.setObjectName("PageSubtitle")
        self._status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(self._icon)
        layout.addSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._status)

    def set_status(self, text: str, error: bool = False):
        t = theme_manager.tokens
        color = t["error"] if error else t["text_secondary"]
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent;"
        )