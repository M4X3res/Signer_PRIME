"""
Регресс-тесты для багов A/B: крах DetectorThread из-за .bbox
и потеря результата OCR при возврате в TrackedSign.
"""
import numpy as np


def test_detected_sign_has_no_bbox_attribute_by_design():
    """Документирует факт: DetectedSign НЕ имеет .bbox, только x/y/w/h.
    Если кто-то добавит property .bbox — тест не должен падать (ОК),
    но если кто-то уберёт x/y/w/h — тест должен упасть."""
    from core.frame import DetectedSign
    det = DetectedSign(
        x=10, y=20, w=30, h=40,
        name_sign="krug", number_sign="3.24",
        frame_number=1, absolute_frame_number=1,
        latitude=0.0, longitude=0.0,
    )
    assert (det.x, det.y, det.w, det.h) == (10, 20, 30, 40)


def test_detected_sign_bbox_property_works():
    """БАГ A: Проверяем что добавленное property bbox работает корректно."""
    from core.frame import DetectedSign
    det = DetectedSign(
        x=10, y=20, w=30, h=40,
        name_sign="krug", number_sign="3.24",
        frame_number=1, absolute_frame_number=1,
        latitude=0.0, longitude=0.0,
    )
    # Теперь property должно работать
    assert det.bbox == (10, 20, 30, 40)


def test_submit_ocr_task_does_not_raise_attributeerror():
    """БАГ A: _submit_ocr_task не должен падать с AttributeError на bbox."""
    from processing.detector_thread import DetectorThread
    from core.sign import TrackedSign
    from core.frame import DetectedSign

    thread = DetectorThread.__new__(DetectorThread)  # без QThread.__init__
    thread._ocr_worker = None  # ранний return — метод не должен упасть
    thread._pending_ocr = {}
    thread._ocr_sign_counter = 0
    thread._using_ocr_pool = True

    tracked = TrackedSign()
    det = DetectedSign(
        x=5, y=5, w=10, h=10, name_sign="krug", number_sign="3.24",
        frame_number=1, absolute_frame_number=1, latitude=0.0, longitude=0.0,
    )
    tracked.append(det)

    frame = np.zeros((100, 100, 3), dtype=np.uint8)
    # Не должно бросать AttributeError, даже с ocr_worker=None (ранний return)
    thread._submit_ocr_task(tracked, frame)


def test_ocr_result_is_written_back_to_tracked_sign():
    """БАГ B: результат OCR должен попадать в TrackedSign.text_results."""
    from processing.detector_thread import DetectorThread
    from core.sign import TrackedSign

    thread = DetectorThread.__new__(DetectorThread)
    thread._pending_ocr = {}

    tracked = TrackedSign()
    thread._pending_ocr[0] = tracked

    class FakeResult:
        sign_id = 0
        text = "60"
        error = None

    thread._on_ocr_result_pool(FakeResult())

    assert "60" in tracked.text_results
    assert 0 not in thread._pending_ocr  # должен быть удалён из pending после обработки


if __name__ == "__main__":
    test_detected_sign_has_no_bbox_attribute_by_design()
    print("✓ test_detected_sign_has_no_bbox_attribute_by_design")
    
    test_detected_sign_bbox_property_works()
    print("✓ test_detected_sign_bbox_property_works")
    
    test_submit_ocr_task_does_not_raise_attributeerror()
    print("✓ test_submit_ocr_task_does_not_raise_attributeerror")
    
    test_ocr_result_is_written_back_to_tracked_sign()
    print("✓ test_ocr_result_is_written_back_to_tracked_sign")
    
    print("\n✅ Все тесты пройдены!")
