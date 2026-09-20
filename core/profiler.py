"""
Профилирование производительности обработки кадров.

Инструментирует ключевые шаги для измерения времени выполнения.
"""
import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Dict, List

logger = logging.getLogger(__name__)


@dataclass
class TimingStats:
    """Статистика времени выполнения операции."""
    name: str
    # BLOCK GPU-MEM-2: samples больше не хранит ВСЕ замеры за всё время работы —
    # это неограниченный по размеру список, который рос всю сессию обработки
    # длинного видео (часы -> миллионы замеров) и создавал постоянное давление
    # на GC параллельно с CUDA-аллокатором. Вместо этого храним точные
    # агрегаты (count/total/min/max) без хранения истории, и ограниченное
    # скользящее окно последних MAX_SAMPLES_FOR_PERCENTILE замеров только для
    # приближённого расчёта перцентилей (p50/p95).
    MAX_SAMPLES_FOR_PERCENTILE: int = field(default=2000, repr=False)
    _count: int = field(default=0, repr=False)
    _total: float = field(default=0.0, repr=False)
    _min: float = field(default=float("inf"), repr=False)
    _max: float = field(default=0.0, repr=False)
    _recent: List[float] = field(default_factory=list, repr=False)

    def add(self, duration: float):
        """Добавить замер времени (в секундах)."""
        self._count += 1
        self._total += duration
        if duration < self._min:
            self._min = duration
        if duration > self._max:
            self._max = duration
        self._recent.append(duration)
        if len(self._recent) > self.MAX_SAMPLES_FOR_PERCENTILE:
            # Не даём окну расти бесконечно — отбрасываем самые старые замеры
            del self._recent[: len(self._recent) - self.MAX_SAMPLES_FOR_PERCENTILE]

    @property
    def count(self) -> int:
        return self._count

    @property
    def total(self) -> float:
        return self._total

    @property
    def mean(self) -> float:
        return self._total / self._count if self._count > 0 else 0.0

    @property
    def min(self) -> float:
        return self._min if self._count > 0 else 0.0

    @property
    def max(self) -> float:
        return self._max

    @property
    def p50(self) -> float:
        """Медиана (приближённая, по последним MAX_SAMPLES_FOR_PERCENTILE замерам)."""
        if not self._recent:
            return 0.0
        sorted_samples = sorted(self._recent)
        mid = len(sorted_samples) // 2
        return sorted_samples[mid]

    @property
    def p95(self) -> float:
        """95-й перцентиль (приближённый, по последним MAX_SAMPLES_FOR_PERCENTILE замерам)."""
        if not self._recent:
            return 0.0
        sorted_samples = sorted(self._recent)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]

    def report(self) -> str:
        """Форматированный отчет."""
        if self._count == 0:
            return f"{self.name}: no data"
        return (
            f"{self.name}:\n"
            f"  Count:  {self.count}\n"
            f"  Total:  {self.total:.3f}s\n"
            f"  Mean:   {self.mean*1000:.1f}ms\n"
            f"  Min:    {self.min*1000:.1f}ms\n"
            f"  Median: {self.p50*1000:.1f}ms (last {len(self._recent)} samples)\n"
            f"  P95:    {self.p95*1000:.1f}ms (last {len(self._recent)} samples)\n"
            f"  Max:    {self.max*1000:.1f}ms"
        )


class Profiler:
    """Профайлер для измерения производительности обработки."""
    
    def __init__(self):
        self.stats: Dict[str, TimingStats] = {}
        self.enabled = False
    
    def enable(self):
        """Включить профилирование."""
        self.enabled = True
        logger.info("Профилирование включено")
    
    def disable(self):
        """Выключить профилирование."""
        self.enabled = False
        logger.info("Профилирование выключено")
    
    @contextmanager
    def measure(self, operation: str):
        """
        Контекстный менеджер для замера времени операции.
        
        Usage:
            with profiler.measure("yolo_detection"):
                result = model.predict(image)
        """
        if not self.enabled:
            yield
            return
        
        start = time.perf_counter()
        try:
            yield
        finally:
            duration = time.perf_counter() - start
            
            if operation not in self.stats:
                self.stats[operation] = TimingStats(operation)
            
            self.stats[operation].add(duration)
    
    def get_report(self) -> str:
        """Полный отчет по всем операциям."""
        if not self.stats:
            return "Профилирование: нет данных"
        
        lines = ["=" * 60]
        lines.append("ПРОФИЛИРОВАНИЕ ПРОИЗВОДИТЕЛЬНОСТИ")
        lines.append("=" * 60)
        lines.append("")
        
        # Сортируем по общему времени (от большего к меньшему)
        sorted_stats = sorted(
            self.stats.values(),
            key=lambda s: s.total,
            reverse=True
        )
        
        for stat in sorted_stats:
            lines.append(stat.report())
            lines.append("")
        
        # Итоговая статистика
        total_time = sum(s.total for s in self.stats.values())
        total_count = sum(s.count for s in self.stats.values())
        
        lines.append("-" * 60)
        lines.append(f"Итого операций: {total_count}")
        lines.append(f"Суммарное время: {total_time:.3f}s")
        lines.append("=" * 60)
        
        return "\n".join(lines)
    
    def reset(self):
        """Сбросить все статистики."""
        self.stats.clear()
        logger.info("Статистики профилирования сброшены")
    
    def log_report(self):
        """Логировать отчет."""
        if self.enabled and self.stats:
            logger.info("\n" + self.get_report())


# Глобальный экземпляр профайлера
profiler = Profiler()


def enable_profiling():
    """Включить профилирование (вызывать из main.py или через config)."""
    profiler.enable()


def disable_profiling():
    """Выключить профилирование."""
    profiler.disable()


def get_profiling_report() -> str:
    """Получить отчет профилирования."""
    return profiler.get_report()
