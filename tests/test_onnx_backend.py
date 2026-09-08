"""
tests/test_onnx_backend.py
Тесты для ONNX/OpenVINO CPU-инференс backend (BLOCK M).
"""
import pytest
import os


def test_call_applies_same_cpu_pin_as_predict():
    """
    Регрессия на BUG-1: __call__ обязан вести себя как predict().
    
    Проблема: основной путь классификации знаков (core/detector.py) вызывает
    модели через __call__ (model(crop)), а не через .predict(). Если __call__
    не проходит через ту же логику CPU-pin, что и predict(), то весь фикс
    BACKEND_SELECTION_FIX.md становится бесполезным для реального пайплайна.
    """
    from configs.sign_models import _LazyModel
    
    captured = {}
    
    class FakeYOLOModel:
        predictor = None
        def predict(self, *a, **kw):
            captured['kwargs'] = kw
            return ["ok"]
    
    lm = _LazyModel(lambda: "fake.pt", task="classify")
    lm._model = FakeYOLOModel()
    lm._backend = "onnx"
    
    # Вызов через __call__
    lm(object())
    
    assert captured['kwargs'].get('device') == 'cpu', (
        "__call__ должен форсировать device='cpu' так же, как .predict()"
    )


def test_openvino_backend_also_gets_cpu_pin():
    """
    BUG-6: OpenVINO backend тоже должен получать device='cpu' pin для симметрии с ONNX.
    """
    from configs.sign_models import _LazyModel
    
    captured = {}
    
    class FakeYOLOModel:
        predictor = None
        def predict(self, *a, **kw):
            captured['kwargs'] = kw
            return ["ok"]
    
    lm = _LazyModel(lambda: "fake.pt", task="classify")
    lm._model = FakeYOLOModel()
    lm._backend = "openvino"
    
    # Вызов через predict
    lm.predict(object())
    
    assert captured['kwargs'].get('device') == 'cpu', (
        "OpenVINO backend должен принудительно устанавливать device='cpu'"
    )


def test_torch_backend_not_affected_by_cpu_pin():
    """
    Проверка, что PyTorch backend не получает лишний device='cpu' pin.
    Когда use_cuda=True, PyTorch должен сам выбирать device (cuda или cpu).
    """
    from configs.sign_models import _LazyModel
    
    captured = {}
    
    class FakeYOLOModel:
        predictor = None
        def predict(self, *a, **kw):
            captured['kwargs'] = kw
            return ["ok"]
    
    lm = _LazyModel(lambda: "fake.pt", task="classify")
    lm._model = FakeYOLOModel()
    lm._backend = "torch"
    
    # Вызов через predict
    lm.predict(object())
    
    # PyTorch backend не должен получать принудительный device='cpu'
    assert 'device' not in captured['kwargs'] or captured['kwargs']['device'] != 'cpu', (
        "PyTorch backend не должен получать принудительный device='cpu'"
    )


@pytest.mark.parametrize("backend", ["torch", "onnx", "openvino"])
@pytest.mark.parametrize("batch_size", [1, 3, 8])
def test_backend_with_different_batch_sizes(backend, batch_size):
    """
    Параметризованный тест: разные backend × разные batch_size.
    
    Скипается, если соответствующие .onnx/_openvino_model файлы отсутствуют,
    чтобы не ломать CI на машинах без экспортированных моделей.
    """
    import torch
    import numpy as np
    from configs.settings import get_app_settings
    from configs.sign_models import rube_modal
    
    # Проверяем доступность моделей
    if backend == "onnx":
        from utils import resource_path
        onnx_path = resource_path("small_models/rude.onnx")
        if not os.path.exists(onnx_path):
            pytest.skip(f"ONNX модель не найдена: {onnx_path}")
    
    elif backend == "openvino":
        from utils import resource_path
        ov_path = resource_path("small_models/rude_openvino_model/rude.xml")
        if not os.path.exists(ov_path):
            pytest.skip(f"OpenVINO модель не найдена: {ov_path}")
    
    # Настраиваем backend
    settings = get_app_settings()
    original_cuda = settings.use_cuda
    original_backend = settings.cpu_inference_backend
    
    try:
        settings.use_cuda = False
        settings.cpu_inference_backend = backend
        
        # Сбрасываем кэш модели
        rube_modal._model = None
        rube_modal._device = None
        rube_modal._backend = None
        
        # Создаём батч изображений 32x32 RGB
        images = np.random.randint(0, 255, (batch_size, 32, 32, 3), dtype=np.uint8)
        
        # Вызываем модель
        results = rube_modal(images, verbose=False)
        
        # Проверяем, что получили результаты
        assert len(results) == batch_size, (
            f"Ожидается {batch_size} результатов, получено {len(results)}"
        )
        
        # Проверяем, что backend действительно загрузился
        if backend != "torch":
            assert rube_modal._backend == backend, (
                f"Ожидается backend={backend}, получено {rube_modal._backend}"
            )
    
    finally:
        # Восстанавливаем настройки
        settings.use_cuda = original_cuda
        settings.cpu_inference_backend = original_backend
        rube_modal._model = None
        rube_modal._device = None
        rube_modal._backend = None


def test_model_consistency_between_backends():
    """
    Тест консистентности: на случайных кропах сравниваем top1-класс между
    PyTorch и ONNX (если модели есть).
    
    Допускаем не более 1 расхождения из 20 (из-за numerical precision).
    """
    import torch
    import numpy as np
    from configs.settings import get_app_settings
    from configs.sign_models import rube_modal
    from utils import resource_path
    
    # Проверяем наличие ONNX модели
    onnx_path = resource_path("small_models/rude.onnx")
    if not os.path.exists(onnx_path):
        pytest.skip(f"ONNX модель не найдена: {onnx_path}")
    
    settings = get_app_settings()
    original_cuda = settings.use_cuda
    original_backend = settings.cpu_inference_backend
    
    try:
        # Генерируем 20 случайных кропов
        n_samples = 20
        images = np.random.randint(0, 255, (n_samples, 32, 32, 3), dtype=np.uint8)
        
        # Получаем результаты с PyTorch backend
        settings.use_cuda = False
        settings.cpu_inference_backend = "torch"
        rube_modal._model = None
        rube_modal._device = None
        rube_modal._backend = None
        
        torch_results = []
        for img in images:
            result = rube_modal(img, verbose=False)[0]
            torch_results.append(result.probs.top1)
        
        # Получаем результаты с ONNX backend
        settings.cpu_inference_backend = "onnx"
        rube_modal._model = None
        rube_modal._device = None
        rube_modal._backend = None
        
        onnx_results = []
        for img in images:
            result = rube_modal(img, verbose=False)[0]
            onnx_results.append(result.probs.top1)
        
        # Сравниваем результаты
        mismatches = sum(t != o for t, o in zip(torch_results, onnx_results))
        
        assert mismatches <= 1, (
            f"Слишком много расхождений между PyTorch и ONNX: {mismatches}/20. "
            f"Torch: {torch_results}, ONNX: {onnx_results}"
        )
    
    finally:
        # Восстанавливаем настройки
        settings.use_cuda = original_cuda
        settings.cpu_inference_backend = original_backend
        rube_modal._model = None
        rube_modal._device = None
        rube_modal._backend = None
