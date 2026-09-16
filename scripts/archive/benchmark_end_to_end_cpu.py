"""
End-to-end benchmark для полного пайплайна RoadScanner (CPU-режим).

Прогоняет весь цикл обработки через ProcessingController без GUI:
- VideoReaderThread
- DetectorThread (с выбранным режимом)
- SignHandler
- FinalHandler
- GeoJSON output

Замеряет:
- Общее время обработки
- Средний FPS
- Итоговое число знаков в GeoJSON
- Пиковое потребление памяти (если psutil доступен)
- Профилировщик-разбивку по стадиям

Использование:
    python scripts/benchmark_end_to_end_cpu.py --video test.mp4 --gpx test.gpx --output test.geojson
    python scripts/benchmark_end_to_end_cpu.py --video test.mp4 --gpx test.gpx --output test.geojson --mode pipeline
    python scripts/benchmark_end_to_end_cpu.py --video test.mp4 --gpx test.gpx --output test.geojson --save-json results.json
"""
import argparse
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def get_system_info() -> dict:
    """Собирает информацию о системе для бенчмарка."""
    import platform
    
    info = {
        "os": platform.system(),
        "os_version": platform.version(),
        "cpu": platform.processor(),
        "cpu_count": os.cpu_count(),
        "python_version": platform.python_version(),
    }
    
    # PyTorch info
    try:
        import torch
        info["pytorch_version"] = torch.__version__
        info["cuda_available"] = torch.cuda.is_available()
        info["torch_num_threads"] = torch.get_num_threads()
        
        if torch.cuda.is_available():
            info["cuda_version"] = torch.version.cuda
            info["gpu_name"] = torch.cuda.get_device_name(0)
    except Exception as e:
        logger.warning(f"Не удалось получить PyTorch info: {e}")
    
    # Git commit (если доступен)
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            stderr=subprocess.DEVNULL,
            text=True
        ).strip()
        info["git_commit"] = commit[:8]
    except:
        info["git_commit"] = "unknown"
    
    # psutil для памяти
    try:
        import psutil
        info["ram_total_gb"] = round(psutil.virtual_memory().total / (1024**3), 2)
        info["psutil_available"] = True
    except ImportError:
        info["psutil_available"] = False
    
    return info


