"""
Скрипт для восстановления всех licensing файлов с GitHub
"""
import sys
import urllib.request
from pathlib import Path

# Настройка UTF-8 вывода для Windows консоли
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')
    sys.stderr.reconfigure(encoding='utf-8')

# Коммит ДО PyArmor integration
COMMIT = "86ba154"
REPO = "https://raw.githubusercontent.com/M4X3res/Signer_PRIME"

FILES = [
    "licensing/license_manager.py",
    "licensing/license_client.py",
    "licensing/device_fingerprint.py",
    "licensing/public_key.py",
]

def download_file(file_path):
    """Скачать файл с GitHub"""
    url = f"{REPO}/{COMMIT}/{file_path}"
    print(f"Downloading: {file_path}")
    
    try:
        with urllib.request.urlopen(url) as response:
            content = response.read().decode('utf-8')
        
        # Сохранить файл
        local_path = Path(file_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(local_path, 'w', encoding='utf-8') as f:
            f.write(content)
        
        print(f"  ✓ Saved to {file_path}")
        return True
    except Exception as e:
        print(f"  ✗ Error: {e}")
        return False

def main():
    print("=" * 70)
    print("Restoring licensing files from GitHub")
    print("=" * 70)
    print()
    
    success_count = 0
    for file_path in FILES:
        if download_file(file_path):
            success_count += 1
        print()
    
    print("=" * 70)
    print(f"Restored {success_count}/{len(FILES)} files")
    print("=" * 70)

if __name__ == "__main__":
    main()
