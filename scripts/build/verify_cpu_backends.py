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
    
    if not exe_path.exists():
        logger.error(f"❌ Собранный .exe не найден: {exe_path}")
        return 1
    
    logger.info(f"Проверка собранного приложения: {exe_path}")
    logger.info("Запуск в headless режиме с --verify-backends...")
    logger.info("")
    
    try:
        # Запускаем .exe с флагом --verify-backends
        result = subprocess.run(
            [str(exe_path), "--verify-backends"],
            capture_output=True,
            text=True,
            timeout=120,  # 2 минуты на загрузку всех моделей
            cwd=exe_path.parent  # Рабочая директория = директория .exe
        )
        
        logger.info("=== Вывод программы ===")
        logger.info(result.stdout)
        
        if result.stderr:
            logger.warning("=== Ошибки/предупреждения ===")
            logger.warning(result.stderr)
        
        # Ищем JSON результат в stdout
        try:
            # Ищем строку с JSON (после "=== VERIFICATION RESULT ===")
            lines = result.stdout.split('\n')
            json_started = False
            json_lines = []
            
            for line in lines:
                if "=== VERIFICATION RESULT ===" in line:
                    json_started = True
                    continue
                if json_started and line.strip():
                    json_lines.append(line)
            
            if json_lines:
                json_text = '\n'.join(json_lines)
                verification = json.loads(json_text)
                
                logger.info("")
                logger.info("="*80)
                logger.info("РЕЗУЛЬТАТЫ ВЕРИФИКАЦИИ")
                logger.info("="*80)
                
                for backend_name, backend_result in verification.get("backends", {}).items():
                    if backend_result["success"]:
                        logger.info(f"✅ {backend_name.upper()}: все модели загружены")
                    else:
                        logger.error(f"❌ {backend_name.upper()}: обнаружены ошибки:")
                        for error in backend_result["errors"]:
                            logger.error(f"   {error}")
                
                if verification.get("success"):
                    logger.info("")
                    logger.info("="*80)
                    logger.info("✅ ПРОВЕРКА ПРОЙДЕНА")
                    logger.info("="*80)
                    return 0
                else:
                    logger.error("")
                    logger.error("="*80)
                    logger.error("❌ ПРОВЕРКА НЕ ПРОЙДЕНА")
                    logger.error("="*80)
                    return 1
            else:
                logger.error("❌ Не удалось найти JSON результат в выводе программы")
                return 1
                
        except json.JSONDecodeError as e:
            logger.error(f"❌ Ошибка парсинга JSON результата: {e}")
            return 1
        
    except subprocess.TimeoutExpired:
        logger.error("❌ Таймаут при проверке (>120 секунд)")
        return 1
    except Exception as e:
        logger.error(f"❌ Ошибка при запуске .exe: {e}", exc_info=True)
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
