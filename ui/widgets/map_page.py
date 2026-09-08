"""
MapPage — страница карты.
Запускает Flask-сервер в ServerThread,
рендерит map.html через QWebEngineView.

ВАЖНО: QWebEngineView импортируется ЛЕНИВО внутри метода start_server(),
потому что он должен быть импортирован только после того как
QApplication создана с флагом AA_ShareOpenGLContexts.
"""
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QPushButton, QSizePolicy, QFrame, QDialog
)
from PyQt6.QtCore import Qt, QUrl, QTimer, pyqtSignal
from ui.themes.theme_manager import theme_manager

MAP_PORT = 3000


class MapPage(QWidget):
    jump_to_second = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

        self._server_thread = None
        self._server_ready  = False
        self._webview       = None  # создаётся лениво в _load_map()

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Topbar ─────────────────────────────────────────────
        self._topbar = QWidget()
        self._topbar.setMinimumHeight(44)  # Минимальная высота
        self._topbar.setMaximumHeight(52)  # Максимальная высота
        tb_layout = QHBoxLayout(self._topbar)
        tb_layout.setContentsMargins(16, 0, 16, 0)
        tb_layout.setSpacing(10)

        self._tb_title = QLabel("КАРТА")
        self._tb_title.setStyleSheet(
            "font-size: 11px; font-weight: 700; letter-spacing: 1.4px;"
            "background: transparent;"
        )
        tb_layout.addWidget(self._tb_title)
        tb_layout.addStretch()

        self._reload_btn = QPushButton("↺  Перезагрузить")
        self._reload_btn.setObjectName("BtnSecondary")
        # ЗАДАЧА 4: Убираем setMinimumHeight - используем QSS (36px)
        self._reload_btn.setFixedWidth(180)  # Увеличено — текст не помещался (см. UI-фикс кнопок)
        self._reload_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._reload_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._reload_btn.clicked.connect(self._reload_map)
        self._reload_btn.setEnabled(False)

        self._open_btn = QPushButton("⬡  В браузере")
        self._open_btn.setObjectName("BtnSecondary")
        # ЗАДАЧА 4: Убираем setMinimumHeight - используем QSS (36px)
        self._open_btn.setFixedWidth(180)  # Увеличено — текст не помещался (см. UI-фикс кнопок)
        self._open_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        self._open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self._open_btn.clicked.connect(self._open_in_browser)
        self._open_btn.setEnabled(False)

        tb_layout.addWidget(self._reload_btn)
        tb_layout.addWidget(self._open_btn)
        root.addWidget(self._topbar)

        # ── Content: placeholder (WebView добавляется позже) ───
        self._content_layout = QVBoxLayout()
        self._content_layout.setContentsMargins(0, 0, 0, 0)

        self._placeholder = _MapPlaceholder()
        self._content_layout.addWidget(self._placeholder)

        root.addLayout(self._content_layout)

        self._restyle_topbar()
        theme_manager.theme_changed.connect(self._restyle_topbar)
        theme_manager.theme_changed.connect(self._on_theme_changed)

    # ── Theme ───────────────────────────────────────────────────

    def _restyle_topbar(self) -> None:
        """Перекрашивает topbar и заголовок при смене темы."""
        t = theme_manager.tokens
        self._topbar.setStyleSheet(
            f"background: {t['bg_secondary']};"
            f"border-bottom: 1px solid {t['border_subtle']};"
        )
        self._tb_title.setStyleSheet(
            f"color: {t['text_tertiary']};"
            "font-size: 11px; font-weight: 700; letter-spacing: 1.4px;"
            "background: transparent;"
        )

    def _on_theme_changed(self, theme_name: str) -> None:
        """Пробрасывает смену темы в открытую веб-страницу карты через SocketIO."""
        try:
            from server.map_server import emit_theme_changed
            emit_theme_changed(theme_name)
        except Exception:
            pass

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
        QTimer.singleShot(800, self._load_map)

    def _on_server_error(self, msg: str):
        self._placeholder.set_status(f"Ошибка сервера: {msg}", error=True)

    def _load_map(self):
        """Создаёт QWebEngineView лениво — только здесь."""
        if self._webview is None:
            # Импорт ЗДЕСЬ, не на уровне модуля
            from PyQt6.QtWebEngineWidgets import QWebEngineView
            from PyQt6.QtWebEngineCore import QWebEngineSettings, QWebEngineProfile, QWebEnginePage

            # ЗАДАЧА 5.2 + 5.3: Определяем кастомную страницу с поддержкой fullscreen и popup
            class MapWebEnginePage(QWebEnginePage):
                """Кастомная страница с поддержкой fullscreen и popup окон."""
                def __init__(self, profile, parent_view):
                    super().__init__(profile, parent_view)
                    self._popup_windows = []
                
                def createWindow(self, _type):
                    """ЗАДАЧА 5.3: Создаёт popup окно для window.open()."""
                    dialog = QDialog(self.view().window())
                    dialog.setWindowTitle("Видеоплеер — Signer v2")
                    dialog.resize(1280, 720)
                    
                    layout = QVBoxLayout(dialog)
                    layout.setContentsMargins(0, 0, 0, 0)
                    
                    popup_view = QWebEngineView(dialog)
                    popup_page = QWebEnginePage(self.profile(), popup_view)
                    popup_view.setPage(popup_page)
                    layout.addWidget(popup_view)
                    dialog.show()
                    
                    # Сохраняем ссылку для предотвращения GC
                    self._popup_windows.append((dialog, popup_view, popup_page))
                    
                    def on_finished():
                        try:
                            self._popup_windows.remove((dialog, popup_view, popup_page))
                        except ValueError:
                            pass
                    dialog.finished.connect(on_finished)
                    
                    return popup_page

            self._webview = QWebEngineView()
            self._webview.setVisible(False)

            # Получаем профиль для настройки
            profile = self._webview.page().profile()
            
            # ЗАДАЧА 5.2 + 5.3: Создаём кастомную страницу
            page = MapWebEnginePage(profile, self._webview)
            self._webview.setPage(page)
            
            # Настройки для работы с медиа
            settings = self._webview.settings()
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.JavascriptEnabled, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessRemoteUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.LocalContentCanAccessFileUrls, True
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.PlaybackRequiresUserGesture, False
            )
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.AllowRunningInsecureContent, True
            )
            
            # ЗАДАЧА 5.2: Включаем поддержку Fullscreen API
            settings.setAttribute(
                QWebEngineSettings.WebAttribute.FullScreenSupportEnabled, True
            )
            
            # Разрешаем автовоспроизведение медиа
            try:
                settings.setAttribute(
                    QWebEngineSettings.WebAttribute.MediaStreamEnabled, True
                )
            except AttributeError:
                pass  # Старая версия PyQt6

            # ЗАДАЧА 5.2: Подключаем обработчик fullscreen запросов
            page.fullScreenRequested.connect(self._on_fullscreen_requested)

            self._content_layout.addWidget(self._webview)
            self._webview.loadFinished.connect(self._on_load_finished)

        url = QUrl(f"http://127.0.0.1:{MAP_PORT}/")
        # Добавляем query-параметр theme для начальной стилизации страницы
        current_theme = theme_manager.current.value  # "dark" или "light"
        url = QUrl(f"http://127.0.0.1:{MAP_PORT}/?theme={current_theme}")
        self._webview.setUrl(url)

    def _on_load_finished(self, ok: bool):
        if ok:
            self._placeholder.setVisible(False)
            self._webview.setVisible(True)
            self._reload_btn.setEnabled(True)
            self._open_btn.setEnabled(True)
        else:
            self._placeholder.set_status("Не удалось загрузить карту", error=True)

    def _on_fullscreen_requested(self, request):
        """
        ЗАДАЧА 5.2: Обработчик fullscreen запросов от видеоплеера.
        
        При нажатии кнопки fullscreen в видеоплеере разворачивает
        всё главное окно приложения на весь экран. При выходе из fullscreen
        (через Esc или повторное нажатие) возвращает нормальный размер.
        """
        request.accept()
        
        main_window = self.window()
        
        if request.toggleOn():
            # Включаем fullscreen
            main_window.showFullScreen()
        else:
            # Выключаем fullscreen
            main_window.showNormal()

    def _reload_map(self):
        if self._webview:
            self._webview.reload()

    def _open_in_browser(self):
        import webbrowser
        webbrowser.open(f"http://127.0.0.1:{MAP_PORT}/")

    # ── Public API ──────────────────────────────────────────────

    def notify_new_sign(self, sign_dict: dict):
        try:
            from server.map_server import emit_new_sign
            emit_new_sign(sign_dict)
        except Exception:
            pass

    def update_position(self, seconds: int):
        try:
            from server.map_server import emit_position
            emit_position(seconds)
        except Exception:
            pass

    def stop_server(self):
        """Остановка Flask-сервера и ServerThread при закрытии приложения."""
        if self._server_thread and self._server_thread.isRunning():
            try:
                print("[MapPage] Останавливаем Flask-сервер...")
                
                # Запрашиваем остановку потока
                self._server_thread.quit()
                
                # Ждём завершения с таймаутом
                if not self._server_thread.wait(2000):  # 2 секунды
                    print("[MapPage] WARNING: ServerThread не остановился за 2 сек, принудительное завершение")
                    self._server_thread.terminate()
                    self._server_thread.wait(1000)
                
                self._server_thread = None
                self._server_ready = False
                print("[MapPage] Flask-сервер остановлен")
            except Exception as e:
                print(f"[MapPage] Ошибка при остановке сервера: {e}")


class _MapPlaceholder(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        self._icon = QLabel("◎")
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

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

        self._restyle()
        theme_manager.theme_changed.connect(self._restyle)

    def _restyle(self):
        t = theme_manager.tokens
        self._icon.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 40px; background: transparent;"
        )

    def set_status(self, text: str, error: bool = False):
        t = theme_manager.tokens
        color = t["error"] if error else t["text_secondary"]
        self._status.setText(text)
        self._status.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent;"
        )