#!/usr/bin/env python
"""
scripts/build/obfuscate_licensing.py

Обф

усцирует модуль licensing/ и main.py с помощью PyArmor перед сборкой релиза.
КРИТИЧЕСКИ ВАЖНО: пишет ТОЛЬКО в build/obfuscated/, НЕ трогает исходники!
"""
import os
import sys
import shutil
import json
import hashlib
import subprocess
from pathlib import Path

# Корень проекта
ROOT = Path(__file__).parent.parent.parent.resolve()

# Пути
BACKUP_DIR = ROOT / "build" / "obfuscated_backup"
OBFUSCATED_OUTPUT_DIR = ROOT / "build" / "obfuscated"
LICENSING_DIR = ROOT / "licensing"
MAIN_PY = ROOT / "main.py"
MANIFEST_FILE = BACKUP_DIR / "manifest.json"

# Файлы для обфускации
FILES_TO_OBFUSCATE = {
    "licensing": [
        LICENSING_DIR / "__init__.py",
        LICENSING_DIR / "license_manager.py",
        LICENSING_DIR / "license_client.py",
        LICENSING_DIR / "device_fingerprint.py",
        LICENSING_DIR / "public_key.py",
    ],
    "main": [MAIN_PY]
}


def log(message: str):
    """Лог с эмодзи-маркером."""
    print(f"🔒 {message}")


def error(message: str):
    """Ошибка с эмодзи-маркером."""
    print(f"❌ {message}", file=sys.stderr)


def calculate_sha256(file_path: Path) -> str:
    """Вычисляет SHA-256 хэш файла."""
    sha256 = hashlib.sha256()
    with open(file_path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''):
            sha256.update(chunk)
    return sha256.hexdigest()


def snapshot_source_hashes():
    """Снимает хэши всех файлов которые НЕ должны измениться."""
    log("Создание snapshot хэшей исходников...")
    snapshot = {}
    
    all_files = FILES_TO_OBFUSCATE["licensing"] + FILES_TO_OBFUSCATE["main"]
    for file_path in all_files:
        if file_path.exists():
            snapshot[str(file_path.relative_to(ROOT))] = calculate_sha256(file_path)
    
    return snapshot


def verify_source_unchanged(snapshot: dict):
    """Проверяет что исходники не изменились после обфускации."""
    log("Верификация что исходники не тронуты...")
    
    changed_files = []
    for rel_path, expected_hash in snapshot.items():
        file_path = ROOT / rel_path
        if not file_path.exists():
            error(f"  ❌ Файл исчез: {rel_path}")
            changed_files.append(rel_path)
            continue
        
        actual_hash = calculate_sha256(file_path)
        if actual_hash != expected_hash:
            error(f"  ❌ ИЗМЕНЁН: {rel_path}")
            error(f"     Ожидалось: {expected_hash}")
            error(f"     Фактически: {actual_hash}")
            changed_files.append(rel_path)
    
    if changed_files:
        error("")
        error("КРИТИЧЕСКАЯ ОШИБКА: PyArmor изменил исходные файлы!")
        error("Это означает что --output путь настроен неправильно.")
        error("")
        error("Изменённые файлы:")
        for f in changed_files:
            error(f"  - {f}")
        error("")
        error("Откатываю изменения...")
        # Откат через git
        subprocess.run(["git", "checkout", "--"] + changed_files, cwd=ROOT)
        sys.exit(1)
    
    log("✅ Все исходники нетронуты")


def check_previous_run():
    """Проверяет наличие незавершённого предыдущего запуска."""
    if BACKUP_DIR.exists() and MANIFEST_FILE.exists():
        error(f"Обнаружен незавершённый предыдущий запуск обфускации!")
        error(f"Бэкап существует: {BACKUP_DIR}")
        error(f"Запустите scripts/build/restore_originals.py для восстановления, затем повторите.")
        sys.exit(1)


