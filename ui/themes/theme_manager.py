"""
ThemeManager - управление темами RoadScanner
Поддерживает современный и классический дизайн
"""
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import QObject, pyqtSignal, QSettings
from enum import Enum

# Импортируем современные темы
from ui.themes.modern_dark import MODERN_DARK_TOKENS
from ui.themes.modern_light import MODERN_LIGHT_TOKENS
from ui.themes.modern_styles import build_modern_qss


class Theme(Enum):
    DARK = "dark"
    LIGHT = "light"


# Используем современные темы по умолчанию
DARK_TOKENS = MODERN_DARK_TOKENS
LIGHT_TOKENS = MODERN_LIGHT_TOKENS


class ThemeManager(QObject):
    theme_changed = pyqtSignal(str)  # Сигнал при смене темы

    def __init__(self):
        super().__init__()
        self._current = Theme.DARK
        self._use_modern = True  # Использовать современный дизайн
        self._settings = QSettings("RoadScanner", "Theme")
        self._load_saved_theme()

    def _load_saved_theme(self):
        """Загрузка сохраненной темы из настроек"""
        try:
            saved = self._settings.value("current_theme", "dark")
            self._current = Theme.DARK if saved == "dark" else Theme.LIGHT
            self._use_modern = self._settings.value("use_modern", True, type=bool)
        except Exception:
            pass

    def _save_theme(self):
        """Сохранение текущей темы в настройки"""
        try:
            self._settings.setValue("current_theme", self._current.value)
            self._settings.setValue("use_modern", self._use_modern)
        except Exception:
            pass

    @property
    def current(self) -> Theme:
        return self._current

    @property
    def tokens(self) -> dict:
        return DARK_TOKENS if self._current == Theme.DARK else LIGHT_TOKENS

    @property
    def is_dark(self) -> bool:
        return self._current == Theme.DARK

    @property
    def use_modern(self) -> bool:
        return self._use_modern

    def apply(self, app: QApplication):
        """Применяет текущую тему к приложению"""
        t = self.tokens
        qss = build_modern_qss(t)
        app.setStyleSheet(qss)
        self.theme_changed.emit(self._current.value)
        self._save_theme()

    def toggle(self, app: QApplication):
        """Переключает между темной и светлой темой"""
        self._current = Theme.LIGHT if self._current == Theme.DARK else Theme.DARK
        self.apply(app)

    def set_theme(self, theme: Theme, app: QApplication):
        """Устанавливает конкретную тему"""
        self._current = theme
        self.apply(app)

    def set_modern(self, enabled: bool, app: QApplication):
        """Включает/выключает современный дизайн"""
        self._use_modern = enabled
        self.apply(app)


# Глобальный синглтон
theme_manager = ThemeManager()
