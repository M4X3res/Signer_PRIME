"""Регресс-тесты для багов C/D: OCR-кэш и best_city_name()."""


def test_best_city_name_uses_plain_strings():
    """БАГ D: best_city_name должен работать с обычными строками в text_results,
    а не требовать список кортежей (старый сломанный формат)."""
    from core.sign import TrackedSign

    sign = TrackedSign()
    sign.text_results = ["минск", "минск", "мiнск", "минск"]

    result = sign.best_city_name()
    assert result == "минск"


def test_best_city_name_empty_when_no_observations():
    """best_city_name должен возвращать пустую строку при отсутствии наблюдений."""
    from core.sign import TrackedSign
    sign = TrackedSign()
    assert sign.best_city_name() == ""


def test_detector_has_ocr_cache():
    """БАГ C: Detector должен иметь отдельный OCR-кэш (не совпадающий с CNN-кэшем)."""
    from core.detector import Detector
    detector = Detector()
    assert hasattr(detector, "_ocr_cache")
    assert detector._ocr_cache is not detector._cnn_cache


def test_ocr_cache_stores_and_retrieves():
    """БАГ C: Проверяем что OCR кэш корректно сохраняет и извлекает результаты."""
    from core.detector import Detector
    import numpy as np
    
    detector = Detector()
    
    # Создаём тестовый crop
    crop = np.zeros((50, 100, 3), dtype=np.uint8)
    
    # Вычисляем хэш
    from core.detector import compute_image_hash
    img_hash = compute_image_hash(crop)
    
    # Проверяем что кэш пуст
    assert detector._ocr_cache.get(f"ocr_basic:{img_hash}") is None
    
    # Добавляем значение
    detector._ocr_cache.put(f"ocr_basic:{img_hash}", "60")
    
    # Проверяем что значение сохранилось
    cached = detector._ocr_cache.get(f"ocr_basic:{img_hash}")
    assert cached == "60"
    
    # Проверяем статистику
    stats = detector._ocr_cache.stats()
    assert stats["hits"] == 1
    assert stats["misses"] == 1


if __name__ == "__main__":
    test_best_city_name_uses_plain_strings()
    print("✓ test_best_city_name_uses_plain_strings")
    
    test_best_city_name_empty_when_no_observations()
    print("✓ test_best_city_name_empty_when_no_observations")
    
    test_detector_has_ocr_cache()
    print("✓ test_detector_has_ocr_cache")
    
    test_ocr_cache_stores_and_retrieves()
    print("✓ test_ocr_cache_stores_and_retrieves")
    
    print("\n✅ Все тесты пройдены!")
