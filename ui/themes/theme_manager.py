from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal
from enum import Enum


class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"


DARK_TOKENS = {
    # Backgrounds
    "bg_primary":       "#141414",
    "bg_secondary":     "#1c1c1c",
    "bg_tertiary":      "#242424",
    "bg_elevated":      "#2a2a2a",
    "bg_hover":         "#303030",

    # Borders
    "border_subtle":    "#2e2e2e",
    "border_default":   "#3a3a3a",
    "border_strong":    "#505050",

    # Text
    "text_primary":     "#f0f0f0",
    "text_secondary":   "#a0a0a0",
    "text_tertiary":    "#606060",
    "text_disabled":    "#404040",

    # Accent — холодный синий, как в DaVinci/Premiere
    "accent":           "#3d8ef0",
    "accent_hover":     "#5aa0f5",
    "accent_pressed":   "#2a70d0",
    "accent_subtle":    "#1a2a40",

    # Status
    "success":          "#3a9e6a",
    "warning":          "#d4882a",
    "error":            "#c94f4f",
    "info":             "#3d8ef0",

    # Sidebar
    "sidebar_bg":       "#111111",
    "sidebar_item_active": "#1e2d42",
    "sidebar_item_hover":  "#1c1c1c",

    # Scrollbar
    "scrollbar_bg":     "#1c1c1c",
    "scrollbar_handle": "#3a3a3a",
}

LIGHT_TOKENS = {
    # Backgrounds
    "bg_primary":       "#f5f5f5",
    "bg_secondary":     "#ffffff",
    "bg_tertiary":      "#efefef",
    "bg_elevated":      "#ffffff",
    "bg_hover":         "#e8e8e8",

    # Borders
    "border_subtle":    "#e8e8e8",
    "border_default":   "#d8d8d8",
    "border_strong":    "#b0b0b0",

    # Text
    "text_primary":     "#141414",
    "text_secondary":   "#505050",
    "text_tertiary":    "#909090",
    "text_disabled":    "#c0c0c0",

    # Accent
    "accent":           "#2a70d0",
    "accent_hover":     "#1a5ab8",
    "accent_pressed":   "#0f44a0",
    "accent_subtle":    "#deeafc",

    # Status
    "success":          "#2d8a58",
    "warning":          "#b87020",
    "error":            "#b03030",
    "info":             "#2a70d0",

    # Sidebar
    "sidebar_bg":       "#1c1c1c",
    "sidebar_item_active": "#2a3a52",
    "sidebar_item_hover":  "#2a2a2a",

    # Scrollbar
    "scrollbar_bg":     "#f0f0f0",
    "scrollbar_handle": "#c0c0c0",
}


