"""
core/frame.py
Иммутабельный датакласс одного обнаруженного знака в кадре.
Заменяет старый Frame.py — убраны мутабельные поля, добавлены типы.
"""
from dataclasses import dataclass, field


@dataclass(slots=True)
class DetectedSign:
    """Один знак обнаруженный детектором в одном кадре."""
    x: int
    y: int
    w: int
    h: int
    name_sign:            str   # класс YOLO (напр. "treugolnik")
    number_sign:          str   # класс CNN  (напр. "1.21")
    frame_number:         int   # номер кадра внутри текущего видео
    absolute_frame_number:int   # глобальный номер кадра по всем видео
    latitude:             float # координата автомобиля X (EPSG:32635, метры)
    longitude:            float # координата автомобиля Y (EPSG:32635, метры)
    text_on_sign:         str = ""
    is_side:              bool = False  # боковой знак (на столбе сбоку)

    @property
    def bbox(self) -> tuple[int, int, int, int]:
        """Возвращает координаты bbox как кортеж (x, y, w, h) для совместимости."""
        return (self.x, self.y, self.w, self.h)

    @staticmethod
    def overlap_area(s1: tuple, s2: tuple) -> float:
        """
        Процент перекрытия s1 квадратом s2.
        s = (x, y, w, h)
        """
        ix = max(s1[0], s2[0])
        iy = max(s1[1], s2[1])
        iw = min(s1[0] + s1[2], s2[0] + s2[2]) - ix
        ih = min(s1[1] + s1[3], s2[1] + s2[3]) - iy
        if iw <= 0 or ih <= 0:
            return 0.0
        return (iw * ih) / (s1[2] * s1[3]) * 100