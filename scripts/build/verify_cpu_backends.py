"""
Верификация CPU-бэкендов в собранном приложении.

Этот скрипт проверяет, что ONNX Runtime и OpenVINO backend'ы
реально работают в собранной сборке, а не откатываются тихо на PyTorch.

Использование (из scripts/build/prepare_release.bat):
    .venv\Scripts\python.exe scripts\build\verify_cpu_backends.py [--exe-path dist\Signer\Signer.exe]

Выход:
    0 - успех (все бэкенды работают)
    1 - ошибка (хотя бы один бэкенд откатился на torch или упал)
"""
import argparse
import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


def verify_in_dev_mode() -> int:
    """
    Верификация в режиме разработки (без собранного .exe).
    Временно переключает cpu_inference_backend и проверяет реальный backend.
    
    Returns:
        0 если все бэкенды работают, 1 если есть ошибки
    """
    try:
        # Добавляем корень проекта в sys.path
        sys.path.insert(0, str(Path(__file__).parent.parent.parent))
        
        from configs import sign_models
        from configs.settings import AppSettings
        
        # Список бэкендов для проверки
        backends_to_check = ["onnx", "openvino"]
        results = {}
        
        for backend_name in backends_to_check:
            logger.info(f"\n{'='*80}")
            logger.info(f"Проверка backend: {backend_name.upper()}")
            logger.info(f"{'='*80}\n")
            
            # Временно создаём настройки с нужным backend
            temp_settings = AppSettings()
            temp_settings.use_cuda = False
            temp_settings.cpu_inference_backend = backend_name
            
            # Патчим функцию get_app_settings для использования наших настроек
            import configs.settings
            original_get_settings = configs.settings.get_app_settings
            configs.settings.get_app_settings = lambda: temp_settings
            
            try:
                # CRITICAL: Сбрасываем кеш моделей перед проверкой
                sign_models.reload_all_models_if_device_changed()
                
                # Вызываем verify_backend_active
                backend_status = sign_models.verify_backend_active()
                
                logger.info(f"\nРезультаты проверки для {backend_name.upper()}:")
                logger.info("-" * 60)
                
                errors = []
                for model_name, actual_backend in backend_status.items():
                    status_symbol = "✅" if actual_backend == backend_name else "❌"
                    logger.info(f"{status_symbol} {model_name}: {actual_backend}")
                    
                    if actual_backend != backend_name:
                        if actual_backend.startswith("ERROR:"):
                            errors.append(f"{model_name}: {actual_backend}")
                        else:
                            errors.append(
                                f"{model_name}: ожидался {backend_name}, "
                                f"получен {actual_backend} (fallback)"
                            )
                
                results[backend_name] = {
                    "success": len(errors) == 0,
                    "errors": errors
                }
                
            finally:
                # Восстанавливаем оригинальную функцию
                configs.settings.get_app_settings = original_get_settings
        
        # Итоговая статистика
        logger.info(f"\n{'='*80}")
        logger.info("ИТОГОВАЯ СТАТИСТИКА")
        logger.info(f"{'='*80}\n")
        
        all_success = True
        for backend_name, result in results.items():
            if result["success"]:
                logger.info(f"✅ {backend_name.upper()}: все модели загружены корректно")
            else:
                logger.error(f"❌ {backend_name.upper()}: обнаружены ошибки:")
                for error in result["errors"]:
                    logger.error(f"   - {error}")
                all_success = False
        
        if all_success:
            logger.info(f"\n{'='*80}")
            logger.info("✅ ПРОВЕРКА ПРОЙДЕНА: все CPU-бэкенды работают корректно")
            logger.info(f"{'='*80}\n")
            return 0
        else:
            logger.error(f"\n{'='*80}")
            logger.error("❌ ПРОВЕРКА НЕ ПРОЙДЕНА: есть проблемы с CPU-бэкендами")
            logger.error("Возможные причины:")
            logger.error("  1. Не установлены onnxruntime/openvino пакеты")
            logger.error("  2. Не экспортированы .onnx/*.openvino_model файлы")
            logger.error("     (запустите: python scripts/export_models_onnx.py --format all)")
            logger.error("  3. Ошибки при загрузке моделей (см. логи выше)")
            logger.error(f"{'='*80}\n")
            return 1
            
    except Exception as e:
        logger.error(f"❌ Критическая ошибка при верификации: {e}", exc_info=True)
        return 1


def verify_in_built_exe(exe_path: Path) -> int:
    """
    Верификация в собранном .exe (через subprocess).
    
    Args:
        exe_path: Путь к собранному Signer.exe
    
    Returns:
        0 если все бэкенды работают, 1 если есть ошибки
    """
    import subprocess
    import json
    import tempfile
    exe_path = exe_path.resolve()
    if not exe_path.is_file():
        logger.error("Missing executable: %s", exe_path)
        return 1
    try:
        with tempfile.TemporaryDirectory(prefix="signer-verify-") as directory:
            report = Path(directory) / "verification.json"
            result = subprocess.run(
                [str(exe_path), "--verify-backends", "--verification-output", str(report)],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=600, cwd=exe_path.parent,
                env={**os.environ, "YOLO_AUTOINSTALL": "false"},
            )
            if not report.is_file():
                logger.error("No verification report; rebuild Signer.exe. %s %s", result.stdout, result.stderr)
                return 1
            data = json.loads(report.read_text(encoding="utf-8"))
            logger.info("Verification report: %s", json.dumps(data, ensure_ascii=True))
            required = ("torch", "onnx", "openvino")
            success = (result.returncode == 0 and data.get("success") is True
                       and data.get("ocr", {}).get("success") is True
                       and all(data.get("backends", {}).get(name, {}).get("success") is True
                               for name in required))
            return 0 if success else 1
    except Exception:
        logger.exception("Built executable verification failed")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Верификация CPU-бэкендов (ONNX Runtime, OpenVINO)"
    )
    parser.add_argument(
        "--exe-path",
        type=Path,
        help="Путь к собранному Signer.exe (опционально, по умолчанию dev-режим)"
    )
    
    args = parser.parse_args()
    
    if args.exe_path:
        return verify_in_built_exe(args.exe_path)
    else:
        return verify_in_dev_mode()


if __name__ == "__main__":
    sys.exit(main())
