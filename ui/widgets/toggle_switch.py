"""
ui/widgets/toggle_switch.py
Компонент переключателя (toggle switch) для темы
"""
from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, pyqtSignal, QPropertyAnimation, QEasingCurve, pyqtProperty
from PyQt6.QtGui import QPainter, QColor, QPen


class ToggleSwitch(QWidget):
    """
    Анимированный переключатель в стиле iOS/Material Design
    """
    toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(44, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        
        self._checked = False
        self._circle_position = 0.0  # 0.0 = left, 1.0 = right
        
        # Анимация
        self._animation = QPropertyAnimation(self, b"circle_position", self)
        self._animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        self._animation.setDuration(200)
        
        # Цвета
        self._bg_color_off = QColor("#3a3a3a")  # Серый для выключенного
        self._bg_color_on = QColor("#0066cc")   # Синий для включенного
        self._circle_color = QColor("#ffffff")  # Белый кружок

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Фон (округлый прямоугольник)
        rect = QRectF(0, 0, self.width(), self.height())
        
        # Плавная интерполяция цвета фона
        if self._checked:
            bg_color = self._bg_color_on
        else:
            bg_color = self._bg_color_off
        
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg_color)
        painter.drawRoundedRect(rect, self.height() / 2, self.height() / 2)
        
        # Кружок (переключатель)
        circle_radius = self.height() - 6
        circle_x = 3 + self._circle_position * (self.width() - circle_radius - 6)
        circle_y = 3
        
        painter.setBrush(self._circle_color)
        painter.drawEllipse(
            int(circle_x), int(circle_y),
            int(circle_radius), int(circle_radius)
        )

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.toggle()

    def toggle(self):
        """Переключить состояние"""
        self.setChecked(not self._checked)

    def setChecked(self, checked: bool):
        """Установить состояние"""
        if self._checked == checked:
            return
        
        self._checked = checked
        
        # Анимация позиции кружка
        self._animation.stop()
        self._animation.setStartValue(self._circle_position)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()
        
        self.toggled.emit(checked)

    def isChecked(self) -> bool:
        """Получить текущее состояние"""
        return self._checked

    # Property для анимации
    @pyqtProperty(float)
    def circle_position(self):
        return self._circle_position

    @circle_position.setter
    def circle_position(self, pos):
        self._circle_position = pos
        self.update()  # Перерисовать

    def setColors(self, off_color: str, on_color: str, circle_color: str = "#ffffff"):
        """Установить цвета переключателя"""
        self._bg_color_off = QColor(off_color)
        self._bg_color_on = QColor(on_color)
        self._circle_color = QColor(circle_color)
        self.update()
