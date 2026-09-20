"""
updater_main.py
Исходник для Updater.exe - изолированный апплаер обновлений.
НЕ импортирует core/, processing/, ui/ для минимизации зависимостей.

Логика:
1. Ждёт завершения процесса Signer.exe
2. В режиме full: распаковывает архив обновления через 7z.exe
3. В режиме delta: распаковывает zip и применяет изменения с бэкапом/роллбеком
4. Удаляет временную папку
5. Запускает обновлённый Signer.exe
"""
import sys
import os
import time
import logging
import argparse
import subprocess
import shutil
import zipfile
import json
from pathlib import Path

if not getattr(sys, 'frozen', False):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# ════════════════════════════════════════════════════════════════
# Настройка логирования в файл
# ════════════════════════════════════════════════════════════════
def setup_logging():
    """Настраивает логирование в файл updater.log."""
    try:
        # Логируем рядом с updater.exe
        if getattr(sys, "frozen", False):
            log_path = Path(sys.executable).parent / "updater.log"
        else:
            log_path = Path(__file__).parent.parent / "updater.log"
        
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s [%(levelname)s] %(message)s',
            datefmt='%H:%M:%S',
            handlers=[
                logging.FileHandler(log_path, encoding='utf-8', mode='a'),
                logging.StreamHandler(sys.stdout)
            ]
        )
        logger = logging.getLogger(__name__)
        logger.info("=" * 60)
        logger.info("Updater запущен")
        logger.info("=" * 60)
        return logger
    except Exception as e:
        # Если логирование не удалось настроить - продолжаем без него
        print(f"[WARN] Не удалось настроить логирование: {e}")
        logging.basicConfig(level=logging.INFO)
        return logging.getLogger(__name__)


# ════════════════════════════════════════════════════════════════
# Ожидание завершения процесса
# ════════════════════════════════════════════════════════════════
def wait_for_process_exit(pid: int, timeout_sec: int = 30) -> bool:
    """
    Ждёт завершения процесса с заданным PID.
    
    Args:
        pid: PID процесса для ожидания
        timeout_sec: Таймаут ожидания в секундах
    
    Returns:
        True если процесс завершился, False если таймаут
    """
    logger = logging.getLogger(__name__)
    logger.info(f"Ожидание завершения процесса PID={pid} (таймаут {timeout_sec}с)...")
    
    # Попытка использовать psutil для корректной проверки
    try:
        import psutil
        start_time = time.time()
        while time.time() - start_time < timeout_sec:
            if not psutil.pid_exists(pid):
                logger.info(f"Процесс PID={pid} завершён (psutil)")
                return True
            time.sleep(0.5)
        
        logger.warning(f"Таймаут ожидания процесса PID={pid}, продолжаем...")
        return False
        
    except ImportError:
        # Fallback: используем ctypes для Windows
        logger.info("psutil не доступен, используем ctypes для Windows")
        
        try:
            import ctypes
            from ctypes import wintypes
            
            PROCESS_QUERY_INFORMATION = 0x0400
            SYNCHRONIZE = 0x00100000
            
            kernel32 = ctypes.windll.kernel32
            kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
            kernel32.WaitForSingleObject.restype = wintypes.DWORD
            kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
            
            # Открываем процесс
            handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | SYNCHRONIZE, False, pid)
            if not handle:
                logger.info(f"Процесс PID={pid} уже не существует (OpenProcess failed)")
                return kernel32.GetLastError() == 87
            
            try:
                # Ждём завершения процесса
                WAIT_TIMEOUT = 0x00000102
                wait_result = kernel32.WaitForSingleObject(handle, timeout_sec * 1000)
                
                if wait_result == WAIT_TIMEOUT:
                    logger.warning(f"Таймаут ожидания процесса PID={pid}, продолжаем...")
                    return False
                elif wait_result == 0:
                    return True
                return False
                    
            finally:
                kernel32.CloseHandle(handle)
                
        except Exception as e:
            logger.error(f"Ошибка при ожидании процесса через ctypes: {e}")
            # Простой fallback: просто подождём фиксированное время
            logger.info(f"Ждём {timeout_sec} секунд...")
            return False


