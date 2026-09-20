"""
Экспорт YOLO моделей в ONNX/OpenVINO форматы для CPU-инференса.

Использование:
    python scripts/export_models_onnx.py --format onnx
    python scripts/export_models_onnx.py --format openvino
    python scripts/export_models_onnx.py --format all
    python scripts/export_models_onnx.py --format onnx --models detect
    python scripts/export_models_onnx.py --format onnx --force
"""
import argparse
import logging
import os
import sys
import time
from pathlib import Path

# Добавляем корень проекта в sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.utils import resource_path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


# Список всех моделей из configs/sign_models.py с указанием задачи и размера входа
# КРИТИЧНО: imgsz должен точно соответствовать размеру, используемому в runtime
# (см. core/detector.py для детекторов и классификаторов)
MODELS = [
    # Детекция (path, task, imgsz)
    ("CNN_side/best.pt", "detect", 608),  # model_side_detect.predict(..., imgsz=608)
    ("lane_guidance_models/arrow_detect.pt", "detect", 640),  # стандартный размер для детекторов стрелок
    
    # Классификация - КРИТИЧНО: 32x32 (см. core/detector.py:291, 889 - cv2.resize(crop, (32, 32)))
    ("small_models/rude.pt", "classify", 32),
    ("small_models/blue.pt", "classify", 32),
    ("small_models/treugolnik.pt", "classify", 32),
    ("small_models/krug.pt", "classify", 32),
    ("small_models/red.pt", "classify", 32),
    ("small_models/servises.pt", "classify", 32),
    ("small_models/tabl l.pt", "classify", 32),
    ("small_models/tabl.pt", "classify", 32),
    ("small_models/tupic.pt", "classify", 32),
    ("small_models/5.38.pt", "classify", 32),
    ("small_models/5.9.1-5.14.pt", "classify", 32),
    ("small_models/one_side.pt", "classify", 32),
    ("small_models/danger.pt", "classify", 32),
    ("small_models/pimicanie.pt", "classify", 32),
    ("small_models/suzenie.pt", "classify", 32),
    
    # Сегментация
    ("lane_guidance_models/arrow_segment.pt", "segment", 640),
]


def get_export_path(pt_path: str, fmt: str) -> str:
    """
    Возвращает путь к экспортированному файлу.
    
    Args:
        pt_path: Путь к .pt файлу
        fmt: "onnx" или "openvino"
    
    Returns:
        Путь к экспортированному файлу/директории
    """
    base = os.path.splitext(pt_path)[0]
    if fmt == "onnx":
        return f"{base}.onnx"
    elif fmt == "openvino":
        # OpenVINO экспортируется в директорию
        return f"{base}_openvino_model"
    else:
        raise ValueError(f"Неизвестный формат: {fmt}")


def should_export(pt_path: str, export_path: str, force: bool) -> bool:
    """
    Проверяет, нужно ли экспортировать модель.
    
    Args:
        pt_path: Путь к .pt файлу
        export_path: Путь к экспортированному файлу
        force: Принудительный экспорт
    
    Returns:
        True если нужно экспортировать
    """
    if force:
        return True
    
    if not os.path.exists(pt_path):
        logger.warning(f"⚠️  Исходный файл не найден: {pt_path}")
        return False
    
    # Для ONNX проверяем файл, для OpenVINO - директорию
    if not os.path.exists(export_path):
        return True
    
    # Проверяем, что экспорт новее исходного файла
    pt_mtime = os.path.getmtime(pt_path)
    
    if os.path.isdir(export_path):
        # OpenVINO - проверяем .xml файл внутри директории
        xml_file = os.path.join(export_path, os.path.basename(export_path).replace("_openvino_model", "") + ".xml")
        if not os.path.exists(xml_file):
            return True
        export_mtime = os.path.getmtime(xml_file)
    else:
        # ONNX - проверяем сам файл
        export_mtime = os.path.getmtime(export_path)
    
    if pt_mtime > export_mtime:
        logger.info(f"  Исходный файл новее экспорта, требуется обновление")
        return True
    
    logger.info(f"  Экспорт актуален, пропускаем")
    return False


