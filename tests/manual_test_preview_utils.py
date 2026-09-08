"""
tests/manual_test_preview_utils.py
Ручное тестирование preview_utils без pytest.

Запуск: python tests/manual_test_preview_utils.py
"""
import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PyQt6.QtWidgets import QApplication

from processing.preview_utils import build_frame_dict, build_pixmap_from_frame_dict


def test_build_frame_dict_roundtrip():
    """Проверяет, что сериализация/десериализация не искажает данные."""
    print("TEST: build_frame_dict_roundtrip...")
    
    img = np.random.randint(0, 255, (100, 200, 3), dtype=np.uint8)
    frame_dict = build_frame_dict(img)

    assert frame_dict["shape"] == (100, 200, 3)
    assert frame_dict["dtype"] == "uint8"

    restored = np.frombuffer(frame_dict["image_bytes"], dtype=np.dtype(frame_dict["dtype"]))
    restored = restored.reshape(frame_dict["shape"])
    assert np.array_equal(img, restored), "Десериализация не совпадает с оригиналом"
    
    print("  ✓ Passed")


def test_build_pixmap_from_frame_dict():
    """Проверяет, что QPixmap создаётся корректно."""
    print("TEST: build_pixmap_from_frame_dict...")
    
    # Зелёное изображение в BGR
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:, :, 1] = 255
    
    frame_dict = build_frame_dict(img)
    pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=(960, 540))

    assert not pixmap.isNull(), "QPixmap не должен быть null"
    assert pixmap.width() <= 960
    assert pixmap.height() <= 540
    
    print(f"  ✓ Passed - QPixmap size: {pixmap.width()}x{pixmap.height()}")


def test_different_sizes():
    """Проверяет масштабирование для разных размеров."""
    print("TEST: different_sizes...")
    
    test_cases = [
        ((100, 200, 3), "горизонтальное"),
        ((200, 100, 3), "вертикальное"),
        ((1920, 1080, 3), "Full HD"),
        ((480, 640, 3), "маленькое"),
    ]
    
    for img_shape, desc in test_cases:
        img = np.random.randint(0, 255, img_shape, dtype=np.uint8)
        frame_dict = build_frame_dict(img)
        pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=(960, 540))
        
        assert not pixmap.isNull()
        assert pixmap.width() <= 960
        assert pixmap.height() <= 540
        
        print(f"  ✓ {desc}: {img_shape[:2]} → {pixmap.width()}x{pixmap.height()}")


def test_invalid_input():
    """Проверяет обработку некорректных данных."""
    print("TEST: invalid_input...")
    
    try:
        build_pixmap_from_frame_dict("not a dict")
        assert False, "Должно было выбросить ValueError"
    except ValueError:
        print("  ✓ ValueError для 'not a dict'")
    
    try:
        build_pixmap_from_frame_dict({"shape": (100, 200, 3), "dtype": "uint8"})
        assert False, "Должно было выбросить ValueError"
    except ValueError:
        print("  ✓ ValueError для dict без image_bytes")


def test_bgr_to_rgb_conversion():
    """Проверяет BGR → RGB конвертацию."""
    print("TEST: bgr_to_rgb_conversion...")
    
    # Красное изображение в BGR (красный = канал 2)
    img_bgr = np.zeros((50, 50, 3), dtype=np.uint8)
    img_bgr[:, :, 2] = 255
    
    frame_dict = build_frame_dict(img_bgr)
    pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=(50, 50))
    
    qimg = pixmap.toImage()
    center_pixel = qimg.pixelColor(25, 25)
    
    # В RGB красный = (255, 0, 0)
    assert center_pixel.red() > 200, f"Красный канал некорректен: {center_pixel.red()}"
    assert center_pixel.green() < 50, f"Зелёный канал должен быть ~0: {center_pixel.green()}"
    assert center_pixel.blue() < 50, f"Синий канал должен быть ~0: {center_pixel.blue()}"
    
    print(f"  ✓ RGB конвертация корректна: R={center_pixel.red()}, G={center_pixel.green()}, B={center_pixel.blue()}")


if __name__ == "__main__":
    print("=" * 60)
    print("Ручное тестирование preview_utils")
    print("=" * 60)
    
    # Создаём QApplication в offscreen режиме
    app = QApplication(["-platform", "offscreen"])
    
    try:
        test_build_frame_dict_roundtrip()
        test_build_pixmap_from_frame_dict()
        test_different_sizes()
        test_invalid_input()
        test_bgr_to_rgb_conversion()
        
        print("\n" + "=" * 60)
        print("✓ ВСЕ ТЕСТЫ ПРОЙДЕНЫ")
        print("=" * 60)
        
    except Exception as e:
        print("\n" + "=" * 60)
        print(f"✗ ТЕСТ УПАЛ: {e}")
        print("=" * 60)
        import traceback
        traceback.print_exc()
        sys.exit(1)