def run_benchmark(video_path: str, gpx_path: str, output_path: str, processing_mode: str) -> dict:
    """
    Запускает end-to-end обработку и возвращает метрики.
    
    Returns:
        dict с ключами: total_time, avg_fps, total_signs, peak_memory_mb, profiler_stats
    """
    # Импорты здесь, чтобы не загружать тяжёлые библиотеки при --help
    from PyQt6.QtCore import QObject, QEventLoop
    from processing.processing_controller import ProcessingController
    from configs import config
    from configs.settings import AppSettings
    from core.profiler import profiler
    
    # Настройка config
    config.PATH_TO_VIDEO = video_path
    config.PATH_TO_GPX = gpx_path
    config.PATH_TO_GEOJSON = output_path
    config.VIDEOS = [video_path]
    config.ENABLE_PROFILING = True
    
    # Настройка settings для CPU-режима
    settings = AppSettings()
    settings.use_cuda = False  # Принудительно CPU
    settings.processing_mode = processing_mode
    
    # Устанавливаем в config (синхронизация, которая может отсутствовать)
    config.PROCESSING_MODE = processing_mode
    
    logger.info(f"Запуск benchmark:")
    logger.info(f"  Видео: {video_path}")
    logger.info(f"  GPX: {gpx_path}")
    logger.info(f"  Режим: {processing_mode}")
    logger.info(f"  CUDA: {settings.use_cuda}")
    
    # Создаём контроллер (не привязанный к реальному UI)
    class DummyParent(QObject):
        """Заглушка для ProcessingController, который ожидает parent с сигналами."""
        pass
    
    parent = DummyParent()
    controller = ProcessingController(parent)
    
    # Подготовка для замера памяти
    peak_memory_mb = None
    try:
        import psutil
        process = psutil.Process(os.getpid())
        initial_memory = process.memory_info().rss / (1024 * 1024)
        logger.info(f"  Начальная память: {initial_memory:.1f} MB")
    except ImportError:
        process = None
    
    # Подготовка event loop для ожидания завершения
    loop = QEventLoop()
    
    finished = False
    error_msg = None
    last_frames_count = 0  # Fix 1.4b: Слушаем сигнал stats вместо чтения глобала
    
    def on_finished():
        nonlocal finished
        finished = True
        loop.quit()
    
    def on_error(msg):
        nonlocal error_msg
        error_msg = msg
        loop.quit()
    
    def on_stats(frames, signs, fps):
        """Обновляем счётчик кадров из сигнала stats."""
        nonlocal last_frames_count
        last_frames_count = frames
    
    # Fix 1.4: Исправление имён сигналов
    controller.finished.connect(on_finished)
    controller.error.connect(on_error)
    
    # Fix 1.4b: Подключаемся к stats для получения реального числа обработанных кадров
    if controller._detector:
        controller._detector.stats_updated.connect(on_stats)
    elif controller._detector_pool:
        # Для detector_pool тоже нужен обработчик, но там другая структура
        # Пока используем fallback через get_result_signs в конце
        pass
    
    # Включаем профилировщик
    profiler.enable()
    profiler.reset()
    
    # Замер времени
    start_time = time.perf_counter()
    
    # Запускаем обработку
    controller.start()
    
    # Ожидаем завершения (с таймаутом 30 минут)
    timeout_ms = 30 * 60 * 1000
    loop.exec()
    
    end_time = time.perf_counter()
    total_time = end_time - start_time
    
    # Проверка ошибок
    if error_msg:
        raise RuntimeError(f"Обработка завершилась с ошибкой: {error_msg}")
    
    if not finished:
        raise RuntimeError("Обработка не завершилась (таймаут или неизвестная ошибка)")
    
    # Замер памяти
    if process:
        final_memory = process.memory_info().rss / (1024 * 1024)
        peak_memory_mb = final_memory
        logger.info(f"  Финальная память: {final_memory:.1f} MB")
    
    # Читаем результат GeoJSON
    total_signs = 0
    if os.path.exists(output_path):
        try:
            with open(output_path, "r", encoding="utf-8") as f:
                geojson = json.load(f)
                total_signs = len(geojson.get("features", []))
        except Exception as e:
            logger.warning(f"Не удалось прочитать GeoJSON: {e}")
    
    # FPS — используем last_frames_count из сигнала stats вместо глобала
    processed_frames = last_frames_count if last_frames_count > 0 else config.COUNT_PROCESSED_FRAMES
    avg_fps = processed_frames / total_time if total_time > 0 else 0
    
    logger.info(f"Обработано кадров: {processed_frames}")
    logger.info(f"Среднее FPS: {avg_fps:.2f}")
    
    # Профилировщик
    profiler_stats = {}
    if profiler.stats:
        for name, stat in profiler.stats.items():
            profiler_stats[name] = {
                "count": stat.count,
                "total_s": round(stat.total, 4),
                "mean_ms": round(stat.mean * 1000, 2),
                "p50_ms": round(stat.p50 * 1000, 2),
                "p95_ms": round(stat.p95 * 1000, 2),
            }
    
    return {
        "total_time_s": round(total_time, 2),
        "processed_frames": processed_frames,
        "avg_fps": round(avg_fps, 2),
        "total_signs": total_signs,
        "peak_memory_mb": round(peak_memory_mb, 1) if peak_memory_mb else None,
        "profiler_stats": profiler_stats,
    }


