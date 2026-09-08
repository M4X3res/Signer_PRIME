# -*- coding: utf-8 -*-
"""
tests/test_attach_unmatched_fix.py
Регрессионный тест на баг в SignHandler._attach_unmatched().
См. prompts/PROMPT_FIX_DUPLICATE_SIGNS_AND_GPS_CONFIDENCE.md, Часть 1, Шаг 1.

Проблема: сравнивалось raw pixel distance с adjusted distance (с учётом SAME_TYPE_BONUS),
из-за чего при совпадении типа (основной случай) abs(raw - adjusted) всегда было = 50 > 30,
и механизм fallback-прикрепления не срабатывал никогда.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.sign_handler import SignHandler
from core.frame import DetectedSign


def test_attach_unmatched_same_type():
    """
    Регрессия: при совпадении типа знака, _attach_unmatched должен прикреплять
    детекцию к существующему треку, если пиксельное расстояние близко.
    
    До фикса: сравнение raw_vec с (raw_vec - 50) давало abs() = 50 > 30 → не прикреплялось.
    После фикса: сравнение raw с raw → прикрепляется.
    """
    handler = SignHandler()
    
    # Создаём первую детекцию и добавляем её как новый знак
    det1 = DetectedSign(
        x=100, y=100, w=50, h=50,
        name_sign="krug",
        number_sign="3.24",
        frame_number=1,
        absolute_frame_number=1,
        latitude=0.0,
        longitude=0.0,
        text_on_sign="",
        is_side=False
    )
    handler._add_sign(det1)
    
    # Следующий кадр: тот же знак, немного сдвинулся по Y (типичное движение в кадре)
    det2 = DetectedSign(
        x=100, y=110, w=50, h=50,  # сдвиг по Y на 10 пикселей
        name_sign="krug",            # тот же тип
        number_sign="3.24",
        frame_number=2,
        absolute_frame_number=2,
        latitude=0.0,
        longitude=0.0,
        text_on_sign="",
        is_side=False
    )
    
    # Имитируем ситуацию, когда _match_evidences не сработал (например, gap > 7 кадров),
    # но _attach_unmatched должен подхватить
    evidences = handler._calc_evidence_matrix([det2])
    matched = []  # не прикреплён через основной match
    
    remaining = handler._attach_unmatched([det2], matched, evidences)
    
    # После фикса: det2 должен быть прикреплён к существующему треку
    assert len(handler.signs) == 1, f"Expected 1 tracked sign, got {len(handler.signs)}"
    assert len(handler.signs[0].frame_numbers) == 2, (
        f"Expected 2 observations in track, got {len(handler.signs[0].frame_numbers)}"
    )
    assert len(remaining) == 0, (
        f"det2 should be attached, not remaining. Remaining: {len(remaining)}"
    )
    
    return True


def test_attach_unmatched_different_type():
    """
    Проверка, что при несовпадении типа знак не прикрепляется (как и ожидалось).
    """
    handler = SignHandler()
    
    det1 = DetectedSign(
        x=100, y=100, w=50, h=50,
        name_sign="krug",
        number_sign="3.24",
        frame_number=1,
        absolute_frame_number=1,
        latitude=0.0,
        longitude=0.0,
        text_on_sign="",
        is_side=False
    )
    handler._add_sign(det1)
    
    # Другой тип знака в том же месте
    det2 = DetectedSign(
        x=100, y=110, w=50, h=50,
        name_sign="treugolnik",  # другой тип
        number_sign="1.2",
        frame_number=2,
        absolute_frame_number=2,
        latitude=0.0,
        longitude=0.0,
        text_on_sign="",
        is_side=False
    )
    
    evidences = handler._calc_evidence_matrix([det2])
    matched = []
    
    remaining = handler._attach_unmatched([det2], matched, evidences)
    
    # Не должно прикрепиться (разные типы)
    assert len(handler.signs) == 1, "Should still have 1 sign"
    assert len(handler.signs[0].frame_numbers) == 1, "Original sign should have 1 observation"
    assert len(remaining) == 1, "det2 should remain unmatched"
    
    return True


if __name__ == "__main__":
    print("Running test 1/2: test_attach_unmatched_same_type")
    result1 = test_attach_unmatched_same_type()
    print(f"[{'PASS' if result1 else 'FAIL'}] Test 1")
    
    print("\nRunning test 2/2: test_attach_unmatched_different_type")
    result2 = test_attach_unmatched_different_type()
    print(f"[{'PASS' if result2 else 'FAIL'}] Test 2")
    
    if result1 and result2:
        print("\n" + "="*60)
        print("[OK] All _attach_unmatched tests passed (2/2)")
        print("="*60)
    else:
        print("\n[FAIL] Some tests failed")
        sys.exit(1)
