from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QSizePolicy, QFrame
)
from PyQt6.QtCore import Qt, pyqtSignal, QSize
from PyQt6.QtGui import QIcon, QFont
from ui.themes.theme_manager import theme_manager, Theme
from ui.widgets.toggle_switch import ToggleSwitch
from ui.widgets.control_styles import line_icon
from app.version import APP_VERSION


# Иконки — Unicode символы (не требуют внешних зависимостей)
NAV_ITEMS = [
    ("dashboard",   "⊞",  "Обзор"),
    ("processing",  "▷",  "Обработка"),
    ("map",         "◎",  "Карта"),
    ("errors",      "◈",  "Редактор знаков"),
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
        self.setAccessibleName(label)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 12, 0)
        layout.setSpacing(10)

        self._icon_lbl = QLabel(icon)
        self._icon_lbl.setObjectName("SidebarItemIcon")
        self._icon_lbl.setFixedWidth(18)
        self._icon_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._icon_lbl.setStyleSheet("background: transparent; font-size: 15px;")

        self._text_lbl = QLabel(label)
        self._text_lbl.setObjectName("SidebarItemText")
        self._text_lbl.setStyleSheet("background: transparent; font-size: 12px;")
        self._text_lbl.setWordWrap(False)  # Не переносим в sidebar
        self._text_lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

        layout.addWidget(self._icon_lbl)
        layout.addWidget(self._text_lbl)
        layout.addStretch()

        self.setFixedHeight(44)
        self.setMinimumWidth(0)
        self.set_active(False)

    def set_active(self, active: bool):
        self._active = active
        self.setProperty("active", "true" if active else "false")
        # Force QSS re-evaluation
        self.style().unpolish(self)
        self.style().polish(self)
        t = theme_manager.tokens
        background = t['accent_subtle'] if active else 'transparent'
        border = t['accent_muted'] if active else 'transparent'
        self.setStyleSheet(f"""
            QPushButton#SidebarItem {{ background: {background}; border: 1px solid {border};
                border-radius: 10px; padding: 0; margin: 0; min-width: 0; min-height: 42px; max-height: 42px; text-align: left; }}
            QPushButton#SidebarItem:hover {{ background: {t['bg_tertiary']}; }}
            QPushButton#SidebarItem:focus {{ border-color: {t['accent']}; }}
        """)
        if active:
            color = t["accent"]
        else:
            color = t["text_secondary"]
        self._icon_lbl.setStyleSheet(
            f"background: transparent; font-size: 15px; color: {color};"
        )
        self._text_lbl.setStyleSheet(
            f"background: transparent; font-size: 12px; color: {color}; font-weight: {'600' if active else '400'};"
        )
        self._icon_lbl.setPixmap(line_icon(self.page_id, color).pixmap(QSize(18, 18)))


