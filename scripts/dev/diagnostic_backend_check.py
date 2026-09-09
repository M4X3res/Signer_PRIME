# diagnostic_backend_check.py — временный скрипт для диагностики ONNX/OpenVINO backend
import numpy as np
import sys
import os

# Добавляем корень проекта в path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

for backend in ("onnx", "openvino"):
    print(f"\n{'='*80}")
    print(f"ТЕСТ BACKEND: {backend.upper()}")
    print(f"{'='*80}\n")
    
    # Сброс настроек и импортов для чистоты теста
    if 'configs.sign_models' in sys.modules:
        del sys.modules['configs.sign_models']
    if 'configs.settings' in sys.modules:
        del sys.modules['configs.settings']
    
    # Настраиваем переменные окружения ДО импорта
    os.environ['USE_CUDA'] = '0'
    os.environ['CPU_INFERENCE_BACKEND'] = backend
    
    try:
        from configs.settings import get_app_settings
        from configs import sign_models
        
        settings = get_app_settings()
        settings.use_cuda = False
        settings.cpu_inference_backend = backend
        
        print(f"Настройки: use_cuda={settings.use_cuda}, cpu_inference_backend='{settings.cpu_inference_backend}'")
        
        # Перезагружаем модели с новыми настройками
        sign_models.reload_all_models_if_device_changed()
        print(f"reload_all_models_if_device_changed() вызван успешно")
        
        # Создаём синтетический кадр
        dummy = np.random.randint(0, 255, (32, 32, 3), dtype=np.uint8)
        
        # Пытаемся выполнить инференс
        print(f"\nВыполняю инференс на модели rube_modal (classify)...")
        result = sign_models.rube_modal(dummy, verbose=False)
        
        # Проверяем реальный backend
        actual_backend = sign_models.rube_modal._backend
        print(f"  ✅ Инференс успешен!")
        print(f"  📊 Запрошенный backend: '{backend}'")
        print(f"  📊 РЕАЛЬНЫЙ backend после _load(): '{actual_backend}'")
        print(f"  📊 Результат: top1={result[0].probs.top1}, top5={result[0].probs.top5}")
        
        if actual_backend != backend:
            print(f"  ⚠️  ВНИМАНИЕ: произошёл ТИХИЙ ОТКАТ с '{backend}' на '{actual_backend}'!")
        else:
            print(f"  ✅ Backend соответствует запрошенному")
            
    except Exception as e:
        import traceback
        print(f"  ❌ ОШИБКА при работе с backend '{backend}':")
        print(f"     {e}")
        print("\nПолный traceback:")
        traceback.print_exc()

print(f"\n{'='*80}")
print("ДИАГНОСТИКА ЗАВЕРШЕНА")
print(f"{'='*80}\n")