def verify_lfs_file(pt_path: str) -> bool:
    """
    Проверяет, что .pt файл — это реальные веса, а не LFS-pointer.
    
    Git LFS pointer — это текстовый файл размером ~130 байт, начинающийся с:
    version https://git-lfs.github.com/spec/v1
    
    Args:
        pt_path: Путь к .pt файлу
    
    Returns:
        True если файл валидный, False если это LFS-pointer
    
    Raises:
        RuntimeError: Если обнаружен LFS-pointer (критическая ошибка)
    """
    if not os.path.exists(pt_path):
        return False
    
    # Проверяем первые 50 байт файла
    try:
        with open(pt_path, 'rb') as f:
            header = f.read(50)
        
        # LFS pointer — это ASCII текст, начинающийся с "version https://git-lfs"
        if header.startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise RuntimeError(
                f"\n{'='*80}\n"
                f"КРИТИЧЕСКАЯ ОШИБКА: Обнаружен Git LFS pointer вместо реальных весов!\n"
                f"Файл: {pt_path}\n"
                f"\n"
                f"Это текстовая заглушка (~130 байт), а не бинарный файл модели.\n"
                f"Экспорт ONNX/OpenVINO из такого файла создаст НЕРАБОЧИЕ модели!\n"
                f"\n"
                f"РЕШЕНИЕ:\n"
                f"  1. Выполните: git lfs pull\n"
                f"  2. Дождитесь завершения загрузки всех .pt файлов\n"
                f"  3. Повторите экспорт\n"
                f"{'='*80}\n"
            )
        
        return True
        
    except UnicodeDecodeError:
        # Бинарный файл (не текст) — это нормально для .pt
        return True


def export_one(pt_path: str, task: str, imgsz: int, fmt: str, force: bool = False) -> tuple[bool, str]:
    """
    Экспортирует одну модель.
    
    Args:
        pt_path: Путь к .pt файлу (относительно корня проекта)
        task: Задача модели ("detect", "classify", "segment")
        imgsz: Размер входного изображения (КРИТИЧНО: должен совпадать с runtime!)
        fmt: Формат экспорта ("onnx", "openvino")
        force: Принудительный экспорт
    
    Returns:
        (успех, путь_к_экспорту)
    """
    try:
        # Получаем абсолютный путь через resource_path
        pt_abs = resource_path(pt_path)
        
        # КРИТИЧЕСКАЯ ПРОВЕРКА: это не LFS pointer?
        verify_lfs_file(pt_abs)
        
        export_path = get_export_path(pt_abs, fmt)
        
        if not should_export(pt_abs, export_path, force):
            return True, export_path
        
        logger.info(f"📦 Экспорт {pt_path} ({task}, imgsz={imgsz}) → {fmt.upper()}")
        
        # Импортируем ultralytics только когда нужно
        from ultralytics import YOLO
        
        # Загружаем модель
        model = YOLO(pt_abs, task=task)
        
        # Экспортируем
        start_time = time.perf_counter()
        
        if fmt == "onnx":
            # TASK 3.1 (PROMPT_FIX_SIGN_MAP_MISMATCH_AND_CPU_PERF):
            # Для классификационных моделей (32x32) используем dynamic=True для батчинга.
            # Это позволяет передавать несколько кропов за один вызов инференса.
            # Для детекторов оставляем dynamic=False (они не батчатся в текущей реализации).
            use_dynamic = (task == "classify")
            
            result = model.export(
                format="onnx",
                imgsz=imgsz,  # КРИТИЧНО: явно указываем размер из MODELS
                dynamic=use_dynamic,  # Динамический batch для classify, фиксированный для detect
                simplify=True,
                opset=12
            )
            export_path = result if isinstance(result, str) else export_path

            # TASK 4.2: Предварительная генерация optimized_model_filepath
            # При первом запуске InferenceSession ORT применяет graph optimization
            # и сохраняет результат в <model>.opt.onnx (если задан
            # sess_options.optimized_model_filepath в inference_threading.py).
            # Здесь логируем ожидаемый путь для информации, фактическое
            # сохранение происходит автоматически при первой загрузке модели.
            if isinstance(export_path, str) and export_path.endswith(".onnx"):
                opt_path = os.path.splitext(export_path)[0] + ".opt.onnx"
                logger.info(
                    f"  ℹ️  При первом запуске ORT сохранит оптимизированный граф: "
                    f"{os.path.basename(opt_path)}"
                )
                if use_dynamic:
                    logger.info(f"  ✓ Динамический batch включен (для эффективной обработки кропов)")
        elif fmt == "openvino":
            # TASK 3.1: Для OpenVINO тоже динамический batch для classify
            use_dynamic = (task == "classify")
            
            # WORKAROUND: Для segment моделей OpenVINO может выдавать ошибку
            # "Tensor without names" при dynamic=False. Используем half=False
            # для обеспечения совместимости.
            export_kwargs = {
                "format": "openvino",
                "imgsz": imgsz,
                "dynamic": use_dynamic,
            }
            
            # Для segment моделей добавляем дополнительные параметры
            if task == "segment":
                export_kwargs["half"] = False  # FP32 вместо FP16
                logger.info(f"  ℹ️  Segment модель: используется FP32 для совместимости с OpenVINO")
            
            result = model.export(**export_kwargs)
            # ultralytics возвращает путь к .xml файлу
            if isinstance(result, str):
                export_path = os.path.dirname(result)
                if use_dynamic:
                    logger.info(f"  ✓ Динамический batch включен (для эффективной обработки кропов)")
        else:
            raise ValueError(f"Неизвестный формат: {fmt}")
        
        elapsed = time.perf_counter() - start_time
        
        # Получаем размер экспортированного файла
        if os.path.isdir(export_path):
            # Для директории суммируем размер всех файлов
            total_size = sum(
                os.path.getsize(os.path.join(dp, f))
                for dp, dn, filenames in os.walk(export_path)
                for f in filenames
            )
        else:
            total_size = os.path.getsize(export_path)
        
        size_mb = total_size / (1024 * 1024)
        
        logger.info(f"  ✅ Экспорт завершён за {elapsed:.1f}с, размер: {size_mb:.1f} МБ")
        return True, export_path
        
    except Exception as e:
        logger.error(f"  ❌ Ошибка экспорта {pt_path}: {e}")
        return False, ""


