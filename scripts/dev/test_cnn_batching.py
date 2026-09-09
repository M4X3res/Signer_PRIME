"""
Тест производительности CNN batching vs non-batching на CPU.

Измеряет реальное время выполнения classify_rube на CPU с батчингом
и без него, чтобы проверить утверждение BATCHING_FAILURE_ANALYSIS.md.

Usage:
    python scripts/test_cnn_batching.py
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import cv2
import numpy as np


def test_batching_performance(n_crops: int = 50, n_runs: int = 5):
    """
    Тест производительности CNN классификации с батчингом и без.
    
    Args:
        n_crops: Количество crops для обработки за раз
        n_runs: Количество прогонов для усреднения
    """
    from core.detector import Detector
    
    print(f"Инициализация Detector...")
    detector = Detector()
    
    # Генерируем синтетические 32x32 crops (типичный размер для CNN)
    print(f"Генерация {n_crops} синтетических crops...")
    crops = []
    for i in range(n_crops):
        # Случайный noise crop
        crop = np.random.randint(0, 256, (32, 32, 3), dtype=np.uint8)
        crops.append(crop)
    
    print(f"\nТестирование на {n_crops} crops, {n_runs} прогонов...\n")
    
    # Test 1: С батчингом (текущий код)
    print("=" * 60)
    print("ТЕСТ 1: С БАТЧИНГОМ (_classify_rube_batch)")
    print("=" * 60)
    
    batch_times = []
    for run in range(n_runs):
        start = time.perf_counter()
        results = detector._classify_rube_batch(crops)
        end = time.perf_counter()
        elapsed = end - start
        batch_times.append(elapsed)
        print(f"  Run {run+1}/{n_runs}: {elapsed:.4f}s ({n_crops/elapsed:.1f} crops/sec)")
    
    batch_avg = sum(batch_times) / len(batch_times)
    batch_std = np.std(batch_times)
    print(f"\nСреднее: {batch_avg:.4f}s ± {batch_std:.4f}s")
    print(f"Пропускная способность: {n_crops/batch_avg:.1f} crops/sec")
    
    # Test 2: Без батчинга (loop)
    print("\n" + "=" * 60)
    print("ТЕСТ 2: БЕЗ БАТЧИНГА (loop _classify_rube)")
    print("=" * 60)
    
    loop_times = []
    for run in range(n_runs):
        start = time.perf_counter()
        results = []
        for crop in crops:
            result = detector._classify_rube(crop)
            results.append(result)
        end = time.perf_counter()
        elapsed = end - start
        loop_times.append(elapsed)
        print(f"  Run {run+1}/{n_runs}: {elapsed:.4f}s ({n_crops/elapsed:.1f} crops/sec)")
    
    loop_avg = sum(loop_times) / len(loop_times)
    loop_std = np.std(loop_times)
    print(f"\nСреднее: {loop_avg:.4f}s ± {loop_std:.4f}s")
    print(f"Пропускная способность: {n_crops/loop_avg:.1f} crops/sec")
    
    # Сравнение
    print("\n" + "=" * 60)
    print("РЕЗУЛЬТАТЫ")
    print("=" * 60)
    
    speedup = loop_avg / batch_avg
    pct_diff = (batch_avg - loop_avg) / loop_avg * 100
    
    print(f"Батчинг:    {batch_avg:.4f}s ({n_crops/batch_avg:.1f} crops/sec)")
    print(f"Loop:       {loop_avg:.4f}s ({n_crops/loop_avg:.1f} crops/sec)")
    print(f"\nSpeedup:    {speedup:.2f}x")
    print(f"Разница:    {pct_diff:+.1f}%")
    
    if speedup > 1.05:
        print(f"\n✅ ВЫВОД: Батчинг БЫСТРЕЕ на {(speedup-1)*100:.1f}% — оставляем")
    elif speedup < 0.95:
        regression = (1 - speedup) * 100
        print(f"\n❌ ВЫВОД: Батчинг МЕДЛЕННЕЕ на {regression:.1f}% — убираем!")
        print(f"   (подтверждает BATCHING_FAILURE_ANALYSIS.md)")
    else:
        print(f"\n⚖️  ВЫВОД: Батчинг и loop примерно равны — без разницы")
    
    return {
        'batch_avg': batch_avg,
        'loop_avg': loop_avg,
        'speedup': speedup,
        'pct_diff': pct_diff,
    }


if __name__ == "__main__":
    import torch
    
    print("=" * 60)
    print("ТЕСТ ПРОИЗВОДИТЕЛЬНОСТИ CNN BATCHING")
    print("=" * 60)
    
    print(f"\nPyTorch version: {torch.__version__}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    print(f"torch.num_threads: {torch.get_num_threads()}")
    
    import os
    print(f"OMP_NUM_THREADS: {os.environ.get('OMP_NUM_THREADS', 'not set')}")
    print(f"MKL_NUM_THREADS: {os.environ.get('MKL_NUM_THREADS', 'not set')}")
    
    print("\n")
    
    results = test_batching_performance(n_crops=50, n_runs=5)
    
    print("\n" + "=" * 60)
    print("ГОТОВО")
    print("=" * 60)
