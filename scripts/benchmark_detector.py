"""
Benchmark-скрипт для профилирования core/detector.py
Используется для замера производительности ДО и ПОСЛЕ оптимизаций.

Использование:
    python scripts/benchmark_detector.py --video path/to/video.mp4 --frames 100
    python scripts/benchmark_detector.py --video path/to/video.mp4 --frames 100 --profile
"""
import argparse
import cProfile
import logging
import os
import pstats
import sys
import time
from pathlib import Path

import cv2
import numpy as np

# Добавляем корневую директорию в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.detector import Detector
from core.profiler import profiler

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def load_test_frames(video_path: str, max_frames: int) -> list[np.ndarray]:
    """Загружает тестовые кадры из видео."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Видео не найдено: {video_path}")
    
    cap = cv2.VideoCapture(video_path)
    frames = []
    
    logger.info(f"Загрузка {max_frames} кадров из {video_path}...")
    
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            logger.warning(f"Видео закончилось на кадре {len(frames)}")
            break
        frames.append(frame)
    
    cap.release()
    logger.info(f"Загружено {len(frames)} кадров")
    return frames


def benchmark_detector(frames: list[np.ndarray], skip_ocr: bool = True) -> dict:
    """
    Прогоняет детектор на всех кадрах и возвращает метрики.
    
    Returns:
        dict с ключами: total_time, fps, total_detections, avg_detections_per_frame
    """
    detector = Detector()
    
    logger.info(f"Запуск бенчмарка на {len(frames)} кадрах (skip_ocr={skip_ocr})...")
    
    total_detections = 0
    start_time = time.perf_counter()
    
    for i, frame in enumerate(frames):
        detections = detector.detect(frame, skip_ocr=skip_ocr)
        total_detections += len(detections)
        
        if (i + 1) % 10 == 0:
            elapsed = time.perf_counter() - start_time
            fps = (i + 1) / elapsed
            logger.info(f"  Обработано {i+1}/{len(frames)} кадров, FPS: {fps:.2f}")
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    fps = len(frames) / total_time
    avg_detections = total_detections / len(frames)
    
    return {
        "total_time": total_time,
        "fps": fps,
        "total_detections": total_detections,
        "avg_detections_per_frame": avg_detections,
        "frames": len(frames),
    }


def run_profiling(frames: list[np.ndarray], skip_ocr: bool = True) -> None:
    """Запускает cProfile на детекторе."""
    logger.info("Запуск профилирования с cProfile...")
    
    detector = Detector()
    
    prof = cProfile.Profile()
    prof.enable()
    
    for frame in frames:
        detector.detect(frame, skip_ocr=skip_ocr)
    
    prof.disable()
    
    # Сохраняем результаты
    output_file = "benchmark_profile.stats"
    prof.dump_stats(output_file)
    logger.info(f"Профиль сохранён в {output_file}")
    
    # Выводим топ-20 функций по cumulative time
    logger.info("\nТОП-20 функций по cumulative time:")
    stats = pstats.Stats(prof)
    stats.strip_dirs()
    stats.sort_stats("cumulative")
    stats.print_stats(20)
    
    logger.info("\nТОП-20 функций по tottime:")
    stats.sort_stats("tottime")
    stats.print_stats(20)


def print_profiler_stats():
    """Выводит статистику из core.profiler."""
    logger.info("\n" + "="*80)
    logger.info("СТАТИСТИКА ИЗ core.profiler:")
    logger.info("="*80)
    
    if not profiler.stats:
        logger.info("Профилировщик не содержит данных")
        return
    
    # Сортируем по total time
    sorted_stats = sorted(
        profiler.stats.values(),
        key=lambda s: s.total,
        reverse=True
    )
    
    print(f"\n{'Операция':<30} {'Вызовов':<10} {'Всего (с)':<12} {'Средн. (мс)':<12} {'% от общего':<12}")
    print("-" * 80)
    
    total_time = sum(s.total for s in profiler.stats.values())
    
    for stat in sorted_stats:
        pct = (stat.total / total_time * 100) if total_time > 0 else 0
        print(f"{stat.name:<30} {stat.count:<10} {stat.total:<12.4f} {stat.mean*1000:<12.2f} {pct:<12.1f}")
    
    print("-" * 80)
    print(f"{'ИТОГО':<30} {'':<10} {total_time:<12.4f}")


def main():
    parser = argparse.ArgumentParser(description="Benchmark для core/detector.py")
    parser.add_argument("--video", required=True, help="Путь к тестовому видео")
    parser.add_argument("--frames", type=int, default=100, help="Количество кадров для теста")
    parser.add_argument("--profile", action="store_true", help="Запустить cProfile")
    parser.add_argument("--with-ocr", action="store_true", help="Включить OCR (по умолчанию выключен)")
    parser.add_argument("--force-cpu", action="store_true", help="Принудительно использовать CPU (даже если CUDA доступна)")
    parser.add_argument("--backend", choices=["torch", "onnx", "openvino"], default="torch", 
                       help="Бэкенд для CPU-инференса (только с --force-cpu)")
    
    args = parser.parse_args()
    
    # Принудительное использование CPU если запрошено
    if args.force_cpu:
        import torch
        logger.info("⚠️ Принудительное использование CPU (--force-cpu)")
        
        # Временно отключаем CUDA для этого процесса
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        
        # Проверяем, что сработало
        if torch.cuda.is_available():
            logger.warning("CUDA всё ещё доступна, попробуйте перезапустить скрипт")
        else:
            logger.info("✅ CPU-режим активирован")
        
        # Устанавливаем backend
        from configs.settings import get_app_settings
        settings = get_app_settings()
        settings.use_cuda = False
        settings.cpu_inference_backend = args.backend
        logger.info(f"✅ Backend установлен: {args.backend}")
        
        # Сбрасываем кэш моделей
        from configs import sign_models
        sign_models.reload_all_models_if_device_changed()
    
    skip_ocr = not args.with_ocr
    
    # Загружаем кадры
    frames = load_test_frames(args.video, args.frames)
    
    if len(frames) == 0:
        logger.error("Не удалось загрузить кадры из видео")
        return 1
    
    # Запускаем бенчмарк
    if args.profile:
        run_profiling(frames[:min(30, len(frames))], skip_ocr=skip_ocr)
    else:
        profiler.enable()  # Включаем профилировщик
        profiler.reset()
        metrics = benchmark_detector(frames, skip_ocr=skip_ocr)
        
        logger.info("\n" + "="*80)
        logger.info("РЕЗУЛЬТАТЫ БЕНЧМАРКА:")
        logger.info("="*80)
        logger.info(f"Кадров обработано:      {metrics['frames']}")
        logger.info(f"Время выполнения:       {metrics['total_time']:.2f} сек")
        logger.info(f"FPS:                    {metrics['fps']:.2f}")
        logger.info(f"Всего детекций:         {metrics['total_detections']}")
        logger.info(f"Детекций на кадр:       {metrics['avg_detections_per_frame']:.1f}")
        logger.info(f"OCR:                    {'включен' if not skip_ocr else 'выключен'}")
        logger.info(f"Режим:                  {'CPU (force)' if args.force_cpu else 'auto'}")
        if args.force_cpu:
            logger.info(f"Backend:                {args.backend}")
        logger.info("="*80)
        
        print_profiler_stats()
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