# ════════════════════════════════════════════════════════════════
# Ретраи для файловых операций
# ════════════════════════════════════════════════════════════════
def retry_file_operation(operation, *args, max_retries=5, **kwargs):
    """
    Обёртка для файловых операций с ретраями на случай блокировки антивирусом.
    
    Args:
        operation: Функция для вызова
        *args, **kwargs: Аргументы функции
        max_retries: Максимальное число попыток
    
    Returns:
        Результат operation
    
    Raises:
        Exception: После исчерпания всех попыток
    """
    logger = logging.getLogger(__name__)
    delay = 0.3
    
    for attempt in range(1, max_retries + 1):
        try:
            return operation(*args, **kwargs)
        except (PermissionError, OSError) as e:
            if attempt < max_retries:
                logger.warning(f"Файловая операция провалена (попытка {attempt}/{max_retries}): {e}, повтор через {delay:.1f}с")
                time.sleep(delay)
                delay = min(delay * 2, 3.0)  # Экспоненциальная задержка до 3с
            else:
                logger.error(f"Файловая операция провалена после {max_retries} попыток")
                raise


# ════════════════════════════════════════════════════════════════
# Распаковка полного архива (full mode)
# ════════════════════════════════════════════════════════════════
def extract_update(temp_dir: Path, install_dir: Path, seven_zip_exe: Path) -> bool:
    """
    Распаковывает многотомный архив 7z в директорию установки.
    
    Args:
        temp_dir: Директория с скачанными файлами (Signer.7z.001, ...)
        install_dir: Целевая директория установки
        seven_zip_exe: Путь к 7z.exe
    
    Returns:
        True при успехе, False при ошибке
    """
    logger = logging.getLogger(__name__)
    
    try:
        # Находим первый том архива
        first_volume = temp_dir / "Signer.7z.001"
        
        if not first_volume.exists():
            logger.error(f"Первый том архива не найден: {first_volume}")
            return False
        
        if not seven_zip_exe.exists():
            logger.error(f"7z.exe не найден: {seven_zip_exe}")
            return False
        
        logger.info(f"Распаковка {first_volume} в {install_dir}...")
        logger.info(f"Используется 7z: {seven_zip_exe}")
        
        import tempfile
        extraction = tempfile.TemporaryDirectory(prefix="signer-full-", dir=temp_dir)
        staging = Path(extraction.name)
        # Запускаем 7z.exe x "Signer.7z.001" -o"install_dir" -y
        cmd = [
            str(seven_zip_exe),
            "x",
            str(first_volume),
            f"-o{staging}",
            "-y"  # Перезаписываем без подтверждения
        ]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode != 0:
            logger.error(f"7z завершился с кодом {result.returncode}")
            logger.error(f"stdout: {result.stdout}")
            logger.error(f"stderr: {result.stderr}")
            return False
        
        from updater.transaction import apply_full
        source = staging / 'Signer'
        if not (source / 'Signer.exe').is_file():
            raise ValueError('Archive has no Signer/Signer.exe')
        manifest_path = temp_dir / 'manifest.json'
        if not manifest_path.exists():
            raise ValueError('Full update manifest is missing')
        manifest = json.loads(manifest_path.read_text(encoding='utf-8-sig'))
        apply_full(source, install_dir, manifest)
        extraction.cleanup()
        logger.info("Распаковка завершена успешно")
        logger.info(f"7z stdout: {result.stdout}")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при распаковке: {e}", exc_info=True)
        return False


# ════════════════════════════════════════════════════════════════
# Применение дельта-обновления (delta mode)
# ════════════════════════════════════════════════════════════════
def apply_delta_update(temp_dir: Path, delta_manifest_path: Path, install_dir: Path) -> bool:
    """
    Применяет дельта-обновление с бэкапом и роллбеком.
    
    Args:
        temp_dir: Директория со скачанными файлами (delta-from-X.zip, delta_manifest.json)
        delta_manifest_path: Путь к delta_manifest.json
        install_dir: Директория установки
    
    Returns:
        True при успехе, False при ошибке (с роллбеком)
    """
    try:
        from updater.transaction import apply_delta
        apply_delta(temp_dir, delta_manifest_path, install_dir)
        return True
    except Exception:
        logging.getLogger(__name__).exception("Delta update failed")
        return False


# ════════════════════════════════════════════════════════════════
# Показ MessageBox при ошибке (Windows)
# ════════════════════════════════════════════════════════════════
def show_error_messagebox(title: str, message: str):
    """Показывает MessageBox с ошибкой (Windows)."""
    try:
        import ctypes
        MB_ICONERROR = 0x10
        ctypes.windll.user32.MessageBoxW(0, message, title, MB_ICONERROR)
    except Exception as e:
        print(f"[ERROR] Не удалось показать MessageBox: {e}")