def main():
    parser = argparse.ArgumentParser(
        description="Экспорт YOLO моделей для оптимизированного CPU-инференса"
    )
    parser.add_argument(
        "--format",
        choices=["onnx", "openvino", "all"],
        default="all",
        help="Формат экспорта (по умолчанию: оба формата)"
    )
    parser.add_argument(
        "--models",
        choices=["all", "detect", "classify", "segment"],
        default="all",
        help="Какие модели экспортировать"
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Принудительный экспорт, даже если файлы актуальны"
    )
    
    args = parser.parse_args()
    
    # Проверяем доступность библиотек
    try:
        import ultralytics
        logger.info(f"✅ ultralytics {ultralytics.__version__}")
    except ImportError:
        logger.error("❌ ultralytics не установлен. Установите: pip install ultralytics")
        return 1
    
    # Определяем форматы для экспорта
    formats = []
    if args.format == "all":
        formats = ["onnx", "openvino"]
    else:
        formats = [args.format]
    
    # Проверяем доступность библиотек для каждого формата
    for fmt in formats:
        if fmt == "onnx":
            try:
                import onnx
                logger.info(f"✅ onnx {onnx.__version__}")
            except ImportError:
                logger.error("❌ onnx не установлен. Установите: pip install onnx")
                return 1
        elif fmt == "openvino":
            try:
                import openvino
                logger.info(f"✅ openvino {openvino.__version__}")
            except ImportError:
                logger.error("❌ openvino не установлен. Установите: pip install openvino openvino-dev")
                return 1
    
    # Фильтруем модели по типу
    models_to_export = MODELS
    if args.models != "all":
        models_to_export = [(path, task, imgsz) for path, task, imgsz in MODELS if task == args.models]
    
    # Экспортируем для каждого формата
    overall_success = True
    for fmt in formats:
        logger.info(f"\n{'='*80}")
        logger.info(f"Экспорт {len(models_to_export)} моделей в формат {fmt.upper()}")
        logger.info(f"{'='*80}\n")
        
        # Экспортируем модели
        success_count = 0
        total_count = len(models_to_export)
        
        for pt_path, task, imgsz in models_to_export:
            success, export_path = export_one(pt_path, task, imgsz, fmt, args.force)
            if success:
                success_count += 1
        
        # Итоговая статистика
        logger.info(f"\n{'='*80}")
        logger.info(f"Экспорт {fmt.upper()} завершён: {success_count}/{total_count} успешно")
        logger.info(f"{'='*80}")
        
        if success_count < total_count:
            logger.warning(f"⚠️  Некоторые модели не удалось экспортировать в {fmt.upper()}")
            overall_success = False
    
    return 0 if overall_success else 1


if __name__ == "__main__":
    sys.exit(main())
