"""
Тест загрузки ONNX моделей.
"""
import os
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)

def test_onnx_loading():
    """Тест загрузки ONNX модели."""
    # Устанавливаем окружение для CPU режима
    os.environ["ORT_DISABLE_CUDA"] = "1"
    os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
    os.environ["OMP_NUM_THREADS"] = "1"
    
    logger.info("=" * 70)
    logger.info("ТЕСТ ЗАГРУЗКИ ONNX МОДЕЛЕЙ")
    logger.info("=" * 70)
    
    # Устанавливаем CPU режим
    from configs.settings import get_app_settings
    settings = get_app_settings()
    original_use_cuda = settings.use_cuda
    original_backend = settings.cpu_inference_backend
    
    settings.use_cuda = False
    settings.cpu_inference_backend = "onnx"
    
    logger.info(f"Настройки: use_cuda={settings.use_cuda}, backend={settings.cpu_inference_backend}")
    logger.info("-" * 70)
    
    try:
        # Импортируем модели
        from configs.sign_models import model_side_detect, rube_modal
        
        logger.info("Тест 1: Загрузка model_side_detect...")
        try:
            # Просто обращаемся к модели, чтобы вызвать ленивую загрузку
            _ = model_side_detect._load()
            logger.info(f"  ✅ model_side_detect загружена: backend={model_side_detect._backend}")
        except Exception as e:
            logger.error(f"  ❌ Ошибка загрузки model_side_detect: {e}")
        
        logger.info("-" * 70)
        logger.info("Тест 2: Загрузка rube_modal...")
        try:
            _ = rube_modal._load()
            logger.info(f"  ✅ rube_modal загружена: backend={rube_modal._backend}")
        except Exception as e:
            logger.error(f"  ❌ Ошибка загрузки rube_modal: {e}")
        
        logger.info("-" * 70)
        logger.info("Тест 3: Проверка ONNX файлов...")
        onnx_files = [
            "CNN_side/best.onnx",
            "small_models/rude.onnx",
        ]
        
        for onnx_file in onnx_files:
            from utils import resource_path
            path = resource_path(onnx_file)
            exists = os.path.exists(path)
            logger.info(f"  {onnx_file}: {'✅ существует' if exists else '❌ не найден'}")
        
    finally:
        # Восстанавливаем настройки
        settings.use_cuda = original_use_cuda
        settings.cpu_inference_backend = original_backend
    
    logger.info("=" * 70)


if __name__ == "__main__":
    test_onnx_loading()
