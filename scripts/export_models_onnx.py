"""
Экспорт YOLO моделей в ONNX/OpenVINO форматы для CPU-инференса.

Использование:
    python scripts/export_models_onnx.py --format onnx
    python scripts/export_models_onnx.py --format openvino
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


# Список всех моделей из configs/sign_models.py с указанием задачи
MODELS = [
    # Детекция
    ("CNN_side/best.pt", "detect"),
    ("lane_guidance_models/arrow_detect.pt", "detect"),
    
    # Классификация
    ("small_models/rude.pt", "classify"),
    ("small_models/blue.pt", "classify"),
    ("small_models/treugolnik.pt", "classify"),
    ("small_models/krug.pt", "classify"),
    ("small_models/red.pt", "classify"),
    ("small_models/servises.pt", "classify"),
    ("small_models/tabl l.pt", "classify"),
    ("small_models/tabl.pt", "classify"),
    ("small_models/tupic.pt", "classify"),
    ("small_models/5.38.pt", "classify"),
    ("small_models/5.9.1-5.14.pt", "classify"),
    ("small_models/one_side.pt", "classify"),
    ("small_models/danger.pt", "classify"),
    ("small_models/pimicanie.pt", "classify"),
    ("small_models/suzenie.pt", "classify"),
    
    # Сегментация
    ("lane_guidance_models/arrow_segment.pt", "segment"),
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


def export_one(pt_path: str, task: str, fmt: str, force: bool = False) -> tuple[bool, str]:
    """
    Экспортирует одну модель.
    
    Args:
        pt_path: Путь к .pt файлу (относительно корня проекта)
        task: Задача модели ("detect", "classify", "segment")
        fmt: Формат экспорта ("onnx", "openvino")
        force: Принудительный экспорт
    
    Returns:
        (успех, путь_к_экспорту)
    """
    try:
        # Получаем абсолютный путь через resource_path
        pt_abs = resource_path(pt_path)
        export_path = get_export_path(pt_abs, fmt)
        
        if not should_export(pt_abs, export_path, force):
            return True, export_path
        
        logger.info(f"📦 Экспорт {pt_path} ({task}) → {fmt.upper()}")
        
        # Импортируем ultralytics только когда нужно
        from ultralytics import YOLO
        
        # Загружаем модель
        model = YOLO(pt_abs, task=task)
        
        # Экспортируем
        start_time = time.perf_counter()
        
        if fmt == "onnx":
            # BLOCK M: Для всех типов моделей используем dynamic=True
            # Это позволяет использовать разные размеры входа (608, 640, 960 и т.д.)
            # Классификационные модели требуют dynamic для батч-инференса,
            # Detection/Segment модели тоже выигрывают от динамического размера
            result = model.export(
                format="onnx",
                dynamic=True,  # Всегда True для гибкости
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
        elif fmt == "openvino":
            # BLOCK M: OpenVINO тоже с dynamic=True для гибкости размера входа
            result = model.export(
                format="openvino",
                dynamic=True
            )
            # ultralytics возвращает путь к .xml файлу
            if isinstance(result, str):
                export_path = os.path.dirname(result)
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
        choices=["onnx", "openvino"],
        default="onnx",
        help="Формат экспорта"
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
    
    if args.format == "onnx":
        try:
            import onnx
            logger.info(f"✅ onnx {onnx.__version__}")
        except ImportError:
            logger.error("❌ onnx не установлен. Установите: pip install onnx")
            return 1
    elif args.format == "openvino":
        try:
            import openvino
            logger.info(f"✅ openvino {openvino.__version__}")
        except ImportError:
            logger.error("❌ openvino не установлен. Установите: pip install openvino openvino-dev")
            return 1
    
    # Фильтруем модели по типу
    models_to_export = MODELS
    if args.models != "all":
        models_to_export = [(path, task) for path, task in MODELS if task == args.models]
    
    logger.info(f"\n{'='*80}")
    logger.info(f"Экспорт {len(models_to_export)} моделей в формат {args.format.upper()}")
    logger.info(f"{'='*80}\n")
    
    # Экспортируем модели
    success_count = 0
    total_count = len(models_to_export)
    
    for pt_path, task in models_to_export:
        success, export_path = export_one(pt_path, task, args.format, args.force)
        if success:
            success_count += 1
    
    # Итоговая статистика
    logger.info(f"\n{'='*80}")
    logger.info(f"Экспорт завершён: {success_count}/{total_count} успешно")
    logger.info(f"{'='*80}")
    
    if success_count < total_count:
        logger.warning(f"⚠️  Некоторые модели не удалось экспортировать")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
