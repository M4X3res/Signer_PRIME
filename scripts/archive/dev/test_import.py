"""Тест импорта detector_process_pool"""
import sys
print("Python version:", sys.version)

try:
    print("1. Импорт configs...")
    from configs import config
    print(f"   PROCESSING_MODE = {config.PROCESSING_MODE}")
    
    print("2. Импорт PyQt6...")
    from PyQt6.QtCore import QObject
    
    print("3. Импорт video_reader...")
    from processing.video_reader import RawFrame, _STOP
    
    print("4. Импорт detector_process_pool...")
    from processing.detector_process_pool import DetectorProcessPool
    
    print("5. Проверка классов...")
    print(f"   DetectorProcessPool: {DetectorProcessPool}")
    
    print("\n✅ Все импорты успешны!")
    
except Exception as e:
    print(f"\n❌ ОШИБКА: {e}")
    import traceback
    traceback.print_exc()