class Sidebar(QWidget):
    page_changed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(216)

        self._items: dict[str, SidebarItem] = {}
        self._current_page = ""

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── Logo block
        logo_block = QWidget()
        logo_block.setObjectName("SidebarLogoBlock")
        logo_block.setFixedHeight(92)
        logo_block.setStyleSheet("background: transparent;")
        logo_layout = QHBoxLayout(logo_block)
        logo_layout.setContentsMargins(18, 18, 16, 18)
        logo_layout.setSpacing(10)
        self._brand_mark = QLabel()
        self._brand_mark.setFixedSize(36, 36)
        self._brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        logo_layout.addWidget(self._brand_mark)
        brand_text = QVBoxLayout()
        brand_text.setSpacing(3)

        self._logo_lbl = QLabel("Signer")
        self._logo_lbl.setObjectName("SidebarLogo")
        self._logo_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_primary']};"
            "font-size: 13px; font-weight: 700; letter-spacing: 1.8px;"
            "background: transparent;"
        )

        self._ver_lbl = QLabel(f"PRIME  ·  v{APP_VERSION}")
        self._ver_lbl.setObjectName("SidebarVersion")
        self._ver_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 10px; background: transparent;"
        )

        brand_text.addWidget(self._logo_lbl)
        brand_text.addWidget(self._ver_lbl)
        logo_layout.addLayout(brand_text)
        root.addWidget(logo_block)

        # ── Thin separator
        self._sep = QFrame()
        self._sep.setObjectName("Separator")
        self._sep.setFixedHeight(1)
        self._sep.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
        root.addWidget(self._sep)

        # ── Section label
        self._nav_lbl = QLabel("НАВИГАЦИЯ")
        self._nav_lbl.setObjectName("SectionLabel")
        self._nav_lbl.setContentsMargins(22, 20, 0, 10)
        self._nav_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_tertiary']};"
            "font-size: 9px; font-weight: 700; letter-spacing: 1.5px;"
            "background: transparent;"
        )
        root.addWidget(self._nav_lbl)

        # ── Nav items
        nav_items_widget = QWidget()
        nav_items_widget.setStyleSheet("background: transparent;")
        nav_layout = QVBoxLayout(nav_items_widget)
        nav_layout.setContentsMargins(12, 0, 12, 0)
        nav_layout.setSpacing(6)

        for page_id, icon, label in NAV_ITEMS:
            item = SidebarItem(page_id, icon, label)
            item.clicked.connect(lambda _, pid=page_id: self._on_item_clicked(pid))
            nav_layout.addWidget(item)
            self._items[page_id] = item

        root.addWidget(nav_items_widget)
        root.addStretch()

        # ── Bottom separator
        self._sep2 = QFrame()
        self._sep2.setObjectName("Separator")
        self._sep2.setFixedHeight(1)
        self._sep2.setStyleSheet(f"background: {theme_manager.tokens['border_subtle']};")
        root.addWidget(self._sep2)

        # ── Theme toggle at bottom
        bottom = QWidget()
        bottom.setStyleSheet("background: transparent;")
        bottom.setMinimumHeight(52)  # Минимальная высота
        bottom_layout = QHBoxLayout(bottom)
        bottom_layout.setContentsMargins(16, 12, 16, 12)
        bottom_layout.setSpacing(8)

        moon_lbl = QLabel("☀" if theme_manager.current == Theme.LIGHT else "☾")
        moon_lbl.setObjectName("ThemeMoonLabel")
        moon_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_secondary']};"
            "font-size: 16px; background: transparent;"
        )

        theme_lbl = QLabel("Светлая" if theme_manager.current == Theme.LIGHT else "Тёмная")
        theme_lbl.setObjectName("ThemeLabel")
        theme_lbl.setStyleSheet(
            f"color: {theme_manager.tokens['text_secondary']};"
            "font-size: 11px; background: transparent;"
        )

        self._moon_lbl = moon_lbl
        self._theme_lbl = theme_lbl

        # Переключатель темы
        theme_toggle = ToggleSwitch()
        theme_toggle.setChecked(theme_manager.current == Theme.LIGHT)
        theme_toggle.setColors(
            off_color="#3a3a3a",  # Темная тема (выкл)
            on_color="#f0a000",   # Светлая тема (вкл) - золотистый
            circle_color="#ffffff"
        )
        theme_toggle.toggled.connect(self._on_toggle_switched)

        bottom_layout.addWidget(moon_lbl)
        bottom_layout.addWidget(theme_lbl)
        bottom_layout.addStretch()
        bottom_layout.addWidget(theme_toggle)
        root.addWidget(bottom)

        # Default page
        self.set_page("dashboard")

        # Listen to theme changes
        theme_manager.theme_changed.connect(self._on_theme_changed)

        # Apply correct colors for the current theme
        self._restyle_static_elements()

    def _restyle_static_elements(self):
        """Обновляет цвета статичных элементов сайдбара под текущую тему."""
        t = theme_manager.tokens
        self._brand_mark.setStyleSheet(f"background: {t['accent_subtle']}; border: 1px solid {t['accent_muted']}; border-radius: 11px;")
        self._brand_mark.setPixmap(line_icon('brand', t['accent']).pixmap(QSize(24, 24)))
        self._logo_lbl.setStyleSheet(
            f"color: {t['text_primary']};"
            "font-size: 18px; font-weight: 700; letter-spacing: 0.3px;"
            "background: transparent;"
        )
        self._ver_lbl.setStyleSheet(
            f"color: {t['text_tertiary']};"
            "font-size: 10px; background: transparent;"
        )
        self._nav_lbl.setStyleSheet(
            f"color: {t['text_tertiary']};"
            "font-size: 9px; font-weight: 700; letter-spacing: 1.5px;"
            "background: transparent;"
        )
        self._sep.setStyleSheet(f"background: {t['border_subtle']};")
        self._sep2.setStyleSheet(f"background: {t['border_subtle']};")

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

    def _on_toggle_switched(self, checked: bool):
        """Обработчик переключателя темы"""
        from PyQt6.QtWidgets import QApplication
        # checked = True означает светлая тема, False - темная
        new_theme = Theme.LIGHT if checked else Theme.DARK
        if theme_manager.current != new_theme:
            theme_manager.set_theme(new_theme, QApplication.instance())

    def _on_theme_changed(self, theme_name: str):
        t = theme_manager.tokens
        is_dark = theme_name == "dark"
        self._moon_lbl.setText("☾" if is_dark else "☀")
        self._theme_lbl.setText("Тёмная" if is_dark else "Светлая")
        self.setStyleSheet("")  # Trigger repaint

        # Обновить цвета статичных элементов
        self._restyle_static_elements()

        # Обновить цвета активных элементов
        for pid, item in self._items.items():
            item.set_active(pid == self._current_page)
