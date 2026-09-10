"""
updater.py
Изолированный модуль для проверки и загрузки обновлений Signer PRIME.
НЕ импортирует core/, processing/, ui/ для минимизации зависимостей.
"""
import os
import sys
import logging
import hashlib
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import requests

from version import APP_VERSION

logger = logging.getLogger(__name__)

# Константы GitHub
GITHUB_REPO = "M4X3res/Signer_PRIME"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
ARCHIVE_PREFIX = "Signer.7z."
CHECKSUM_FILE = "checksum.sha256"

# Таймауты
REQUEST_TIMEOUT = 10  # секунд для HTTP-запросов

# 7-Zip исполняемый файл (используется 7z.exe, а не 7za.exe)
SEVEN_ZIP_EXE = "7z.exe"


@dataclass
class UpdateInfo:
    """Информация о доступном обновлении."""
    version: str
    release_notes: str
    assets: list[tuple[str, str, int]]  # (имя, url, size)
    total_size_bytes: int


def _parse_version(version_str: str) -> tuple[int, ...]:
    """
    Парсит версию вида "2.1.0" или "v2.1.0" в кортеж (2, 1, 0).
    Используется для сравнения версий.
    """
    clean = version_str.lstrip("v").strip()
    try:
        return tuple(int(x) for x in clean.split("."))
    except (ValueError, AttributeError):
        logger.warning(f"Не удалось распарсить версию: {version_str}")
        return (0, 0, 0)


def check_for_update() -> Optional[UpdateInfo]:
    """
    Проверяет наличие обновления через GitHub API.
    
    Returns:
        UpdateInfo если найдено более новое обновление, иначе None.
        При ошибке (сеть, rate-limit, 404) возвращает None с логированием.
    """
    try:
        logger.info(f"Проверка обновлений для версии {APP_VERSION}...")
        
        response = requests.get(GITHUB_API_URL, timeout=REQUEST_TIMEOUT)
        
        # Проверка rate-limit
        if response.status_code == 403:
            logger.warning("GitHub API rate limit достигнут, повторите позже")
            return None
        
        if response.status_code == 404:
            logger.info("Релизы не найдены в репозитории")
            return None
        
        response.raise_for_status()
        data = response.json()
        
        # Парсинг версии
        latest_version = data.get("tag_name", "").lstrip("v")
        release_notes = data.get("body", "Нет описания изменений")
        
        # Сравнение версий
        current = _parse_version(APP_VERSION)
        latest = _parse_version(latest_version)
        
        if latest <= current:
            logger.info(f"Обновлений нет. Текущая версия {APP_VERSION} актуальна.")
            return None
        
        # Поиск ассетов архива
        assets_data = data.get("assets", [])
        archive_assets = []
        total_size = 0
        
        for asset in assets_data:
            name = asset.get("name", "")
            if name.startswith(ARCHIVE_PREFIX) or name == CHECKSUM_FILE:
                url = asset.get("browser_download_url", "")
                size = asset.get("size", 0)
                if url:
                    archive_assets.append((name, url, size))
                    total_size += size
        
        if not archive_assets:
            logger.warning("В релизе не найдены файлы обновления (Signer.7z.*)")
            return None
        
        logger.info(f"Найдено обновление: {latest_version} (размер: {total_size / (1024**2):.1f} MB)")
        
        return UpdateInfo(
            version=latest_version,
            release_notes=release_notes,
            assets=archive_assets,
            total_size_bytes=total_size
        )
        
    except requests.RequestException as e:
        logger.warning(f"Ошибка при проверке обновлений: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка при проверке обновлений: {e}", exc_info=True)
        return None


