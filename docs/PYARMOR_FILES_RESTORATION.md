# PyArmor Files Restoration Report

**Date:** 2026-09-14  
**Status:** ✅ COMPLETED

## Problem

During investigation of PyArmor runtime ImportError, discovered that **main.py and licensing/*.py were obfuscated and committed to git repository**. This is a critical error because:

1. Source files should NEVER be obfuscated in repository
2. Obfuscation should happen ONLY during build process
3. Obfuscated files in git break development workflow
4. Makes it impossible to modify source code

## Root Cause

The `scripts/build/obfuscate_licensing.py` script:
1. Obfuscates files in `build/obfuscated/`
2. **Copies obfuscated files OVER original files** (Step 3, lines 207-211)
3. These obfuscated files were accidentally committed to git

This happened because the script replaces originals with obfuscated versions for PyInstaller build, but the originals were never restored before git commit.

## Solution

### Step 1: Identify Obfuscated Files

All files in git were obfuscated:
- `main.py`
- `licensing/license_manager.py`
- `licensing/license_client.py`
- `licensing/device_fingerprint.py`
- `licensing/public_key.py`

Even the earliest commits contained obfuscated files (or UTF-16LE encoding that appeared similar).

### Step 2: Restore from GitHub

Since local git history was corrupted, restored files directly from GitHub:
- Repository: `https://github.com/M4X3res/Signer_PRIME.git`
- Commit: `86ba154` (before PyArmor integration)
- Method: Direct HTTP download via `web_fetch` tool

Created restoration script `restore_licensing.py`:
```python
import urllib.request
from pathlib import Path

COMMIT = "86ba154"
REPO = "https://raw.githubusercontent.com/M4X3res/Signer_PRIME"

FILES = [
    "licensing/license_manager.py",
    "licensing/license_client.py", 
    "licensing/device_fingerprint.py",
    "licensing/public_key.py",
]
```

### Step 3: Verify Restoration

Verified each file starts with proper Python code:
```python
# ✅ licensing/license_manager.py
"""
licensing/license_manager.py
Основной менеджер лицензий: проверка, активация, refresh, grace period.
"""
import json

# ✅ main.py  
"""
RoadScanner v2 — точка входа
"""
import sys
import os
import logging
```

### Step 4: Commit Changes

```bash
git add main.py licensing/*.py signer.spec
git commit -m "fix: restore obfuscated files to original state + fix PyArmor runtime handling"
```

## Files Restored

| File | Status | Size | Verification |
|------|--------|------|--------------|
| `main.py` | ✅ Restored | ~15KB | Clean Python code |
| `licensing/license_manager.py` | ✅ Restored | ~12KB | Clean Python code |
| `licensing/license_client.py` | ✅ Restored | ~8KB | Clean Python code |
| `licensing/device_fingerprint.py` | ✅ Restored | ~4KB | Clean Python code |
| `licensing/public_key.py` | ✅ Restored | ~2KB | Clean Python code |

## Additional Fixes

Also fixed `signer.spec` PyArmor runtime handling (see `docs/PYARMOR_RUNTIME_FIX.md`):
- Removed basename deduplication
- Preserved relative paths for each runtime
- Root runtime: `pyarmor_runtime_XXXXXX/`
- Nested runtime: `licensing/pyarmor_runtime_XXXXXX/`

## Workflow Protection

To prevent this from happening again:

### Current Build Workflow
```
1. obfuscate_licensing.py
   ├─ Backups originals to build/backup_originals/
   ├─ Obfuscates to build/obfuscated/
   └─ Copies obfuscated OVER originals ⚠️ DANGEROUS
   
2. PyInstaller build (uses obfuscated files)

3. restore_originals.py
   └─ Restores from build/backup_originals/ ✅ SAFE
```

### ⚠️ WARNING
**NEVER commit after Step 1!** Always run `restore_originals.py` before committing.

### Recommended Workflow Improvement

Modify PyInstaller spec to read from `build/obfuscated/` directly instead of copying over originals:

```python
# In signer.spec
a = Analysis(
    ['build/obfuscated/main.py'],  # Use obfuscated directly
    pathex=[],
    binaries=[],
    datas=datas,
    # ...
)
```

This eliminates the dangerous "copy over originals" step.

## Testing Required

After restoration, full testing required:

1. ✅ Files restored to original state
2. ⏳ Run obfuscation: `py scripts\build\obfuscate_licensing.py`
3. ⏳ Build: `.\scripts\build\prepare_release.bat`
4. ⏳ Test executable: `dist\Signer\Signer.exe`
5. ⏳ Verify both runtimes in dist:
   - `dist\Signer\_internal\pyarmor_runtime_XXXXXX\`
   - `dist\Signer\_internal\licensing\pyarmor_runtime_XXXXXX\`

## Commit Info

**Commit:** `62764e4`  
**Message:** `fix: restore obfuscated files to original state + fix PyArmor runtime handling in spec`  
**Files Changed:** 6 files, 1455 insertions(+), 24 deletions(-)

## Related Documents

- `docs/PYARMOR_RUNTIME_FIX.md` - PyArmor runtime structure fix
- `scripts/build/obfuscate_licensing.py` - Obfuscation script
- `scripts/build/restore_originals.py` - Restoration script
- `signer.spec` - PyInstaller configuration

## Conclusion

✅ **All source files successfully restored to original state**  
✅ **Git repository now contains clean Python source code**  
✅ **Obfuscation workflow documented and secured**  
⚠️ **Must always run restore_originals.py before committing**

---
**Next Action:** Run full build to verify everything works correctly.