# ════════════════════════════════════════════════════════════════
# Главная логика
# ════════════════════════════════════════════════════════════════
def main():
    """Главная функция Updater."""
    logger = setup_logging()
    
    try:
        # Парсинг аргументов
        parser = argparse.ArgumentParser(description="Signer PRIME Updater")
        parser.add_argument("--pid", type=int, required=True, help="PID процесса Signer для ожидания")
        parser.add_argument("--temp", type=str, required=True, help="Временная папка с файлами обновления")
        parser.add_argument("--install", type=str, required=True, help="Директория установки Signer")
        parser.add_argument("--exe", type=str, required=True, help="Путь к Signer.exe для запуска")
        parser.add_argument("--7z", type=str, required=True, help="Путь к 7z.exe для распаковки")
        parser.add_argument("--mode", type=str, choices=["full", "delta"], default="full", help="Режим обновления")
        parser.add_argument("--delta-manifest", type=str, help="Путь к delta_manifest.json (для delta режима)")
        
        args = parser.parse_args()
        
        logger.info(f"Параметры:")
        logger.info(f"  PID: {args.pid}")
        logger.info(f"  Temp: {args.temp}")
        logger.info(f"  Install: {args.install}")
        logger.info(f"  Exe: {args.exe}")
        logger.info(f"  7z: {getattr(args, '7z')}")
        logger.info(f"  Mode: {args.mode}")
        if args.delta_manifest:
            logger.info(f"  Delta manifest: {args.delta_manifest}")
        
        temp_dir = Path(args.temp)
        install_dir = Path(args.install)
        signer_exe = Path(args.exe)
        seven_zip_exe = Path(getattr(args, '7z'))
        
        # Шаг 1: Ждём завершения Signer
        if not wait_for_process_exit(args.pid, timeout_sec=30):
            logger.error("Signer ещё работает; обновление отменено до изменения файлов")
            show_error_messagebox("Signer — обновление отложено",
                "Signer ещё работает. Дождитесь завершения обработки и сохранения, "
                "закройте программу и повторите обновление. Файлы не изменены.")
            sys.exit(1)
        
        # Небольшая пауза для гарантированного освобождения файлов
        logger.info("Пауза перед обновлением...")
        time.sleep(1)
        
        # Шаг 2: Применяем обновление (delta или full)
        success = False
        
        if args.mode == "delta":
            if not args.delta_manifest:
                logger.error("Для delta режима требуется --delta-manifest")
                show_error_messagebox(
                    "Signer — ошибка обновления",
                    "Внутренняя ошибка: не указан путь к delta_manifest.json"
                )
                sys.exit(1)
            
            delta_manifest_path = Path(args.delta_manifest)
            success = apply_delta_update(temp_dir, delta_manifest_path, install_dir)
        else:
            success = extract_update(temp_dir, install_dir, seven_zip_exe)
        
        if not success:
            show_error_messagebox(
                "Signer — ошибка обновления",
                "Не удалось применить обновление.\nПодробности в updater.log"
            )
            logger.error("Обновление провалено, завершение с ошибкой")
            sys.exit(1)
        
        # Шаг 3: Удаляем временную папку
        try:
            logger.info(f"Удаление временной папки {temp_dir}...")
            shutil.rmtree(temp_dir, ignore_errors=True)
            logger.info("Временная папка удалена")
        except Exception as e:
            logger.warning(f"Не удалось удалить временную папку: {e}")
        
        # Шаг 4: Запускаем обновлённый Signer.exe
        if not signer_exe.exists():
            show_error_messagebox(
                "Signer — ошибка обновления",
                f"Обновлённый Signer.exe не найден:\n{signer_exe}"
            )
            logger.error(f"Signer.exe не найден: {signer_exe}")
            sys.exit(1)
        
        logger.info(f"Запуск обновлённого Signer: {signer_exe}")
        
        subprocess.Popen(
            [str(signer_exe)],
            cwd=str(install_dir),
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )
        
        logger.info("Signer успешно запущен, обновление завершено")
        logger.info("=" * 60)
        sys.exit(0)
        
    except Exception as e:
        logger.critical(f"КРИТИЧЕСКАЯ ОШИБКА: {e}", exc_info=True)
        show_error_messagebox(
            "Signer — критическая ошибка обновления",
            f"Произошла неожиданная ошибка:\n{e}\n\nПодробности в updater.log"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
