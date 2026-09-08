"""Регресс-тест для бага E: знаки, активные на момент конца видео."""
from core.frame import DetectedSign
from core.sign_handler import SignHandler


def test_finalize_remaining_saves_still_active_signs():
    """БАГ E: finalize_remaining должен финализировать знаки, всё ещё активные в конце видео."""
    handler = SignHandler()
    
    # Имитируем 5 наблюдений одного знака (>= MIN_OBSERVATIONS=4)
    for i in range(5):
        det = DetectedSign(
            x=100 + i, y=100, w=50, h=50, 
            name_sign="krug", number_sign="3.24",
            frame_number=1 + i, absolute_frame_number=1 + i,
            latitude=100000.0, longitude=200000.0,  # EPSG:32635 координаты
        )
        handler.check_the_data_to_add([det], None)
    
    # Знак всё ещё "активен", видео не закончилось
    assert len(handler.result_signs) == 0
    assert len(handler.signs) == 1
    
    # Вызываем финализацию
    handler.finalize_remaining()
    
    # Теперь знак должен быть в result_signs
    assert len(handler.result_signs) == 1
    assert len(handler.signs) == 0
    
    # Проверяем что знак имеет корректные данные
    finalized = handler.result_signs[0]
    assert finalized.best_cnn == "3.24"
    assert finalized.observation_count == 5


def test_finalize_remaining_ignores_insufficient_observations():
    """finalize_remaining не должен финализировать знаки с недостаточным количеством наблюдений."""
    handler = SignHandler()
    
    # Имитируем только 3 наблюдения (< MIN_OBSERVATIONS=4)
    for i in range(3):
        det = DetectedSign(
            x=100 + i, y=100, w=50, h=50, 
            name_sign="krug", number_sign="3.24",
            frame_number=1 + i, absolute_frame_number=1 + i,
            latitude=100000.0, longitude=200000.0,
        )
        handler.check_the_data_to_add([det], None)
    
    # Вызываем финализацию
    handler.finalize_remaining()
    
    # Знак НЕ должен быть финализирован (недостаточно наблюдений)
    assert len(handler.result_signs) == 0
    assert len(handler.signs) == 1


def test_finalize_remaining_handles_empty_signs():
    """finalize_remaining должен корректно работать при отсутствии активных знаков."""
    handler = SignHandler()
    
    # Вызываем на пустом handler
    handler.finalize_remaining()
    
    # Не должно быть ошибок
    assert len(handler.result_signs) == 0
    assert len(handler.signs) == 0


if __name__ == "__main__":
    test_finalize_remaining_saves_still_active_signs()
    print("✓ test_finalize_remaining_saves_still_active_signs")
    
    test_finalize_remaining_ignores_insufficient_observations()
    print("✓ test_finalize_remaining_ignores_insufficient_observations")
    
    test_finalize_remaining_handles_empty_signs()
    print("✓ test_finalize_remaining_handles_empty_signs")
    
    print("\n✅ Все тесты пройдены!")
