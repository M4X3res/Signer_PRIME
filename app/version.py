"""
version.py
Единственный источник версии приложения Signer PRIME (RoadScanner).
Читает версию из version.json для гибкости (можно менять без пересборки в frozen build).
"""
import json
import os
import sys
from pathlib import Path


def _get_version_file_path() -> Path:
    """Определяет путь к version.json в зависимости от режима запуска."""
    if getattr(sys, "frozen", False):
        # Frozen build: version.json лежит рядом с exe
        return Path(sys.executable).parent / "version.json"
    else:
        # Dev режим: version.json в корне проекта (на уровень выше app/)
        return Path(__file__).parent.parent / "version.json"


def _load_version() -> str:
    """Загружает версию из version.json."""
    try:
        version_file = _get_version_file_path()
        
        if version_file.exists():
            with open(version_file, "r", encoding="utf-8") as f:
                data = json.load(f)
                version = data.get("version", "2.0.0")
                return version
        else:
            # Fallback если файл не найден
            return "2.0.0"
            
    except Exception as e:
        # В случае ошибки чтения - возвращаем дефолтную версию
        import logging
        logging.getLogger(__name__).warning(f"Не удалось прочитать version.json: {e}")
        return "2.0.0"


# Глобальная переменная с версией
APP_VERSION = _load_version()


# Для обратной совместимости и удобства
def get_version() -> str:
    """Возвращает текущую версию приложения."""
    return APP_VERSION