def create_backup():
    """Создаёт бэкап оригинальных файлов."""
    log("Создание бэкапа оригинальных файлов...")
    
    if BACKUP_DIR.exists():
        shutil.rmtree(BACKUP_DIR)
    
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    
    manifest = {"files": {}}
    
    all_files = FILES_TO_OBFUSCATE["licensing"] + FILES_TO_OBFUSCATE["main"]
    for file_path in all_files:
        if not file_path.exists():
            error(f"Файл не найден: {file_path}")
            sys.exit(1)
        
        rel_path = file_path.relative_to(ROOT)
        backup_file = BACKUP_DIR / rel_path
        backup_file.parent.mkdir(parents=True, exist_ok=True)
        
        shutil.copy2(file_path, backup_file)
        
        file_hash = calculate_sha256(file_path)
        manifest["files"][str(rel_path)] = {
            "hash": file_hash,
            "backup_path": str(backup_file.relative_to(BACKUP_DIR))
        }
        
        log(f"  Бэкап: {rel_path} (SHA-256: {file_hash[:16]}...)")
    
    import time
    manifest["timestamp"] = int(time.time())
    
    with open(MANIFEST_FILE, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    
    log(f"✅ Бэкап создан: {len(manifest['files'])} файлов")


def obfuscate_with_pyarmor():
    """Обфусцирует файлы с помощью PyArmor."""
    log("Запуск обфускации PyArmor...")
    
    # Используем python из venv (если скрипт запущен из него)
    python_exe = sys.executable
    
    try:
        result = subprocess.run(
            [python_exe, "-m", "pyarmor", "--version"],
            capture_output=True,
            text=True,
            check=True,
            cwd=ROOT
        )
        log(f"  PyArmor версия: {result.stdout.strip()}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        error(f"PyArmor не установлен! Установите: pip install pyarmor>=9.0.0")
        error(f"Python executable: {python_exe}")
        error(f"Error: {e}")
        sys.exit(1)
    
    # Очищаем build/obfuscated
    if OBFUSCATED_OUTPUT_DIR.exists():
        shutil.rmtree(OBFUSCATED_OUTPUT_DIR)
    
    OBFUSCATED_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Обфускация licensing/ в build/obfuscated/licensing/
    log("  Обфускация licensing/...")
    licensing_output = OBFUSCATED_OUTPUT_DIR / "licensing"
    
    try:
        subprocess.run(
            [
                python_exe, "-m", "pyarmor",
                "gen",
                "-O", str(licensing_output),  # КРИТИЧЕСКИ ВАЖНО: output в build/obfuscated/
                "-i",  # Runtime внутри пакета
                "-r",  # Рекурсивно
                str(LICENSING_DIR)
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True
        )
        log("    ✅ licensing/ обфусцирован")
    except subprocess.CalledProcessError as e:
        error(f"Ошибка обфускации licensing/: {e}")
        error(f"stdout: {e.stdout}")
        error(f"stderr: {e.stderr}")
        sys.exit(1)
    
    # 2. Обфускация main.py в build/obfuscated/
    log("  Обфускация main.py...")
    
    try:
        subprocess.run(
            [
                python_exe, "-m", "pyarmor",
                "gen",
                "-O", str(OBFUSCATED_OUTPUT_DIR),  # КРИТИЧЕСКИ ВАЖНО: output в build/obfuscated/
                str(MAIN_PY)
            ],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True
        )
        log("    ✅ main.py обфусцирован")
    except subprocess.CalledProcessError as e:
        error(f"Ошибка обфускации main.py: {e}")
        error(f"stdout: {e.stdout}")
        error(f"stderr: {e.stderr}")
        sys.exit(1)
    
    log("✅ Обфускация завершена")


def main():
    """Главная функция."""
    log("=" * 60)
    log("PyArmor Obfuscation Script (SAFE MODE)")
    log("=" * 60)
    
    # Снимок хэшей ПЕРЕД обфускацией
    source_snapshot = snapshot_source_hashes()
    
    # Шаг 1: Проверка предыдущего запуска
    check_previous_run()
    
    # Шаг 2: Создание бэкапа
    create_backup()
    
    # Шаг 3: Обфускация (пишет в build/obfuscated/)
    obfuscate_with_pyarmor()
    
    # Шаг 4: КРИТИЧЕСКАЯ ПРОВЕРКА - исходники не тронуты?
    verify_source_unchanged(source_snapshot)
    
    log("=" * 60)
    log("✅ Обфускация успешно завершена!")
    log(f"Результат: {OBFUSCATED_OUTPUT_DIR.relative_to(ROOT)}")
    log(f"Бэкап: {BACKUP_DIR.relative_to(ROOT)}")
    log("=" * 60)
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
