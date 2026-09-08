"""
tests/test_preview_utils.py
Тесты для processing/preview_utils.py — единой точки конвертации кадра в QPixmap.

Эти тесты обеспечивают, что:
1. Сериализация/десериализация кадров не искажает данные
2. QPixmap создаётся корректно и имеет ожидаемый размер
3. BGR → RGB конвертация работает правильно
"""
import numpy as np
import pytest

from processing.preview_utils import build_frame_dict, build_pixmap_from_frame_dict


def test_build_frame_dict_roundtrip():
    """Проверяет, что сериализация/десериализация не искажает данные."""
    # Создаём случайное изображение
    img = np.random.randint(0, 255, (100, 200, 3), dtype=np.uint8)
    
    # Сериализуем
    frame_dict = build_frame_dict(img)

    # Проверяем формат словаря
    assert isinstance(frame_dict, dict)
    assert "image_bytes" in frame_dict
    assert "shape" in frame_dict
    assert "dtype" in frame_dict
    
    assert frame_dict["shape"] == (100, 200, 3)
    assert frame_dict["dtype"] == "uint8"
    assert isinstance(frame_dict["image_bytes"], bytes)

    # Десериализуем и проверяем идентичность
    restored = np.frombuffer(frame_dict["image_bytes"], dtype=np.dtype(frame_dict["dtype"]))
    restored = restored.reshape(frame_dict["shape"])
    assert np.array_equal(img, restored), "Десериализованное изображение не совпадает с оригиналом"


def test_build_frame_dict_contiguous():
    """Проверяет, что build_frame_dict работает с non-contiguous массивами."""
    # Создаём non-contiguous массив (transpose)
    img = np.random.randint(0, 255, (100, 200, 3), dtype=np.uint8)
    img_transposed = img.transpose(1, 0, 2)  # не C-contiguous
    
    # Должно работать без ошибок
    frame_dict = build_frame_dict(img_transposed)
    
    # Проверяем, что данные сохранены корректно
    restored = np.frombuffer(frame_dict["image_bytes"], dtype=np.dtype(frame_dict["dtype"]))
    restored = restored.reshape(frame_dict["shape"])
    assert np.array_equal(img_transposed, restored)


def test_build_pixmap_from_frame_dict_requires_qapp(qapp):
    """
    Проверяет, что build_pixmap_from_frame_dict создаёт корректный QPixmap.
    
    Args:
        qapp: фикстура QApplication (offscreen режим)
    """
    # Создаём зелёное изображение в BGR формате
    img = np.zeros((100, 200, 3), dtype=np.uint8)
    img[:, :, 1] = 255  # зелёный канал в BGR
    
    # Сериализуем
    frame_dict = build_frame_dict(img)

    # Создаём QPixmap (требует GUI поток)
    pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=(960, 540))

    # Проверяем результат
    assert not pixmap.isNull(), "QPixmap не должен быть null"
    assert pixmap.width() <= 960, f"Ширина {pixmap.width()} превышает максимум 960"
    assert pixmap.height() <= 540, f"Высота {pixmap.height()} превышает максимум 540"
    
    # Проверяем аспект (100x200 → должен быть в 2 раза шире чем выше)
    aspect_ratio = pixmap.width() / pixmap.height()
    expected_aspect = 200 / 100  # 2.0
    assert abs(aspect_ratio - expected_aspect) < 0.01, f"Aspect ratio нарушен: {aspect_ratio} != {expected_aspect}"


def test_build_pixmap_from_frame_dict_different_sizes(qapp):
    """Проверяет масштабирование для разных размеров изображений."""
    test_cases = [
        ((100, 200, 3), (960, 540)),    # горизонтальное
        ((200, 100, 3), (960, 540)),    # вертикальное
        ((1920, 1080, 3), (960, 540)),  # Full HD → preview
        ((480, 640, 3), (960, 540)),    # маленькое
    ]
    
    for img_shape, target_size in test_cases:
        img = np.random.randint(0, 255, img_shape, dtype=np.uint8)
        frame_dict = build_frame_dict(img)
        pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=target_size)
        
        assert not pixmap.isNull()
        assert pixmap.width() <= target_size[0]
        assert pixmap.height() <= target_size[1]
        
        # Проверяем, что хотя бы одна из сторон равна максимальной
        # (при сохранении aspect ratio)
        assert (pixmap.width() == target_size[0] or 
                pixmap.height() == target_size[1] or
                img_shape[1] < target_size[0] and img_shape[0] < target_size[1]), \
            f"Масштабирование некорректно для {img_shape}"


def test_build_pixmap_from_frame_dict_invalid_input(qapp):
    """Проверяет обработку некорректных входных данных."""
    # Не dict
    with pytest.raises(ValueError):
        build_pixmap_from_frame_dict("not a dict")
    
    # dict без image_bytes
    with pytest.raises(ValueError):
        build_pixmap_from_frame_dict({"shape": (100, 200, 3), "dtype": "uint8"})
    
    # Некорректный формат
    with pytest.raises(Exception):  # ValueError или другое исключение
        build_pixmap_from_frame_dict({
            "image_bytes": b"invalid",
            "shape": (100, 200, 3),
            "dtype": "uint8"
        })


def test_bgr_to_rgb_conversion(qapp):
    """
    Проверяет, что BGR → RGB конвертация происходит ровно один раз.
    
    Создаём изображение с чётко выраженным цветом в BGR формате и проверяем,
    что QPixmap содержит корректные RGB данные.
    """
    # Создаём красное изображение в BGR (красный = канал 2)
    img_bgr = np.zeros((50, 50, 3), dtype=np.uint8)
    img_bgr[:, :, 2] = 255  # BGR: B=0, G=0, R=255
    
    frame_dict = build_frame_dict(img_bgr)
    pixmap = build_pixmap_from_frame_dict(frame_dict, target_size=(50, 50))
    
    # Конвертируем QPixmap → QImage для проверки пикселей
    qimg = pixmap.toImage()
    
    # Проверяем несколько пикселей (должны быть красными в RGB)
    from PyQt6.QtGui import QColor
    center_pixel = qimg.pixelColor(25, 25)
    
    # В RGB красный = (255, 0, 0)
    assert center_pixel.red() > 200, f"Красный канал некорректен: {center_pixel.red()}"
    assert center_pixel.green() < 50, f"Зелёный канал должен быть ~0: {center_pixel.green()}"
    assert center_pixel.blue() < 50, f"Синий канал должен быть ~0: {center_pixel.blue()}"
