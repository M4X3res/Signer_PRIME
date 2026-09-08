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
    samples: List[float] = field(default_factory=list)
    
    def add(self, duration: float):
        """Добавить замер времени (в секундах)."""
        self.samples.append(duration)
    
    @property
    def count(self) -> int:
        return len(self.samples)
    
    @property
    def total(self) -> float:
        return sum(self.samples)
    
    @property
    def mean(self) -> float:
        return self.total / self.count if self.count > 0 else 0.0
    
    @property
    def min(self) -> float:
        return min(self.samples) if self.samples else 0.0
    
    @property
    def max(self) -> float:
        return max(self.samples) if self.samples else 0.0
    
    @property
    def p50(self) -> float:
        """Медиана."""
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        mid = len(sorted_samples) // 2
        return sorted_samples[mid]
    
    @property
    def p95(self) -> float:
        """95-й перцентиль."""
        if not self.samples:
            return 0.0
        sorted_samples = sorted(self.samples)
        idx = int(len(sorted_samples) * 0.95)
        return sorted_samples[min(idx, len(sorted_samples) - 1)]
    
    def report(self) -> str:
        """Форматированный отчет."""
        if not self.samples:
            return f"{self.name}: no data"
        
        return (
            f"{self.name}:\n"
            f"  Count:  {self.count}\n"
            f"  Total:  {self.total:.3f}s\n"
            f"  Mean:   {self.mean*1000:.1f}ms\n"
            f"  Min:    {self.min*1000:.1f}ms\n"
            f"  Median: {self.p50*1000:.1f}ms\n"
            f"  P95:    {self.p95*1000:.1f}ms\n"
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
