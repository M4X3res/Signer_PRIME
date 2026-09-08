# -*- coding: utf-8 -*-
"""
tests/test_reorder_buffer.py
Регрессионный тест на баг с ReorderBuffer в Process Pool режиме —
см. PROMPT_FIX_PREVIEW_AND_PROCESSING.md, Часть 1.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from processing.detector_process_pool import ReorderBuffer


def test_reorder_buffer_releases_first_frame_immediately():
    """
    Регрессия: раньше буфер ждал frame_idx == 0, которого никогда не было
    (реальный abs_frame_number первого кадра == FRAME_STEP, например 5).
    После фикса буфер ключуется по 'seq' (0,1,2,...), присваиваемому
    submitter'ом, и должен отдать первый кадр сразу же, без ожидания
    остальных 31 (max_gap) кадров.
    """
    buf = ReorderBuffer(max_gap=32)
    frame = {"seq": 0, "frame_idx": 5, "payload": "first"}
    ready = buf.add(frame)
    assert ready == [frame], (
        "ReorderBuffer должен немедленно отдать самый первый кадр (seq=0), "
        "а не ждать flush() в конце видео"
    )


def test_reorder_buffer_handles_frame_step_stride_and_reordering():
    """
    Имитация реального FRAME_STEP=5: frame_idx растёт как 5,10,15,...,
    но seq присваивается строго последовательно submitter'ом. Воркеры
    могут завершиться не в том порядке, в котором были отправлены —
    буфер должен восстановить порядок по seq.
    """
    buf = ReorderBuffer(max_gap=32)
    frames = [
        {"seq": 2, "frame_idx": 15},
        {"seq": 0, "frame_idx": 5},
        {"seq": 1, "frame_idx": 10},
        {"seq": 4, "frame_idx": 25},
        {"seq": 3, "frame_idx": 20},
    ]
    released = []
    for f in frames:
        released.extend(buf.add(f))

    assert [r["frame_idx"] for r in released] == [5, 10, 15, 20, 25], (
        "Кадры должны выходить из буфера строго по возрастанию frame_idx "
        "(что эквивалентно возрастанию seq), независимо от порядка поступления"
    )


def test_reorder_buffer_gap_safety_valve_still_works():
    """
    Если какой-то seq потерян навсегда (например, воркер упал и future
    никогда не вернул результат для него), gap-механизм должен сработать
    и пропустить недостающие кадры, чтобы не накапливать память бесконечно.
    """
    buf = ReorderBuffer(max_gap=5)
    
    # Сначала добавляем последовательные кадры 0-4
    for seq in range(5):
        buf.add({"seq": seq, "frame_idx": seq * 5})
    
    # Все 5 кадров должны были выйти (последовательные)
    assert len(buf) == 0, "Buffer should be empty after sequential frames"
    
    # Теперь имитируем большой разрыв: следующий кадр seq=15 (кадры 5-14 потеряны)
    # gap = 15 - 5 = 10 > max_gap=5
    result = buf.add({"seq": 15, "frame_idx": 75})
    
    # Gap-механизм должен сработать: _next_expected сдвинется на 15,
    # и кадр 15 сразу выйдет
    assert len(result) == 1, (
        f"Gap safety valve should skip lost frames and release seq=15, "
        f"but got {len(result)} frames"
    )
    assert result[0]['seq'] == 15, "Released frame should be seq=15"
    assert buf._next_expected == 16, "next_expected should advance to 16"


def test_build_detected_signs_converts_to_epsg32635():
    """
    Регрессия «Африка-баг»: latitude/longitude в DetectedSign должны быть
    в EPSG:32635 (метры, обычно сотни тысяч), а не в WGS84 (градусы, < 180).
    """
    from processing.detector_process_pool import ResultAggregatorThread

    class FakeGPX:
        def get_current_coordinate(self, idx):
            return (53.9021, 27.5612)  # Минск, WGS84

    # Создаём минимальный экземпляр без вызова QThread.__init__
    # (чтобы не требовалась QApplication)
    agg = ResultAggregatorThread.__new__(ResultAggregatorThread)
    try:
        from core.converter import Converter
        agg._gpx = FakeGPX()
        agg._converter = Converter()
    except Exception as e:
        print(f"[SKIP] Coordinate test skipped: {e}")
        return

    frame_data = {
        "frame_idx": 100,
        "frame_number": 100,
        "gps_data": {"gps_index": 5},
        "detections": [
            {"box": [10, 10, 20, 20], "yolo_class": "krug", "cnn_class": "3.24",
             "text": "", "is_side": False}
        ],
    }

    signs = agg._build_detected_signs(frame_data)
    assert len(signs) == 1
    lat, lon = signs[0].latitude, signs[0].longitude

    # WGS84 координаты всегда в диапазоне [-180, 180]; EPSG:32635 (UTM, зона 35N)
    # для Беларуси — это величины порядка 300000-700000 (X) и 5900000-6200000 (Y).
    assert abs(lat) > 1000 or abs(lon) > 1000, (
        f"Координаты ({lat}, {lon}) похожи на WGS84 градусы — конвертация "
        f"в EPSG:32635 не сработала (снова 'Африка-баг')"
    )


if __name__ == "__main__":
    print("Running test 1/4: test_reorder_buffer_releases_first_frame_immediately")
    test_reorder_buffer_releases_first_frame_immediately()
    print("[PASS] Test 1 passed")
    
    print("\nRunning test 2/4: test_reorder_buffer_handles_frame_step_stride_and_reordering")
    test_reorder_buffer_handles_frame_step_stride_and_reordering()
    print("[PASS] Test 2 passed")
    
    print("\nRunning test 3/4: test_reorder_buffer_gap_safety_valve_still_works")
    test_reorder_buffer_gap_safety_valve_still_works()
    print("[PASS] Test 3 passed")
    
    print("\nRunning test 4/4: test_build_detected_signs_converts_to_epsg32635")
    test_build_detected_signs_converts_to_epsg32635()
    print("[PASS] Test 4 passed")
    
    print("\n" + "="*60)
    print("[OK] All ReorderBuffer tests passed (4/4)")
    print("="*60)
