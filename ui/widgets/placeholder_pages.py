from PyQt6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from ui.themes.theme_manager import theme_manager


class _PlaceholderPage(QWidget):
    def __init__(self, icon: str, title: str, desc: str, parent=None):
        super().__init__(parent)
        self.setObjectName("ContentArea")

        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(8)

        t = theme_manager.tokens

        icon_lbl = QLabel(icon)
        icon_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_lbl.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 40px; background: transparent;"
        )

        title_lbl = QLabel(title)
        title_lbl.setObjectName("PageTitle")
        title_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        desc_lbl = QLabel(desc)
        desc_lbl.setObjectName("PageSubtitle")
        desc_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(icon_lbl)
        layout.addSpacing(4)
        layout.addWidget(title_lbl)
        layout.addWidget(desc_lbl)


class MapPage(_PlaceholderPage):
    def __init__(self, parent=None):
        super().__init__(
            "◎",
            "Карта",
            "Запустите обработку и откройте карту — здесь будет отображаться GPS-трек и знаки",
            parent,
        )


class ErrorEditorPage(_PlaceholderPage):
    def __init__(self, parent=None):
        super().__init__(
            "◈",
            "Редактор ошибок",
            "После завершения обработки здесь можно скорректировать неверно распознанные знаки",
            parent,
        )