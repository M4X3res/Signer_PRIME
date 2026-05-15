from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont
from ui.themes.theme_manager import theme_manager, Theme


# Иконки — Unicode символы (не требуют внешних зависимостей)
NAV_ITEMS = [
    ("dashboard",   "⊞",  "Dashboard"),
    ("processing",  "▷",  "Обработка"),
    ("map",         "◎",  "Карта"),
    ("errors",      "◈",  "Ошибки"),
    ("settings",    "⚙",  "Настройки"),
]


class SidebarItem(QPushButton):
    def __init__(self, page_id: str, icon: str, label: str, parent=None):
        super().__init__(parent)
        self.page_id = page_id
        self._active = False

        self.setObjectName("SidebarItem")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setCheckable(False)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(10)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setObjectName("SidebarItemIcon")
        self._icon_lbl.setFixedWidth(18)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent; font-size: 15px;")

        self._text_lbl = QLabel(label)
        self._text_lbl.setObjectName("SidebarItemText")
        self._text_lbl.setStyleSheet("background: transparent; font-size: 12px;")

        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)
        layout.addStretch()

        self.setFixedHeight(38)
        self.setMinimumWidth(180)

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("active", "true" if active else "false")
        # Force QSS re-evaluation
        self.style().unpolish(self)
        self.style().polish(self)
        t = theme_manager.tokens
        if active:
            color = t["accent"]
        else:
            color = t["text_secondary"]
        self._icon_lbl.setStyleSheet(
            f"background: transparent; font-size: 15px; color: {color};"
        )
        self._text_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {color};"
        )


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(200)

        self._items: dict[str, SidebarItem] = {}
        self._current_page = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Logo block
        logo_block = QWidget()
        logo_block.setObjectName("SidebarLogoBlock")
        logo_block.setFixedHeight(64)
        logo_block.setStyleSheet("background: transparent;")
        logo_layout = QVBoxLayout(logo_block)
        logo_layout.setContentsMargins(16, 16, 16, 8)
        logo_layout.setSpacing(2)

        logo_lbl = QLabel("Signer")
        logo_lbl.setObjectName("SidebarLogo")
        logo_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_primary']};"
            "font-size: 13px; font-weight: 700; letter-spacing: 1.8px;"
            "background: transparent;"
        )

        ver_lbl = QLabel("v2.0")
        ver_lbl.setObjectName("SidebarVersion")
        ver_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 10px; background: transparent;"
        )

        logo_layout.addWidget(logo_lbl)
        logo_layout.addWidget(ver_lbl)
        root.addWidget(logo_block)

        # ── Thin separator
        sep = QFrame()
        sep.setObjectName("Separator")
        sep.setFixedHeight(1)
        sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
        root.addWidget(sep)

        # ── Section label
        nav_lbl = QLabel("НАВИГАЦИЯ")
        nav_lbl.setObjectName("SectionLabel")
        nav_lbl.setContentsMargins(16, 14, 0, 6)
        nav_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 9px; font-weight: 700; letter-spacing: 1.5px;"
            "background: transparent;"
        )
        root.addWidget(nav_lbl)

        # ── Nav items
        nav_items_widget = QWidget()
        nav_items_widget.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_items_widget)
        nav_layout.setContentsMargins(8, 0, 8, 0)
        nav_layout.setSpacing(2)

        for page_id, icon, label in NAV_ITEMS:
            item = SidebarItem(page_id, icon, label)
            item.clicked.connect(lambda _, pid=page_id: self._on_item_clicked(pid))
            nav_layout.addWidget(item)
            self._items[page_id] = item

        root.addWidget(nav_items_widget)
        root.addStretch()

        # ── Bottom separator
        sep2 = QFrame()
        sep2.setObjectName("Separator")
        sep2.setFixedHeight(1)
        sep2.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
        root.addWidget(sep2)

        # ── Theme toggle at bottom
        bottom = QWidget()
        bottom.setStyleSheet("background: transparent;")
        bottom.setFixedHeight(52)
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.setSpacing(8)

        moon_lbl = QLabel("☀" if theme_manager.current == Theme.LIGHT else "☾")
        moon_lbl.setObjectName("ThemeMoonLabel")
        moon_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_secondary']};"
            "font-size: 13px; background: transparent;"
        )

        theme_lbl = QLabel("Светлая" if theme_manager.current == Theme.LIGHT else "Тёмная")
        theme_lbl.setObjectName("ThemeLabel")
        theme_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_secondary']};"
            "font-size: 11px; background: transparent;"
        )

        self._moon_lbl = moon_lbl
        self._theme_lbl = theme_lbl

        theme_btn = QPushButton("переключить")
        theme_btn.setObjectName("BtnIcon")
        theme_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        theme_btn.setStyleSheet(
            f"color: {theme_manager.tokens['accent']};"
            "font-size: 10px; background: transparent; border: none;"
            "text-decoration: underline;"
        )
        theme_btn.clicked.connect(self._toggle_theme)

        bottom_layout.addWidget(moon_lbl)
        bottom_layout.addWidget(theme_lbl)
        bottom_layout.addStretch()
        bottom_layout.addWidget(theme_btn)
        root.addWidget(bottom)

        # Default page
        self.set_page("dashboard")

        # Listen to theme changes
        theme_manager.theme_changed.connect(self._on_theme_changed)

    def _on_item_clicked(self, page_id: str):
        self.set_page(page_id)
        self.page_changed.emit(page_id)

    def set_page(self, page_id: str):
        if self._current_page:
            self._items[self._current_page].set_active(False)
        self._current_page = page_id
        self._items[page_id].set_active(True)

    def _toggle_theme(self):
        from PyQt6.QtWidgets import QApplication
        theme_manager.toggle(QApplication.instance())

    def _on_theme_changed(self, theme_name: str):
        t = theme_manager.tokens
        is_dark = theme_name == "dark"
        self._moon_lbl.setText("☾" if is_dark else "☀")
        self._theme_lbl.setText("Тёмная" if is_dark else "Светлая")
        self.setStyleSheet("")  # Trigger repaint

        # Обновить цвета активных элементов
        for pid, item in self._items.items():
            item.set_active(pid == self._current_page)