def _build_qss(t: dict) -> str:
    return f"""
/* ── Root ─────────────────────────────────────────── */
QMainWindow, QDialog, QWidget {{
    background-color: {t['bg_primary']};
    color: {t['text_primary']};
    font-family: "Segoe UI", "SF Pro Display", "Helvetica Neue", sans-serif;
    font-size: 13px;
}}

/* ── Sidebar ───────────────────────────────────────── */
#Sidebar {{
    background-color: {t['sidebar_bg']};
    border-right: 1px solid {t['border_subtle']};
}}

#SidebarItem {{
    background: transparent;
    border: none;
    border-radius: 6px;
    color: {t['text_secondary']};
    padding: 10px 12px;
    text-align: left;
    font-size: 12px;
    font-weight: 500;
    letter-spacing: 0.3px;
}}
#SidebarItem:hover {{
    background-color: {t['sidebar_item_hover']};
    color: {t['text_primary']};
}}
#SidebarItem[active="true"] {{
    background-color: {t['sidebar_item_active']};
    color: {t['accent']};
    border-left: 2px solid {t['accent']};
    border-radius: 0px 6px 6px 0px;
    padding-left: 10px;
}}

#SidebarLogo {{
    color: {t['text_primary']};
    font-size: 14px;
    font-weight: 700;
    letter-spacing: 1.5px;
    padding: 0px;
    background: transparent;
    border: none;
}}

#SidebarVersion {{
    color: {t['text_tertiary']};
    font-size: 10px;
    background: transparent;
}}

/* ── Content area ──────────────────────────────────── */
#ContentArea {{
    background-color: {t['bg_primary']};
}}

#PageTitle {{
    color: {t['text_primary']};
    font-size: 20px;
    font-weight: 600;
    letter-spacing: -0.3px;
}}

#PageSubtitle {{
    color: {t['text_secondary']};
    font-size: 12px;
    font-weight: 400;
}}

/* ── Cards ─────────────────────────────────────────── */
#Card {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border_subtle']};
    border-radius: 8px;
}}

#CardTitle {{
    color: {t['text_secondary']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.2px;
    text-transform: uppercase;
    background: transparent;
}}

/* ── Buttons ───────────────────────────────────────── */
#BtnPrimary {{
    background-color: {t['accent']};
    color: #ffffff;
    border: none;
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: 500;
    min-width: 140px;
}}
#BtnPrimary:hover {{
    background-color: {t['accent_hover']};
}}
#BtnPrimary:pressed {{
    background-color: {t['accent_pressed']};
}}
#BtnPrimary:disabled {{
    background-color: {t['bg_elevated']};
    color: {t['text_disabled']};
}}

#BtnSecondary {{
    background-color: transparent;
    color: {t['text_primary']};
    border: 1px solid {t['border_default']};
    border-radius: 6px;
    padding: 8px 24px;
    font-size: 13px;
    font-weight: 400;
    min-width: 140px;
}}
#BtnSecondary:hover {{
    background-color: {t['bg_hover']};
    border-color: {t['border_strong']};
}}
#BtnSecondary:pressed {{
    background-color: {t['bg_elevated']};
}}

#BtnDanger {{
    background-color: transparent;
    color: {t['error']};
    border: 1px solid {t['error']};
    border-radius: 6px;
    padding: 8px 20px;
    font-size: 13px;
}}
#BtnDanger:hover {{
    background-color: {t['error']};
    color: #ffffff;
}}

#BtnIcon {{
    background: transparent;
    border: none;
    border-radius: 6px;
    padding: 6px;
    color: {t['text_secondary']};
}}
#BtnIcon:hover {{
    background-color: {t['bg_hover']};
    color: {t['text_primary']};
}}

/* ── FilePathWidget ────────────────────────────────── */
#FilePathBox {{
    background-color: {t['bg_tertiary']};
    border: 1px solid {t['border_subtle']};
    border-radius: 6px;
    padding: 8px 12px;
    color: {t['text_secondary']};
    font-size: 11px;
    font-family: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
}}

#FileLabel {{
    color: {t['text_secondary']};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.8px;
    background: transparent;
}}

/* ── Progress ──────────────────────────────────────── */
QProgressBar {{
    background-color: {t['bg_tertiary']};
    border: none;
    border-radius: 3px;
    height: 4px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {t['accent']};
    border-radius: 3px;
}}

/* ── Log / Console ─────────────────────────────────── */
#LogConsole {{
    background-color: {t['bg_tertiary']};
    border: 1px solid {t['border_subtle']};
    border-radius: 6px;
    color: {t['text_secondary']};
    font-family: "Cascadia Code", "JetBrains Mono", "Consolas", monospace;
    font-size: 11px;
    padding: 8px;
    selection-background-color: {t['accent_subtle']};
}}

/* ── Input / ComboBox ──────────────────────────────── */
QLineEdit, QSpinBox, QDoubleSpinBox {{
    background-color: {t['bg_tertiary']};
    border: 1px solid {t['border_default']};
    border-radius: 6px;
    padding: 7px 10px;
    color: {t['text_primary']};
    font-size: 13px;
    selection-background-color: {t['accent_subtle']};
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {t['accent']};
}}

QComboBox {{
    background-color: {t['bg_tertiary']};
    border: 1px solid {t['border_default']};
    border-radius: 6px;
    padding: 7px 10px;
    color: {t['text_primary']};
    font-size: 13px;
}}
QComboBox:focus {{
    border-color: {t['accent']};
}}
QComboBox::drop-down {{
    border: none;
    width: 24px;
}}
QComboBox QAbstractItemView {{
    background-color: {t['bg_elevated']};
    border: 1px solid {t['border_default']};
    selection-background-color: {t['accent_subtle']};
    color: {t['text_primary']};
    border-radius: 4px;
}}

/* ── CheckBox ──────────────────────────────────────── */
QCheckBox {{
    color: {t['text_primary']};
    spacing: 8px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {t['border_default']};
    background: {t['bg_tertiary']};
}}
QCheckBox::indicator:checked {{
    background: {t['accent']};
    border-color: {t['accent']};
}}

/* ── Scrollbar ─────────────────────────────────────── */
QScrollBar:vertical {{
    background: {t['scrollbar_bg']};
    width: 6px;
    margin: 0;
    border-radius: 3px;
}}
QScrollBar::handle:vertical {{
    background: {t['scrollbar_handle']};
    border-radius: 3px;
    min-height: 30px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {t['scrollbar_bg']};
    height: 6px;
    border-radius: 3px;
}}
QScrollBar::handle:horizontal {{
    background: {t['scrollbar_handle']};
    border-radius: 3px;
    min-width: 30px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}

/* ── Separator ─────────────────────────────────────── */
#Separator {{
    background-color: {t['border_subtle']};
}}

/* ── Status bar ────────────────────────────────────── */
#StatusBar {{
    background-color: {t['sidebar_bg']};
    border-top: 1px solid {t['border_subtle']};
    color: {t['text_tertiary']};
    font-size: 11px;
    padding: 0 12px;
}}

#StatusDot {{
    background: transparent;
    border: none;
    font-size: 11px;
    padding: 0;
}}

/* ── Settings ──────────────────────────────────────── */
#SettingsGroup {{
    background-color: {t['bg_secondary']};
    border: 1px solid {t['border_subtle']};
    border-radius: 8px;
    padding: 4px;
}}

#SettingsLabel {{
    color: {t['text_primary']};
    font-size: 13px;
    background: transparent;
}}

#SettingsHint {{
    color: {t['text_tertiary']};
    font-size: 11px;
    background: transparent;
}}

/* ── Toggle Switch ─────────────────────────────────── */
#ToggleSwitch {{
    background-color: {t['bg_hover']};
    border: none;
    border-radius: 10px;
    min-width: 40px;
    max-width: 40px;
    min-height: 20px;
    max-height: 20px;
}}
#ToggleSwitch[checked="true"] {{
    background-color: {t['accent']};
}}

/* ── Stat cards ────────────────────────────────────── */
#StatValue {{
    color: {t['text_primary']};
    font-size: 28px;
    font-weight: 300;
    letter-spacing: -1px;
    background: transparent;
}}

#StatLabel {{
    color: {t['text_tertiary']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1px;
    background: transparent;
}}

#AccentLine {{
    background-color: {t['accent']};
    border-radius: 1px;
}}

/* ── Divider label ─────────────────────────────────── */
#SectionLabel {{
    color: {t['text_tertiary']};
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    background: transparent;
}}
"""


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self._current = Theme.DARK

    @property
    def current(self) -> Theme:
        return self._current

    @property
    def tokens(self) -> dict:
        return DARK_TOKENS if self._current == Theme.DARK else LIGHT_TOKENS

    def apply(self, app: QApplication):
        t = self.tokens
        qss = _build_qss(t)
        app.setStyleSheet(qss)
        self.theme_changed.emit(self._current.value)

    def toggle(self, app: QApplication):
        self._current = Theme.LIGHT if self._current == Theme.DARK else Theme.DARK
        self.apply(app)

    def set_theme(self, theme: Theme, app: QApplication):
        self._current = theme
        self.apply(app)


# Глобальный синглтон
theme_manager = ThemeManager()