"""
processing/frame_skip.py
SmartFrameSkipper — общая адаптивная логика пропуска кадров, вынесенная
из DetectorThread (BLOCK CPU-7), чтобы её мог использовать и
DetectorProcessPool. До этого рефакторинга Process Pool не применял ни
проверку "машина стоит", ни адаптивный skip по скорости/активности —
единственный из трёх режимов обработки, обрабатывавший буквально все
кадры из очереди. Поведение (константы, формулы) сохранено 1:1 с
оригиналом в DetectorThread — только вынесено для переиспользования.
"""
from __future__ import annotations
from typing import Optional


class SmartFrameSkipper:
    """
    Адаптивный пропуск кадров на основе скорости и активности детекций.
    
    Используется в DetectorThread и DetectorProcessPool для одинаковой
    логики обработки кадров во всех режимах.
    """
    
    # Минимальная скорость для обработки (км/ч)
    MIN_SPEED_KMH = 2.0

    # Базовые интервалы пропуска в зависимости от скорости
    # {скорость_км/ч: (мин_интервал, макс_интервал)}
    SKIP_INTERVALS = {
        0:   (1, 1),   # Стоим — каждый кадр
        30:  (1, 2),   # Медленно
        60:  (2, 3),   # Средняя скорость
        90:  (3, 4),   # Быстро
        120: (4, 5),   # Очень быстро
    }

    # Настройки адаптации по активности детекций
    ACTIVITY_WINDOW = 10              # Окно наблюдения (кадров)
    HIGH_ACTIVITY_THRESHOLD = 3       # Порог "много знаков"
    ACTIVITY_BONUS = -1               # Уменьшаем skip при активности
    NO_ACTIVITY_PENALTY = 1           # Увеличиваем skip без активности

    def __init__(self) -> None:
        """Инициализация skipper."""
        self._skip_counter = 0
        self.current_skip = 1
        self._activity_history: list[int] = []
        self.frames_skipped = 0

    def is_stationary(self, speed_kmh: Optional[float]) -> bool:
        """
        Проверяет, стоит ли машина.
        
        Args:
            speed_kmh: Скорость в км/ч (или None если GPS недоступен)
        
        Returns:
            True если машина стоит (скорость < MIN_SPEED_KMH)
        """
        return speed_kmh is not None and speed_kmh < self.MIN_SPEED_KMH

    def update_activity(self, n_detections: int) -> None:
        """
        Обновляет историю активности детекций.
        
        Args:
            n_detections: Количество обнаруженных знаков в кадре
        """
        self._activity_history.append(n_detections)
        if len(self._activity_history) > self.ACTIVITY_WINDOW * 2:
            self._activity_history = self._activity_history[-self.ACTIVITY_WINDOW:]

    def calc_skip_interval(self, speed_kmh: Optional[float]) -> int:
        """
        Вычисляет адаптивный интервал пропуска кадров.
        
        Args:
            speed_kmh: Скорость в км/ч
        
        Returns:
            Интервал пропуска (1 = каждый кадр, 2 = каждый второй, и т.д.)
        """
        if speed_kmh is None or speed_kmh < self.MIN_SPEED_KMH:
            self.current_skip = 1
            return 1
        
        base_skip = self._interpolate_skip(speed_kmh)
        modifier = self._calc_activity_modifier()
        self.current_skip = max(1, min(5, base_skip + modifier))
        return self.current_skip

    def _interpolate_skip(self, speed: float) -> int:
        """
        Интерполяция базового интервала skip по скорости.
        
        Args:
            speed: Скорость в км/ч
        
        Returns:
            Базовый интервал skip
        """
        speeds = sorted(self.SKIP_INTERVALS.keys())
        
        if speed <= speeds[0]:
            lo, hi = self.SKIP_INTERVALS[speeds[0]]
            return (lo + hi) // 2
        
        if speed >= speeds[-1]:
            return self.SKIP_INTERVALS[speeds[-1]][1]
        
        for i in range(len(speeds) - 1):
            s1, s2 = speeds[i], speeds[i + 1]
            if s1 <= speed <= s2:
                t = (speed - s1) / (s2 - s1)
                min1, max1 = self.SKIP_INTERVALS[s1]
                min2, max2 = self.SKIP_INTERVALS[s2]
                avg1, avg2 = (min1 + max1) / 2, (min2 + max2) / 2
                return round(avg1 + t * (avg2 - avg1))
        
        return 2

    def _calc_activity_modifier(self) -> int:
        """
        Вычисляет модификатор интервала на основе активности детекций.
        
        Returns:
            Модификатор (-1, 0, или +1)
        """
        if len(self._activity_history) < self.ACTIVITY_WINDOW // 2:
            return 0
        
        recent = sum(self._activity_history[-self.ACTIVITY_WINDOW:])
        
        if recent >= self.HIGH_ACTIVITY_THRESHOLD:
            return self.ACTIVITY_BONUS
        
        if recent == 0 and len(self._activity_history) >= self.ACTIVITY_WINDOW:
            return self.NO_ACTIVITY_PENALTY
        
        return 0

    def should_process(self) -> bool:
        """
        Определяет, нужно ли обрабатывать текущий кадр.
        
        Returns:
            True если кадр нужно обработать, False если пропустить
        """
        self._skip_counter += 1
        if self._skip_counter >= self.current_skip:
            self._skip_counter = 0
            return True
        
        self.frames_skipped += 1
        return False
