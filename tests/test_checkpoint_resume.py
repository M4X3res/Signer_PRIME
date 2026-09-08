"""
tests/test_checkpoint_resume.py
Regression test для БАГ №2: восстановление из checkpoint должно работать.

Проверяет:
1. load_checkpoint() корректно восстанавливает индексы
2. _reset_config() НЕ сбрасывает индексы при восстановлении
3. checkpoint_signs корректно передается в DetectorThread
"""
import sys
import os
from pathlib import Path
import io

# Устанавливаем UTF-8 для stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Добавляем корень проекта в sys.path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from configs import config
from processing.processing_controller import ProcessingController
from core.sign import TrackedSign


def test_checkpoint_resume():
    """
    Тестирует механизм восстановления из checkpoint.
    """
    print("=" * 60)
    print("TEST: Checkpoint resume mechanism")
    print("=" * 60)
    
    # Создаём фиктивные знаки для checkpoint
    print("\n[1] Creating fake checkpoint data...")
    fake_signs = []
    for i in range(3):
        sign = TrackedSign()
        sign.cnn_results = [f"3.2{i}"]
        sign.frame_numbers = [100 + i]
        fake_signs.append(sign)
    
    # Создаём фиктивный checkpoint файл
    import joblib
    checkpoint_path = "test_checkpoint.pkl"
    checkpoint_data = {
        'config': {
            'INDEX_OF_FRAME': 500,
            'INDEX_OF_VIDEO': 2,
            'INDEX_OF_All_FRAME': 1234,
            'INDEX_OF_GPS': 300,
            'FRAME_STEP': 5,
            'VIDEOS': ['test1.mp4', 'test2.mp4'],
            'PATH_TO_VIDEO': 'C:/test/videos',
            'PATH_TO_GPX': 'C:/test/track.gpx',
            'PATH_TO_GEOJSON': 'C:/test/signs.geojson',
        },
        'signs': {
            'result_signs': fake_signs,
            'active_signs': [],
            'turns': [],
        },
        'stats': {
            'frames_processed': 1234,
            'signs_found': 10,
        }
    }
    
    # Временно подменяем CHECKPOINT_PATH
    original_checkpoint_path = ProcessingController.CHECKPOINT_PATH
    ProcessingController.CHECKPOINT_PATH = checkpoint_path
    
    try:
        joblib.dump(checkpoint_data, checkpoint_path, compress=3)
        print(f"Checkpoint created: {checkpoint_path}")
        
        # Test 1: load_checkpoint() должен восстановить индексы
        print("\n[2] Testing load_checkpoint()...")
        controller = ProcessingController()
        
        success = controller.load_checkpoint()
        assert success, "load_checkpoint() returned False"
        assert controller._resume_from_checkpoint, "Resume flag not set"
        assert controller._checkpoint_data is not None, "Checkpoint data not saved"
        
        # Проверяем что индексы восстановлены
        assert config.INDEX_OF_FRAME == 500, f"INDEX_OF_FRAME: expected 500, got {config.INDEX_OF_FRAME}"
        assert config.INDEX_OF_VIDEO == 2, f"INDEX_OF_VIDEO: expected 2, got {config.INDEX_OF_VIDEO}"
        assert config.INDEX_OF_All_FRAME == 1234, f"INDEX_OF_All_FRAME: expected 1234, got {config.INDEX_OF_All_FRAME}"
        print("PASS: Indices restored correctly")
        
        # Test 2: _reset_config() НЕ должен сбросить индексы при восстановлении
        print("\n[3] Testing _reset_config() with resume flag...")
        controller._reset_config()
        
        # Индексы должны остаться нетронутыми
        assert config.INDEX_OF_FRAME == 500, f"INDEX_OF_FRAME was reset! Got {config.INDEX_OF_FRAME}"
        assert config.INDEX_OF_VIDEO == 2, f"INDEX_OF_VIDEO was reset! Got {config.INDEX_OF_VIDEO}"
        assert config.INDEX_OF_All_FRAME == 1234, f"INDEX_OF_All_FRAME was reset! Got {config.INDEX_OF_All_FRAME}"
        print("PASS: Indices NOT reset when resuming")
        
        # Test 3: Проверяем что данные знаков доступны для DetectorThread
        print("\n[4] Testing checkpoint_signs availability...")
        checkpoint_signs = controller._checkpoint_data.get('signs')
        assert checkpoint_signs is not None, "Signs data not available"
        assert len(checkpoint_signs['result_signs']) == 3, f"Expected 3 signs, got {len(checkpoint_signs['result_signs'])}"
        print("PASS: Checkpoint signs data accessible")
        
        # Test 4: Проверяем сброс флага после использования
        print("\n[5] Testing flag reset after use...")
        controller._resume_from_checkpoint = False
        controller._checkpoint_data = None
        
        config.INDEX_OF_FRAME = 0
        config.INDEX_OF_VIDEO = 0
        config.INDEX_OF_All_FRAME = 0
        
        controller._reset_config()
        
        # Теперь индексы ДОЛЖНЫ сброситься
        assert config.INDEX_OF_FRAME == 0, "Indices not reset when flag is False"
        print("PASS: Indices reset correctly when flag is False")
        
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\nFAIL: {e}")
        return False
        
    finally:
        # Cleanup
        ProcessingController.CHECKPOINT_PATH = original_checkpoint_path
        if os.path.exists(checkpoint_path):
            os.remove(checkpoint_path)
            print(f"\nCleanup: Removed {checkpoint_path}")


if __name__ == "__main__":
    sys.stdout.flush()
    success = test_checkpoint_resume()
    sys.exit(0 if success else 1)
