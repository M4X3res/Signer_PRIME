"""Compact themed controls shared by the map and sign editor."""
from PyQt6.QtCore import Qt, QPointF
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def line_icon(name: str, color: str) -> QIcon:
    pixmap = QPixmap(40, 40)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(color), 1.6, Qt.PenStyle.SolidLine,
                        Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
    paths = {
        'left': [[(15, 10), (5, 10)], [(9, 6), (5, 10), (9, 14)]],
        'right': [[(5, 10), (15, 10)], [(11, 6), (15, 10), (11, 14)]],
        'up': [[(10, 15), (10, 5)], [(6, 9), (10, 5), (14, 9)]],
        'down': [[(10, 5), (10, 15)], [(6, 11), (10, 15), (14, 11)]],
        'external': [[(11, 4), (16, 4), (16, 9)], [(16, 4), (9, 11)],
                     [(8, 5), (4, 5), (4, 16), (15, 16), (15, 12)]],
        'reload': [[(16, 4), (16, 9), (11, 9)]],
        'dashboard': [[(3,3),(8,3),(8,8),(3,8),(3,3)], [(12,3),(17,3),(17,8),(12,8),(12,3)],
                      [(3,12),(8,12),(8,17),(3,17),(3,12)], [(12,12),(17,12),(17,17),(12,17),(12,12)]],
        'processing': [[(6,3),(17,10),(6,17),(6,3)]],
        'map': [[(3,5),(7,3),(13,6),(17,4),(17,15),(13,17),(7,14),(3,16),(3,5)],
                [(7,3),(7,14)], [(13,6),(13,17)]],
        'errors': [[(4,3),(16,3),(16,17),(4,17),(4,3)], [(7,7),(13,7)], [(7,11),(9,13),(13,10)]],
        'settings': [[(3,5),(8,5)],[(12,5),(17,5)],[(8,3),(8,7),(12,7),(12,3),(8,3)],
                     [(3,14),(6,14)],[(10,14),(17,14)],[(6,12),(6,16),(10,16),(10,12),(6,12)]],
        'upload': [[(10,13),(10,3)],[(6,7),(10,3),(14,7)],[(3,12),(3,17),(17,17),(17,12)]],
        'check': [[(4,10),(8,14),(16,6)]],
        'brand': [[(4,17),(7,3)],[(16,17),(13,3)],[(10,4),(10,7)],[(10,11),(10,15)]],
    }
    for points in paths[name]:
        path = QPainterPath(QPointF(*points[0]))
        for point in points[1:]:
            path.lineTo(QPointF(*point))
        painter.drawPath(path)
    if name == 'reload':
        path = QPainterPath()
        path.arcMoveTo(4, 4, 12, 12, 25)
        path.arcTo(4, 4, 12, 12, 25, 295)
        painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


def compact_button_style(t: dict) -> str:
    return f"""
        QPushButton {{ background: {t['bg_tertiary']}; color: {t['text_primary']};
            border: 1px solid {t['border_subtle']}; border-radius: 9px;
            padding: 0 12px; font-size: 12px; font-weight: 500;
            min-height: 0px; min-width: 0px; }}
        QPushButton:hover {{ background: {t['bg_elevated']}; border-color: {t['border_strong']}; }}
        QPushButton:pressed, QPushButton:checked {{ background: {t['accent_subtle']}; border-color: {t['accent']}; }}
        QPushButton:focus {{ border-color: {t['accent']}; }}
        QPushButton:disabled {{ color: {t['text_tertiary']}; background: {t['bg_secondary']}; border-color: {t['border_subtle']}; }}
    """
