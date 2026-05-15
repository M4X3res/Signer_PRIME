"""
RoadScanner v2 — точка входа
Заменяет ViewPlayer.py / ButtonsHandler.py / PlayerHandler.py
"""
import sys
import os

# Чтобы импорты configs/ и utils работали из корня проекта
base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, base_path)

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont

from ui.main_window import MainWindow
from ui.themes.theme_manager import theme_manager, Theme


def main():
    # High-DPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Signer")
    app.setApplicationVersion("2.0")

    # Базовый шрифт
    font = QFont("Segoe UI", 13)
    app.setFont(font)

    # Применяем тёмную тему по умолчанию
    theme_manager.set_theme(Theme.DARK, app)

    window = MainWindow()
    window.show()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()