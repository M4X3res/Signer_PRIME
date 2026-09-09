"""
Тест выбора backend для моделей в зависимости от настроек use_cuda.
"""
import os
import sys
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%H:%M:%S'
)

logger = logging.getLogger(__name__)

def test_backend_selection():
    """Тест логики выбора backend."""
    from configs.settings import get_app_settings
    from configs.sign_models import _resolve_device, _LazyModel, _p
    
    settings = get_app_settings()
    
    logger.info("=" * 70)
    logger.info("ТЕСТ ВЫБОРА BACKEND ДЛЯ МОДЕЛЕЙ")
    logger.info("=" * 70)
    
    # Проверяем доступность CUDA
    try:
        import torch
        cuda_available = torch.cuda.is_available()
        if cuda_available:
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"✅ CUDA доступна: {gpu_name}")
        else:
            logger.info("❌ CUDA недоступна")
    except Exception as e:
        logger.error(f"Ошибка проверки CUDA: {e}")
        cuda_available = False
    
    logger.info("-" * 70)
    logger.info("ТЕКУЩИЕ НАСТРОЙКИ:")
    logger.info(f"  use_cuda: {settings.use_cuda}")
    logger.info(f"  cpu_inference_backend: {settings.cpu_inference_backend}")
    logger.info("-" * 70)
    
    # Определяем device
    device = _resolve_device()
    logger.info(f"Определённый device: {device}")
    
    # Определяем backend через временный экземпляр LazyModel
    temp_model = _LazyModel(_p("CNN_side/best.pt"), task="detect")
    backend = temp_model._resolve_backend()
    logger.info(f"Определённый backend: {backend}")
    
    logger.info("-" * 70)
    logger.info("ОЖИДАЕМОЕ ПОВЕДЕНИЕ:")
    
    if settings.use_cuda:
        if cuda_available:
            logger.info("  ✅ use_cuda=True и CUDA доступна")
            logger.info("  → Должны использоваться: PyTorch backend + CUDA device")
            logger.info(f"  → Фактически: backend={backend}, device={device}")
            
            if backend == "torch" and device == "cuda:0":
                logger.info("  ✅ КОРРЕКТНО: Используются старые .pt модели на CUDA")
            else:
                logger.error("  ❌ ОШИБКА: Неправильный backend или device!")
        else:
            logger.warning("  ⚠️ use_cuda=True но CUDA недоступна")
            logger.info("  → Должны использоваться: PyTorch backend + CPU device")
            logger.info(f"  → Фактически: backend={backend}, device={device}")
            
            if backend == "torch" and device == "cpu":
                logger.info("  ✅ КОРРЕКТНО: Используются .pt модели на CPU")
            else:
                logger.error("  ❌ ОШИБКА: Неправильный backend или device!")
    else:
        logger.info("  ✅ use_cuda=False (CPU режим)")
        logger.info(f"  → Должны использоваться: {settings.cpu_inference_backend} backend + CPU device")
        logger.info(f"  → Фактически: backend={backend}, device={device}")
        
        if backend == settings.cpu_inference_backend and device == "cpu":
            logger.info(f"  ✅ КОРРЕКТНО: Используется {backend} backend на CPU")
        else:
            logger.error("  ❌ ОШИБКА: Неправильный backend или device!")
    
    logger.info("=" * 70)
    
    # Проверяем переменную окружения ONNX Runtime
    ort_disable_cuda = os.environ.get("ORT_DISABLE_CUDA", "не установлена")
    logger.info(f"ORT_DISABLE_CUDA: {ort_disable_cuda}")
    
    if settings.use_cuda:
        if ort_disable_cuda == "1":
            logger.warning("  ⚠️ ВНИМАНИЕ: ORT_DISABLE_CUDA=1 при use_cuda=True")
            logger.info("     (Не критично, т.к. при CUDA используется PyTorch, а не ONNX)")
    else:
        if ort_disable_cuda != "1":
            logger.warning("  ⚠️ ВНИМАНИЕ: ORT_DISABLE_CUDA не установлена при CPU режиме")
            logger.info("     (Может вызывать warning'и при использовании ONNX Runtime)")
    
    logger.info("=" * 70)


if __name__ == "__main__":
    # Имитируем настройку окружения как в main.py
    try:
        from configs.settings import get_app_settings
        settings = get_app_settings()
        if not settings.use_cuda:
            os.environ["ORT_DISABLE_CUDA"] = "1"
            logger.info("Установлена ORT_DISABLE_CUDA=1 (CPU режим)")
    except Exception as e:
        logger.error(f"Ошибка настройки окружения: {e}")
    
    test_backend_selection()
