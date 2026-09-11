"""
build_release_manifest.py
Скрипт для генерации манифеста файлов релиза и создания дельта-пакетов.

Использование:
    python scripts/build_release_manifest.py \\
        --dist-dir dist/Signer \\
        --repo M4X3res/Signer_PRIME \\
        --out-dir dist/release_assets \\
        --current-version 2.1.0
"""
import os
import sys
import json
import hashlib
import argparse
import zipfile
import logging
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional
import requests

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


def calculate_sha256(file_path: Path) -> str:
    """Вычисляет SHA-256 хеш файла."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(8192 * 1024):  # 8 MB chunks
            sha256.update(chunk)
    return sha256.hexdigest()


def build_manifest(dist_dir: Path, version: str) -> dict:
    """
    Строит манифест всех файлов в dist_dir.
    
    Args:
        dist_dir: Директория dist/Signer
        version: Версия релиза (например, "2.1.0")
    
    Returns:
        Словарь с манифестом:
        {
            "version": "2.1.0",
            "generated_at": "2026-09-11T12:00:00Z",
            "files": {
                "Signer.exe": {"sha256": "...", "size": 12345},
                ...
            }
        }
    """
    logger.info(f"Сканирование директории {dist_dir}...")
    
    if not dist_dir.exists():
        raise FileNotFoundError(f"Директория не найдена: {dist_dir}")
    
    files = {}
    total_files = 0
    total_size = 0
    
    for file_path in dist_dir.rglob("*"):
        if file_path.is_file():
            # Относительный путь с прямыми слешами (posix-style)
            rel_path = file_path.relative_to(dist_dir).as_posix()
            
            # Вычисляем хеш и размер
            file_size = file_path.stat().st_size
            file_hash = calculate_sha256(file_path)
            
            files[rel_path] = {
                "sha256": file_hash,
                "size": file_size
            }
            
            total_files += 1
            total_size += file_size
            
            if total_files % 100 == 0:
                logger.info(f"  Обработано {total_files} файлов, {total_size / (1024**2):.1f} MB...")
    
    logger.info(f"✓ Всего файлов: {total_files}, размер: {total_size / (1024**2):.1f} MB")
    
    manifest = {
        "version": version,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "files": files
    }
    
    return manifest


def fetch_previous_manifest(repo: str, github_token: Optional[str] = None) -> Optional[dict]:
    """
    Скачивает manifest.json из последнего опубликованного релиза.
    
    Args:
        repo: Репозиторий в формате "owner/repo"
        github_token: Опциональный токен для авторизации (для приватных репо или rate-limit)
    
    Returns:
        Словарь с манифестом или None если манифест не найден
    """
    try:
        api_url = f"https://api.github.com/repos/{repo}/releases/latest"
        headers = {}
        if github_token:
            headers["Authorization"] = f"token {github_token}"
        
        logger.info(f"Получение последнего релиза из {repo}...")
        response = requests.get(api_url, headers=headers, timeout=30)
        
        if response.status_code == 404:
            logger.warning("Последний релиз не найден (404)")
            return None
        
        response.raise_for_status()
        data = response.json()
        
        # Ищем manifest.json в ассетах
        for asset in data.get("assets", []):
            if asset.get("name") == "manifest.json":
                manifest_url = asset.get("browser_download_url")
                logger.info(f"Найден manifest.json: {manifest_url}")
                
                manifest_response = requests.get(manifest_url, timeout=30)
                manifest_response.raise_for_status()
                
                manifest = manifest_response.json()
                logger.info(f"✓ Загружен манифест версии {manifest.get('version')}")
                return manifest
        
        logger.warning("manifest.json не найден в ассетах последнего релиза")
        return None
        
    except requests.RequestException as e:
        logger.error(f"Ошибка при получении предыдущего манифеста: {e}")
        return None
    except Exception as e:
        logger.error(f"Неожиданная ошибка: {e}", exc_info=True)
        return None


def compute_delta(old_manifest: dict, new_manifest: dict) -> dict:
    """
    Вычисляет разницу между двумя манифестами.
    
    Returns:
        {
            "added": ["file1.exe", ...],
            "changed": ["file2.dll", ...],
            "removed": ["file3.txt", ...]
        }
    """
    old_files = old_manifest.get("files", {})
    new_files = new_manifest.get("files", {})
    
    old_paths = set(old_files.keys())
    new_paths = set(new_files.keys())
    
    added = sorted(new_paths - old_paths)
    removed = sorted(old_paths - new_paths)
    
    changed = []
    for path in sorted(new_paths & old_paths):
        if old_files[path]["sha256"] != new_files[path]["sha256"]:
            changed.append(path)
    
    logger.info(f"Delta: +{len(added)} новых, ~{len(changed)} изменённых, -{len(removed)} удалённых")
    
    return {
        "added": added,
        "changed": changed,
        "removed": removed
    }


def create_delta_package(
    dist_dir: Path,
    delta: dict,
    from_version: str,
    to_version: str,
    out_dir: Path,
    new_manifest: dict
) -> Optional[tuple[Path, Path]]:
    """
    Создаёт дельта-пакет (zip-архив) с изменёнными/новыми файлами.
    
    Returns:
        (delta_zip_path, delta_manifest_path) или None при ошибке
    """
    try:
        out_dir.mkdir(parents=True, exist_ok=True)
        
        # Имена файлов
        delta_zip_name = f"delta-from-{from_version}.zip"
        delta_zip_path = out_dir / delta_zip_name
        delta_manifest_path = out_dir / "delta_manifest.json"
        
        # Список файлов для включения в архив
        files_to_include = delta["added"] + delta["changed"]
        
        if not files_to_include:
            logger.info("Нет изменённых/новых файлов, дельта-пакет не создаётся")
            return None
        
        logger.info(f"Создание дельта-архива {delta_zip_name}...")
        logger.info(f"  Файлов для упаковки: {len(files_to_include)}")
        
        total_size = 0
        with zipfile.ZipFile(delta_zip_path, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
            for i, rel_path in enumerate(files_to_include, 1):
                src_file = dist_dir / rel_path
                
                if not src_file.exists():
                    logger.error(f"Файл не найден: {src_file}")
                    continue
                
                # Добавляем с сохранением пути
                zf.write(src_file, arcname=rel_path)
                file_size = src_file.stat().st_size
                total_size += file_size
                
                if i % 50 == 0:
                    logger.info(f"  Упаковано {i}/{len(files_to_include)} файлов...")
        
        archive_size = delta_zip_path.stat().st_size
        logger.info(f"✓ Архив создан: {archive_size / (1024**2):.1f} MB (несжатый: {total_size / (1024**2):.1f} MB)")
        
        # Вычисляем хеш архива
        archive_sha256 = calculate_sha256(delta_zip_path)
        
        # Вычисляем хеш целевого манифеста
        manifest_json = json.dumps(new_manifest, indent=2, ensure_ascii=False)
        target_manifest_sha256 = hashlib.sha256(manifest_json.encode("utf-8")).hexdigest()
        
        # Создаём delta_manifest.json
        delta_manifest = {
            "from_version": from_version,
            "to_version": to_version,
            "changed_or_added": files_to_include,
            "removed": delta["removed"],
            "archive_sha256": archive_sha256,
            "archive_size": archive_size,
            "target_manifest_sha256": target_manifest_sha256
        }
        
        with open(delta_manifest_path, "w", encoding="utf-8") as f:
            json.dump(delta_manifest, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Создан {delta_manifest_path.name}")
        
        return delta_zip_path, delta_manifest_path
        
    except Exception as e:
        logger.error(f"Ошибка при создании дельта-пакета: {e}", exc_info=True)
        return None


def main():
    parser = argparse.ArgumentParser(description="Генерация манифеста релиза и дельта-пакета")
    parser.add_argument("--dist-dir", type=str, required=True, help="Директория dist/Signer")
    parser.add_argument("--repo", type=str, required=True, help="GitHub репозиторий (owner/repo)")
    parser.add_argument("--out-dir", type=str, required=True, help="Директория для выходных файлов")
    parser.add_argument("--current-version", type=str, required=True, help="Текущая версия (например, 2.1.0)")
    parser.add_argument("--github-token", type=str, help="GitHub token для API (опционально)")
    
    args = parser.parse_args()
    
    dist_dir = Path(args.dist_dir)
    out_dir = Path(args.out_dir)
    current_version = args.current_version.lstrip("v")
    
    try:
        # Шаг 1: Строим манифест текущей сборки
        logger.info("=" * 60)
        logger.info(f"Шаг 1: Генерация манифеста для версии {current_version}")
        logger.info("=" * 60)
        
        current_manifest = build_manifest(dist_dir, current_version)
        
        # Сохраняем манифест
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = out_dir / "manifest.json"
        
        with open(manifest_path, "w", encoding="utf-8") as f:
            json.dump(current_manifest, f, indent=2, ensure_ascii=False)
        
        logger.info(f"✓ Сохранён {manifest_path}")
        
        # Шаг 2: Пытаемся получить манифест предыдущей версии
        logger.info("")
        logger.info("=" * 60)
        logger.info("Шаг 2: Получение манифеста предыдущей версии")
        logger.info("=" * 60)
        
        previous_manifest = fetch_previous_manifest(args.repo, args.github_token)
        
        if previous_manifest is None:
            logger.warning("Предыдущий манифест не найден, дельта не будет создана")
            logger.info("Публикуйте только полный архив и manifest.json")
            return 0
        
        # Шаг 3: Вычисляем дельту
        logger.info("")
        logger.info("=" * 60)
        logger.info("Шаг 3: Вычисление дельты")
        logger.info("=" * 60)
        
        delta = compute_delta(previous_manifest, current_manifest)
        
        # Шаг 4: Создаём дельта-пакет
        logger.info("")
        logger.info("=" * 60)
        logger.info("Шаг 4: Создание дельта-пакета")
        logger.info("=" * 60)
        
        result = create_delta_package(
            dist_dir,
            delta,
            previous_manifest["version"],
            current_version,
            out_dir,
            current_manifest
        )
        
        if result:
            delta_zip, delta_manifest = result
            logger.info("")
            logger.info("=" * 60)
            logger.info("✓ ГОТОВО")
            logger.info("=" * 60)
            logger.info("Файлы для публикации:")
            logger.info(f"  - {manifest_path}")
            logger.info(f"  - {delta_zip}")
            logger.info(f"  - {delta_manifest}")
        else:
            logger.info("")
            logger.info("=" * 60)
            logger.info("✓ ГОТОВО (без дельты)")
            logger.info("=" * 60)
            logger.info("Файлы для публикации:")
            logger.info(f"  - {manifest_path}")
        
        return 0
        
    except Exception as e:
        logger.error(f"Критическая ошибка: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
