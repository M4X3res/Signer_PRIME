"""
Регрессионный тест для detector.py — проверка идентичности результатов
после рефакторинга с батчингом.

Сравнивает результаты детекции кадр-за-кадром:
- Количество детекций
- bbox координаты
- yolo_class
- cnn_class
- is_side

Использование:
    # Записать baseline (до рефакторинга)
    python scripts/test_detector_regression.py --video test.mp4 --frames 50 --save-baseline
    
    # Сравнить с baseline (после рефакторинга)
    python scripts/test_detector_regression.py --video test.mp4 --frames 50 --compare
"""
import argparse
import hashlib
import json
import logging
import os
import sys
from dataclasses import asdict
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).parent.parent))

from core.detector import Detector, RawDetection

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def serialize_detection(d: RawDetection) -> dict:
    """Сериализует RawDetection в JSON-совместимый dict."""
    return {
        "box": list(d.box),
        "yolo_class": d.yolo_class,
        "cnn_class": d.cnn_class,
        "is_side": d.is_side,
        # text и color игнорируем (text может быть недетерминированным)
    }


def compute_frame_hash(frame: np.ndarray) -> str:
    """Вычисляет хэш кадра для идентификации."""
    # Используем MD5 первых 100 строк для скорости
    sample = frame[:100, :100, :].tobytes()
    return hashlib.md5(sample).hexdigest()[:16]


def load_test_frames(video_path: str, max_frames: int) -> list[tuple[np.ndarray, str]]:
    """Загружает кадры из видео с хэшами."""
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Видео не найдено: {video_path}")
    
    cap = cv2.VideoCapture(video_path)
    frames = []
    
    logger.info(f"Загрузка {max_frames} кадров из {video_path}...")
    
    frame_idx = 0
    while len(frames) < max_frames:
        ret, frame = cap.read()
        if not ret:
            logger.warning(f"Видео закончилось на кадре {len(frames)}")
            break
        
        # Берём каждый 5-й кадр для разнообразия
        if frame_idx % 5 == 0:
            frame_hash = compute_frame_hash(frame)
            frames.append((frame, frame_hash))
        
        frame_idx += 1
    
    cap.release()
    logger.info(f"Загружено {len(frames)} кадров")
    return frames


