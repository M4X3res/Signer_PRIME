"""
UI утилиты для виджетов RoadScanner.
ЗАДАЧА 1 (P1): Стилизация попапов QComboBox для корректного отображения темы.
ЗАДАЧА 2 (P3): Переиспользуемый виджет пустого состояния.
"""
from PyQt6.QtWidgets import QComboBox, QWidget, QVBoxLayout, QLabel
from PyQt6.QtCore import Qt
from ui.themes.theme_manager import theme_manager


def style_combobox_popup(combo: QComboBox) -> None:
    """
    ЗАДАЧА 1 (P1): Применяет тему к popup (выпадающему списку) комбобокса.
    
    Проблема: QComboBox в стиле Fusion создаёт отдельный popup-контейнер
    (QFrame с флагом Qt::Popup), который не покрывается стандартными
    QSS-селекторами `QComboBox` или `QComboBox QAbstractItemView`.
    Этот контейнер имеет собственный фон и рамку, которые нужно стилизовать
    программно.
    
    Args:
        combo: QComboBox для стилизации
    """
    t = theme_manager.tokens
    
    # Получаем контейнер popup (может быть как родителем view, так и самим view)
    view = combo.view()
    popup = view.parentWidget() if view.parentWidget() else view
    
    # Применяем стиль к popup-контейнеру
    popup.setStyleSheet(
        f"background-color: {t['bg_elevated']};"
        f"border: 1px solid {t['border_default']};"
        f"border-radius: 8px;"
    )


def connect_combobox_theme_updates(combo: QComboBox) -> None:
    """
    ЗАДАЧА 1 (P1): Подключает автообновление темы popup при смене темы.
    
    Args:
        combo: QComboBox для подключения
    """
    def update_theme(_theme_name: str):
        style_combobox_popup(combo)
    
    theme_manager.theme_changed.connect(update_theme)
    # Применяем сразу
    style_combobox_popup(combo)


class EmptyStatePlaceholder(QWidget):
    """
    ЗАДАЧА 2 (P3): Переиспользуемый виджет "пустого состояния".
    
    Единообразный паттерн: иконка + заголовок + подзаголовок,
    как в _MapPlaceholder на странице Карты.
    """
    def __init__(self, icon: str, title: str, subtitle: str, parent=None):
        super().__init__(parent)
        
        self._icon_text = icon
        self._title_text = title
        self._subtitle_text = subtitle
        
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)
        
        self._icon = QLabel(icon)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._title = QLabel(title)
        self._title.setObjectName("PageTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        self._subtitle = QLabel(subtitle)
        self._subtitle.setObjectName("PageSubtitle")
        self._subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(self._icon)
        layout.addSpacing(4)
        layout.addWidget(self._title)
        layout.addWidget(self._subtitle)
        
        self._restyle()
        theme_manager.theme_changed.connect(self._restyle)
    
    def _restyle(self):
        t = theme_manager.tokens
        self._icon.setStyleSheet(
            f"color: {t['text_tertiary']}; font-size: 40px; background: transparent;"
        )
    
    def set_subtitle(self, text: str, error: bool = False):
        """Обновляет подзаголовок (для статусных сообщений)."""
        t = theme_manager.tokens
        color = t["error"] if error else t["text_secondary"]
        self._subtitle.setText(text)
        self._subtitle.setStyleSheet(
            f"color: {color}; font-size: 12px; background: transparent;"
        )
    
    def set_icon(self, icon: str):
        """Обновляет иконку."""
        self._icon.setText(icon)
        self._icon_text = icon

