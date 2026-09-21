# -*- mode: python ; coding: utf-8 -*-
"""
updater.spec — PyInstaller build-скрипт для Updater.exe.

Собирается в режиме --onefile (один EXE без папки _internal) для максимальной
независимости и портативности.

Использование:
    pyinstaller updater.spec --noconfirm

После сборки Updater.exe будет в dist/Updater/Updater.exe и должен быть
скопирован в dist/Signer/ рядом с Signer.exe.
"""

import os

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPEC))

# Resolve native dependencies from the build interpreter and Windows only.
# Unrelated tools on PATH can supply an incompatible ICU (breaking QtWidgets).
import sys
_windows = os.environ.get('SystemRoot', r'C:\Windows')
os.environ['PATH'] = os.pathsep.join([os.path.join(sys.prefix, 'Scripts'), sys.base_prefix,
    os.path.join(_windows, 'System32'), _windows,
    os.path.join(_windows, 'System32', 'WindowsPowerShell', 'v1.0')])

# ═══════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════
a = Analysis(
    ['updater/updater_main.py'],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=[
        'updater.transaction',
        'updater.permissions',
        'psutil',  # Опционально, для корректной проверки процесса
        'app.version',  # Updater использует version для проверки
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # Исключаем тяжёлые зависимости, которые не нужны Updater
        'torch',
        'torchvision',
        'cv2',
        'numpy',
        'PIL',
        'matplotlib',
        'pandas',
        'scipy',
        'sklearn',
        'tensorflow',
        'keras',
        'PyQt6',  # Updater не использует Qt
        'ultralytics',
        'easyocr',
        'onnxruntime',
        'openvino',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure)

# ═══════════════════════════════════════════════════════════════════
# EXE (onefile mode)
# ═══════════════════════════════════════════════════════════════════
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='Updater',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Для отладки можно временно переключить на True
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=os.path.join(ROOT, 'assets', 'ico.ico') if os.path.exists(os.path.join(ROOT, 'assets', 'ico.ico')) else None,
)

# ВАЖНО: В режиме --onefile НЕ используется COLLECT, результат сразу в dist/Updater.exe
# Но PyInstaller всё равно создаёт папку dist/Updater/, внутри которой один Updater.exe