def main():
    parser = argparse.ArgumentParser(description="End-to-end benchmark для RoadScanner (CPU)")
    parser.add_argument("--video", required=True, help="Путь к видеофайлу")
    parser.add_argument("--gpx", required=True, help="Путь к GPX-файлу")
    parser.add_argument("--output", default="benchmark_output.geojson", help="Путь для GeoJSON (будет перезаписан)")
    parser.add_argument("--mode", default="single_thread", choices=["single_thread", "pipeline", "process_pool"], 
                        help="Режим обработки")
    parser.add_argument("--save-json", help="Сохранить результаты в JSON-файл")
    
    args = parser.parse_args()
    
    # Проверка существования файлов
    if not os.path.exists(args.video):
        logger.error(f"Видео не найдено: {args.video}")
        return 1
    
    if not os.path.exists(args.gpx):
        logger.error(f"GPX не найден: {args.gpx}")
        return 1
    
    # Собираем системную информацию
    logger.info("Сбор системной информации...")
    system_info = get_system_info()
    
    logger.info("\n" + "="*80)
    logger.info("СИСТЕМНАЯ ИНФОРМАЦИЯ:")
    logger.info("="*80)
    for key, value in system_info.items():
        logger.info(f"  {key}: {value}")
    
    # Запускаем бенчмарк
    try:
        logger.info("\n" + "="*80)
        logger.info("ЗАПУСК БЕНЧМАРКА...")
        logger.info("="*80)
        
        metrics = run_benchmark(args.video, args.gpx, args.output, args.mode)
        
        # Выводим результаты
        logger.info("\n" + "="*80)
        logger.info("РЕЗУЛЬТАТЫ БЕНЧМАРКА:")
        logger.info("="*80)
        logger.info(f"Общее время:            {metrics['total_time_s']} сек ({metrics['total_time_s']/60:.1f} мин)")
        logger.info(f"Обработано кадров:      {metrics['processed_frames']}")
        logger.info(f"Средний FPS:            {metrics['avg_fps']}")
        logger.info(f"Знаков в GeoJSON:       {metrics['total_signs']}")
        if metrics['peak_memory_mb']:
            logger.info(f"Пиковая память:         {metrics['peak_memory_mb']} MB")
        logger.info(f"Режим обработки:        {args.mode}")
        logger.info("="*80)
        
        # Профилировщик (топ-10)
        if metrics['profiler_stats']:
            logger.info("\nТОП-10 ОПЕРАЦИЙ ПО ВРЕМЕНИ:")
            logger.info("-"*80)
            
            sorted_ops = sorted(
                metrics['profiler_stats'].items(),
                key=lambda x: x[1]['total_s'],
                reverse=True
            )[:10]
            
            print(f"\n{'Операция':<30} {'Вызовов':<10} {'Всего (с)':<12} {'Средн. (мс)':<12}")
            print("-" * 80)
            
            for name, stats in sorted_ops:
                print(f"{name:<30} {stats['count']:<10} {stats['total_s']:<12} {stats['mean_ms']:<12}")
        
        # Сохранение в JSON
        if args.save_json:
            result = {
                "timestamp": datetime.now().isoformat(),
                "system_info": system_info,
                "benchmark_params": {
                    "video": args.video,
                    "gpx": args.gpx,
                    "processing_mode": args.mode,
                },
                "metrics": metrics,
            }
            
            with open(args.save_json, "w", encoding="utf-8") as f:
                json.dump(result, f, indent=2, ensure_ascii=False)
            
            logger.info(f"\n✅ Результаты сохранены в {args.save_json}")
        
        return 0
        
    except Exception as e:
        logger.error("="*80)
        logger.error("ОШИБКА ПРИ ВЫПОЛНЕНИИ БЕНЧМАРКА:")
        logger.error("="*80)
        logger.exception(e)
        return 1


if __name__ == "__main__":
    # КРИТИЧНО для multiprocessing на Windows
    from multiprocessing import freeze_support
    freeze_support()
    
    sys.exit(main())