def download_assets(
    assets: list[tuple[str, str, int]],
    dest_dir: Path,
    progress_cb: Optional[Callable[[str, int, int, float], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None
) -> bool:
    """
    Скачивает ассеты обновления.
    
    Args:
        assets: Список (имя, url, размер) для скачивания
        dest_dir: Целевая директория
        progress_cb: Callback(filename, downloaded, total, speed_bps) для прогресса
        cancel_check: Функция для проверки отмены (возвращает True если нужно отменить)
    
    Returns:
        True при успехе, False при ошибке или отмене
    """
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        for name, url, total_size in assets:
            # Проверка отмены перед началом скачивания файла
            if cancel_check and cancel_check():
                logger.info(f"Загрузка отменена перед скачиванием {name}")
                return False
            
            file_path = dest_dir / name
            logger.info(f"Скачивание {name} ({total_size / (1024**2):.1f} MB)...")
            
            try:
                response = requests.get(url, stream=True, timeout=REQUEST_TIMEOUT)
                response.raise_for_status()
                
                downloaded = 0
                chunk_size = 1024 * 1024  # 1 MB
                last_update_time = time.time()
                last_update_downloaded = 0
                
                with open(file_path, "wb") as f:
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        # Проверка отмены во время скачивания
                        if cancel_check and cancel_check():
                            logger.info(f"Загрузка отменена во время скачивания {name}")
                            # Удаляем неполный файл
                            if file_path.exists():
                                file_path.unlink()
                            return False
                        
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # Throttled callback (не чаще раза в 200мс)
                            current_time = time.time()
                            if progress_cb and (current_time - last_update_time) >= 0.2:
                                elapsed = current_time - last_update_time
                                bytes_since_last = downloaded - last_update_downloaded
                                speed_bps = bytes_since_last / elapsed if elapsed > 0 else 0
                                
                                progress_cb(name, downloaded, total_size, speed_bps)
                                
                                last_update_time = current_time
                                last_update_downloaded = downloaded
                
                # Финальный callback для завершения прогресс-бара
                if progress_cb:
                    progress_cb(name, downloaded, total_size, 0)
                
                logger.info(f"Скачивание {name} завершено")
                
            except requests.RequestException as e:
                logger.error(f"Ошибка при скачивании {name}: {e}")
                # Удаляем неполный файл
                if file_path.exists():
                    file_path.unlink()
                return False
        
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при скачивании ассетов: {e}", exc_info=True)
        return False


def verify_checksum(dest_dir: Path, checksum_filename: str = CHECKSUM_FILE) -> bool:
    """
    Проверяет SHA-256 чексуммы скачанных файлов.
    
    Args:
        dest_dir: Директория со скачанными файлами
        checksum_filename: Имя файла с чексуммами
    
    Returns:
        True если все файлы прошли проверку, False иначе
    """
    try:
        checksum_file = dest_dir / checksum_filename
        
        if not checksum_file.exists():
            logger.error(f"Файл чексумм не найден: {checksum_file}")
            return False
        
        # Парсим чексуммы
        checksums = {}
        with open(checksum_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                
                parts = line.split()
                if len(parts) >= 2:
                    # Формат: "hash filename" или "hash  filename"
                    expected_hash = parts[0]
                    filename = " ".join(parts[1:])
                    checksums[filename] = expected_hash
        
        if not checksums:
            logger.warning("Файл чексумм пуст или имеет неверный формат")
            return False
        
        # Проверяем каждый архивный файл
        logger.info("Проверка целостности скачанных файлов...")
        all_valid = True
        
        for filename, expected_hash in checksums.items():
            file_path = dest_dir / filename
            
            if not file_path.exists():
                logger.warning(f"Файл не найден для проверки: {filename}")
                continue
            
            # Вычисляем SHA-256
            sha256 = hashlib.sha256()
            with open(file_path, "rb") as f:
                while chunk := f.read(8192):
                    sha256.update(chunk)
            
            actual_hash = sha256.hexdigest()
            
            if actual_hash.lower() != expected_hash.lower():
                logger.error(f"Чексумма не совпадает для {filename}")
                logger.error(f"  Ожидалось: {expected_hash}")
                logger.error(f"  Получено:  {actual_hash}")
                all_valid = False
            else:
                logger.info(f"✓ {filename} проверен")
        
        if not all_valid:
            logger.error("Проверка целостности провалена, удаляем скачанные файлы")
            # Удаляем скачанные файлы
            for file_path in dest_dir.glob(f"{ARCHIVE_PREFIX}*"):
                try:
                    file_path.unlink()
                except Exception as e:
                    logger.warning(f"Не удалось удалить {file_path}: {e}")
            return False
        
        logger.info("Все файлы прошли проверку целостности")
        return True
        
    except Exception as e:
        logger.error(f"Ошибка при проверке чексумм: {e}", exc_info=True)
        return False


def launch_updater_and_exit(temp_dir: Path, install_dir: Path) -> None:
    """
    Запускает Updater.exe для применения обновления и завершает текущий процесс.
    
    Args:
        temp_dir: Директория со скачанными файлами обновления
        install_dir: Директория установки приложения (где Signer.exe)
    """
    try:
        # Определяем путь к Updater.exe
        if getattr(sys, "frozen", False):
            # Frozen build: Updater.exe лежит рядом с Signer.exe
            updater_exe = Path(sys.executable).parent / "Updater.exe"
        else:
            # Dev-режим: для тестирования
            updater_exe = Path(__file__).parent / "dist" / "Updater" / "Updater.exe"
        
        if not updater_exe.exists():
            logger.error(f"Updater.exe не найден: {updater_exe}")
            raise FileNotFoundError(f"Updater.exe не найден: {updater_exe}")
        
        # Путь к Signer.exe
        if getattr(sys, "frozen", False):
            signer_exe = Path(sys.executable)
        else:
            signer_exe = Path(__file__).parent / "dist" / "Signer" / "Signer.exe"
        
        # Путь к 7z.exe (рядом с Updater.exe)
        if getattr(sys, "frozen", False):
            seven_zip_exe = Path(sys.executable).parent / SEVEN_ZIP_EXE
        else:
            seven_zip_exe = Path(__file__).parent / "installer" / SEVEN_ZIP_EXE
        
        # Формируем аргументы
        args = [
            str(updater_exe),
            "--pid", str(os.getpid()),
            "--temp", str(temp_dir),
            "--install", str(install_dir),
            "--exe", str(signer_exe),
            "--7z", str(seven_zip_exe)  # Передаём путь к 7z.exe
        ]
        
        logger.info(f"Запуск Updater: {' '.join(args)}")
        
        # Запускаем Updater в фоне
        subprocess.Popen(
            args,
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            close_fds=True
        )
        
        logger.info("Updater запущен, завершение работы приложения...")
        
        # Возвращаем управление вызывающему коду для корректного закрытия Qt
        # QApplication.quit() будет вызван в UI-слое
        
    except Exception as e:
        logger.error(f"Ошибка при запуске Updater: {e}", exc_info=True)
        raise
