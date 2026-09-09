"""
configs/hardware_recommend.py
Определение рекомендуемого backend инференса на основе доступного железа.
"""
from __future__ import annotations
import logging
import platform

logger = logging.getLogger(__name__)


def detect_recommended_backend() -> dict:
    """
    Определяет рекомендуемые настройки вычислений на основе доступного железа.

    Returns:
        dict с ключами:
            use_cuda: bool
            cpu_inference_backend: "torch" | "onnx" | "openvino"
            reason: str — человекочитаемое объяснение выбора (для UI/лога)
    """
    # ── Шаг 1: проверяем CUDA ──────────────────────────────────────
    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            return {
                "use_cuda": True,
                "cpu_inference_backend": "torch",  # неважно, CUDA использует torch-путь
                "reason": f"Обнаружена CUDA-видеокарта: {gpu_name}. "
                          f"Используется GPU-ускорение (PyTorch + CUDA).",
            }
    except Exception as e:
        logger.warning(f"[hardware_recommend] Ошибка проверки CUDA: {e}")

    # ── Шаг 2: CUDA недоступна — выбираем между OpenVINO и ONNX ────
    cpu_info = _detect_cpu_vendor()

    if cpu_info == "intel":
        # OpenVINO даёт наибольший выигрыш именно на Intel CPU (родная библиотека Intel,
        # использует AVX/AVX512, MKL-DNN оптимизации специфичные для Intel).
        backend = "openvino"
        reason = (
            "CUDA недоступна. Обнаружен процессор Intel — рекомендуется OpenVINO "
            "(наилучшая производительность на Intel CPU)."
        )
    else:
        # AMD, ARM (Apple Silicon под Rosetta/нативно), неизвестный вендор —
        # ONNX Runtime более универсален и одинаково хорошо работает везде,
        # тогда как OpenVINO оптимизирован именно под Intel и может не дать
        # выигрыша (или быть недоступен) на других архитектурах.
        backend = "onnx"
        reason = (
            "CUDA недоступна. Процессор не Intel (или не удалось определить) — "
            "рекомендуется ONNX Runtime (универсальный CPU-бэкенд)."
        )

    return {
        "use_cuda": False,
        "cpu_inference_backend": backend,
        "reason": reason,
    }


def _detect_cpu_vendor() -> str:
    """
    Пытается определить производителя CPU: "intel", "amd" или "unknown".
    Работает кроссплатформенно с graceful fallback.
    """
    try:
        # platform.processor() на Windows обычно возвращает что-то вроде
        # "Intel64 Family 6 Model 158 Stepping 10, GenuineIntel"
        proc_info = platform.processor().lower()
        if "intel" in proc_info or "genuineintel" in proc_info:
            return "intel"
        if "amd" in proc_info or "authenticamd" in proc_info:
            return "amd"
    except Exception:
        pass

    # Fallback для Windows: WMI/реестр через wmic, если platform.processor() пуст
    # (случается на некоторых сборках Python на Windows).
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "cpu", "get", "manufacturer"],
            capture_output=True, text=True, timeout=3,
        )
        output = result.stdout.lower()
        if "intel" in output:
            return "intel"
        if "amd" in output:
            return "amd"
    except Exception:
        pass

    # Дополнительный fallback через py-cpuinfo, если установлен (не обязательная зависимость —
    # оборачиваем в try/except, чтобы не требовать новый пакет).
    try:
        import cpuinfo  # type: ignore
        brand = cpuinfo.get_cpu_info().get("brand_raw", "").lower()
        if "intel" in brand:
            return "intel"
        if "amd" in brand:
            return "amd"
    except Exception:
        pass

    return "unknown"
