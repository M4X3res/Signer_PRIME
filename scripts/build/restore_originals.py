#!/usr/bin/env python
"""scripts/build/restore_originals.py - Восстановление файлов после обфускации"""
import os, sys, shutil, json, hashlib
from pathlib import Path

# Настройка кодировки для Windows
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

ROOT = Path(__file__).parent.parent.parent.resolve()
BACKUP_DIR = ROOT / "build" / "obfuscated_backup"
MANIFEST_FILE = BACKUP_DIR / "manifest.json"

def log(msg): print(f"[RESTORE] {msg}")
def error(msg): print(f"[ERROR] {msg}", file=sys.stderr)

def calc_hash(path):
    h = hashlib.sha256()
    with open(path, 'rb') as f:
        for chunk in iter(lambda: f.read(8192), b''): h.update(chunk)
    return h.hexdigest()

def main():
    log("="*60); log("Restore Original Files"); log("="*60)
    
    if not BACKUP_DIR.exists():
        log("⚠️  Бэкап не найден (уже восстановлен?)")
        return 0
    
    if not MANIFEST_FILE.exists():
        error("Манифест отсутствует!"); sys.exit(1)
    
    with open(MANIFEST_FILE, 'r', encoding='utf-8') as f:
        manifest = json.load(f)
    
    log(f"Восстановление {len(manifest['files'])} файлов...")
    
    failures = []
    for rel_path, info in manifest["files"].items():
        target = ROOT / rel_path
        backup_file = BACKUP_DIR / info["backup_path"]
        
        if not backup_file.exists():
            error(f"  Бэкап не найден: {backup_file}"); failures.append(rel_path); continue
        
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup_file, target)
        
        if calc_hash(target) != info["hash"]:
            error(f"  ❌ Хэш не совпал: {rel_path}"); failures.append(rel_path)
        else:
            log(f"  ✅ {rel_path}")
    
    log("="*60)
    if failures:
        error(f"❌ Ошибок: {len(failures)}")
        for f in failures: error(f"  - {f}")
        sys.exit(1)
    else:
        log(f"✅ Все файлы восстановлены ({len(manifest['files'])})")
        
        # Удаляем бэкап после успешного восстановления
        log("Удаление бэкапа...")
        shutil.rmtree(BACKUP_DIR)
        log("✅ Бэкап удалён")
        
        log("="*60)
        return 0

if __name__ == "__main__":
    sys.exit(main())
