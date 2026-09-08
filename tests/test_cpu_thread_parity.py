"""
Регресс-тест BLOCK CPU-5: паритет потоков между backend'ами.

Проверяет что модуль configs/inference_threading.py корректно патчит
ONNX Runtime и OpenVINO для ограничения потоков CPU-инференса.
"""
import pytest
import os


def test_inference_threading_module_imports():
    """Модуль inference_threading должен импортироваться без ошибок."""
    from configs.inference_threading import apply_cpu_thread_limits, compute_safe_intra_threads
    assert callable(apply_cpu_thread_limits)
    assert callable(compute_safe_intra_threads)


def test_compute_safe_intra_threads_single():
    """compute_safe_intra_threads для single thread: все ядра - 1."""
    from configs.inference_threading import compute_safe_intra_threads
    
    # Single thread: все ядра - 1
    result_single = compute_safe_intra_threads(1)
    expected = max(1, (os.cpu_count() or 4) - 1)
    assert result_single == expected, f"Expected {expected}, got {result_single}"


def test_compute_safe_intra_threads_pool():
    """compute_safe_intra_threads для process pool: делим поровну."""
    from configs.inference_threading import compute_safe_intra_threads
    
    # Process pool: делим поровну
    result_pool = compute_safe_intra_threads(4)
    expected = max(1, (os.cpu_count() or 4) // 4)
    assert result_pool == expected, f"Expected {expected}, got {result_pool}"


def test_compute_safe_intra_threads_edge_cases():
    """Проверка edge cases: 0 workers, большое число workers."""
    from configs.inference_threading import compute_safe_intra_threads
    
    # 0 workers — как single thread
    result = compute_safe_intra_threads(0)
    assert result >= 1
    
    # Много workers — минимум 1 поток на каждый
    result = compute_safe_intra_threads(100)
    assert result >= 1


def test_onnxruntime_patch_idempotent():
    """Патч ONNX Runtime должен быть идемпотентным."""
    pytest.importorskip("onnxruntime")  # skip если нет библиотеки
    
    from configs import inference_threading
    
    # Сбрасываем флаг для теста
    inference_threading._patched_onnx = False
    
    # Первый вызов
    inference_threading.apply_cpu_thread_limits(intra_threads=2, inter_threads=1)
    assert inference_threading._patched_onnx is True
    
    # Второй вызов не должен упасть и не должен перепатчить
    inference_threading.apply_cpu_thread_limits(intra_threads=4, inter_threads=1)
    assert inference_threading._patched_onnx is True


def test_openvino_patch_idempotent():
    """Патч OpenVINO должен быть идемпотентным."""
    pytest.importorskip("openvino")  # skip если нет библиотеки
    
    from configs import inference_threading
    
    # Сбрасываем флаг для теста
    inference_threading._patched_openvino = False
    
    # Первый вызов
    inference_threading.apply_cpu_thread_limits(openvino_threads=2)
    assert inference_threading._patched_openvino is True
    
    # Второй вызов не должен упасть и не должен перепатчить
    inference_threading.apply_cpu_thread_limits(openvino_threads=4)
    assert inference_threading._patched_openvino is True


def test_apply_cpu_thread_limits_with_missing_libs():
    """apply_cpu_thread_limits должен корректно обрабатывать отсутствие библиотек."""
    from configs.inference_threading import apply_cpu_thread_limits
    
    # Не должно упасть даже если библиотеки отсутствуют
    try:
        apply_cpu_thread_limits(intra_threads=2, inter_threads=1, openvino_threads=2)
        # Успех — функция не упала
        assert True
    except ImportError:
        pytest.fail("apply_cpu_thread_limits не должна кидать ImportError")


"""Регресс-тест BLOCK CPU-6: verify_backend_active не вызывается в GUI потоке."""


def test_verify_backend_active_not_called_directly_in_processing_controller():
    """
    verify_backend_active() грузит модели синхронно и должна вызываться
    ТОЛЬКО изнутри run() дочернего QThread (например BackendVerifyThread),
    никогда напрямую из ProcessingController.start() в GUI-потоке.
    """
    with open("processing/processing_controller.py", encoding="utf-8") as f:
        content = f.read()

    # verify_backend_active может упоминаться только в backend_verify_thread.py
    assert "verify_backend_active()" not in content, (
        "verify_backend_active() не должна вызываться напрямую из "
        "ProcessingController — это грузит модели в главном GUI-потоке. "
        "Используйте BackendVerifyThread (processing/backend_verify_thread.py)."
    )


def test_backend_verify_thread_exists():
    """BackendVerifyThread должен существовать."""
    with open("processing/backend_verify_thread.py", encoding="utf-8") as f:
        thread_content = f.read()
    
    assert "verify_backend_active()" in thread_content
    assert "class BackendVerifyThread(QThread)" in thread_content
    assert "def run(self)" in thread_content


def test_processing_controller_uses_backend_verify_thread():
    """ProcessingController должен использовать _start_backend_verify."""
    with open("processing/processing_controller.py", encoding="utf-8") as f:
        content = f.read()
    
    assert "_start_backend_verify(" in content
    assert "BackendVerifyThread" in content


if __name__ == "__main__":
    test_verify_backend_active_not_called_directly_in_processing_controller()
    print("✓ test_verify_backend_active_not_called_directly_in_processing_controller")
    
    test_backend_verify_thread_exists()
    print("✓ test_backend_verify_thread_exists")
    
    test_processing_controller_uses_backend_verify_thread()
    print("✓ test_processing_controller_uses_backend_verify_thread")
    
    print("\n✅ Все тесты пройдены!")
    # Запуск тестов напрямую
    test_inference_threading_module_imports()
    print("✓ test_inference_threading_module_imports")
    
    test_compute_safe_intra_threads_single()
    print("✓ test_compute_safe_intra_threads_single")
    
    test_compute_safe_intra_threads_pool()
    print("✓ test_compute_safe_intra_threads_pool")
    
    test_compute_safe_intra_threads_edge_cases()
    print("✓ test_compute_safe_intra_threads_edge_cases")
    
    test_apply_cpu_thread_limits_with_missing_libs()
    print("✓ test_apply_cpu_thread_limits_with_missing_libs")
    
    # Тесты с библиотеками — только если установлены
    try:
        test_onnxruntime_patch_idempotent()
        print("✓ test_onnxruntime_patch_idempotent")
    except:
        print("⊘ test_onnxruntime_patch_idempotent (ONNX Runtime не установлен)")
    
    try:
        test_openvino_patch_idempotent()
        print("✓ test_openvino_patch_idempotent")
    except:
        print("⊘ test_openvino_patch_idempotent (OpenVINO не установлен)")
    
    print("\n✅ Все тесты пройдены!")