def save_baseline(frames: list[tuple[np.ndarray, str]], output_path: str) -> None:
    """Запускает детектор на кадрах и сохраняет результаты как baseline."""
    detector = Detector()
    
    baseline = {}
    
    logger.info(f"Создание baseline на {len(frames)} кадрах...")
    
    for i, (frame, frame_hash) in enumerate(frames):
        detections = detector.detect(frame, skip_ocr=True)
        
        baseline[frame_hash] = {
            "frame_idx": i,
            "detections": [serialize_detection(d) for d in detections]
        }
        
        if (i + 1) % 10 == 0:
            logger.info(f"  Обработано {i+1}/{len(frames)} кадров")
    
    # Сохраняем в JSON
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(baseline, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Baseline сохранён в {output_path}")


def compare_with_baseline(frames: list[tuple[np.ndarray, str]], baseline_path: str) -> bool:
    """Сравнивает текущие результаты с baseline."""
    if not os.path.exists(baseline_path):
        raise FileNotFoundError(f"Baseline не найден: {baseline_path}")
    
    with open(baseline_path, "r", encoding="utf-8") as f:
        baseline = json.load(f)
    
    detector = Detector()
    
    logger.info(f"Сравнение с baseline на {len(frames)} кадрах...")
    
    mismatches = []
    total_detections_baseline = 0
    total_detections_current = 0
    
    for i, (frame, frame_hash) in enumerate(frames):
        if frame_hash not in baseline:
            logger.warning(f"Кадр {i} (hash={frame_hash}) отсутствует в baseline, пропускаем")
            continue
        
        expected = baseline[frame_hash]["detections"]
        detections = detector.detect(frame, skip_ocr=True)
        actual = [serialize_detection(d) for d in detections]
        
        total_detections_baseline += len(expected)
        total_detections_current += len(actual)
        
        # Сравнение
        if len(expected) != len(actual):
            mismatches.append({
                "frame_idx": i,
                "frame_hash": frame_hash,
                "error": "count_mismatch",
                "expected_count": len(expected),
                "actual_count": len(actual),
            })
            logger.warning(f"  Кадр {i}: детекций {len(actual)}, ожидалось {len(expected)}")
        else:
            # Сравниваем каждую детекцию (порядок может различаться, используем множества)
            expected_set = {json.dumps(d, sort_keys=True) for d in expected}
            actual_set = {json.dumps(d, sort_keys=True) for d in actual}
            
            if expected_set != actual_set:
                missing = expected_set - actual_set
                extra = actual_set - expected_set
                
                mismatches.append({
                    "frame_idx": i,
                    "frame_hash": frame_hash,
                    "error": "content_mismatch",
                    "missing": list(missing),
                    "extra": list(extra),
                })
                logger.warning(f"  Кадр {i}: несоответствие содержимого детекций")
        
        if (i + 1) % 10 == 0:
            logger.info(f"  Проверено {i+1}/{len(frames)} кадров")
    
    # Итоговый отчёт
    logger.info("\n" + "="*80)
    logger.info("РЕЗУЛЬТАТЫ РЕГРЕССИОННОГО ТЕСТА:")
    logger.info("="*80)
    logger.info(f"Кадров проверено:         {len(frames)}")
    logger.info(f"Детекций baseline:        {total_detections_baseline}")
    logger.info(f"Детекций текущих:         {total_detections_current}")
    logger.info(f"Кадров с расхождениями:   {len(mismatches)}")
    
    if len(mismatches) == 0:
        logger.info("✅ ТЕСТ ПРОЙДЕН: Результаты идентичны")
        return True
    else:
        logger.error(f"❌ ТЕСТ ПРОВАЛЕН: {len(mismatches)} кадров с расхождениями")
        
        # Выводим детали первых 5 несоответствий
        logger.info("\nПервые несоответствия:")
        for mm in mismatches[:5]:
            logger.info(f"  Кадр {mm['frame_idx']}: {mm['error']}")
            if mm["error"] == "count_mismatch":
                logger.info(f"    Ожидалось: {mm['expected_count']}, получено: {mm['actual_count']}")
            else:
                logger.info(f"    Пропущено: {len(mm['missing'])}, лишних: {len(mm['extra'])}")
        
        # Сохраняем полный отчёт
        mismatch_report = "regression_test_mismatches.json"
        with open(mismatch_report, "w", encoding="utf-8") as f:
            json.dump(mismatches, f, indent=2, ensure_ascii=False)
        logger.info(f"\nПолный отчёт сохранён в {mismatch_report}")
        
        return False


def main():
    parser = argparse.ArgumentParser(description="Регрессионный тест для detector.py")
    parser.add_argument("--video", required=True, help="Путь к тестовому видео")
    parser.add_argument("--frames", type=int, default=50, help="Количество кадров для теста")
    parser.add_argument("--save-baseline", action="store_true", help="Сохранить baseline")
    parser.add_argument("--compare", action="store_true", help="Сравнить с baseline")
    parser.add_argument("--baseline-file", default="regression_baseline.json", help="Путь к baseline файлу")
    
    args = parser.parse_args()
    
    if not args.save_baseline and not args.compare:
        parser.error("Укажите --save-baseline или --compare")
    
    # Загружаем кадры
    frames = load_test_frames(args.video, args.frames)
    
    if len(frames) == 0:
        logger.error("Не удалось загрузить кадры из видео")
        return 1
    
    # Выполняем действие
    if args.save_baseline:
        save_baseline(frames, args.baseline_file)
        return 0
    
    if args.compare:
        success = compare_with_baseline(frames, args.baseline_file)
        return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
