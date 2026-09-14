# -*- mode: python ; coding: utf-8 -*-
"""
signer.spec — PyInstaller build-скрипт для RoadScanner (Signer v2).

Точка входа проекта — main.py (не ViewPlayer.py, как в старой версии).
Собирается в режиме --onedir (COLLECT), как и раньше: exe + папка _internal.
Это ОБЯЗАТЕЛЬНО для utils.resource_path(), который полагается на
sys._MEIPASS, указывающий на папку с данными рядом с exe.

Использование:
    pyinstaller signer.spec --noconfirm

ВАЖНО ПЕРЕД СБОРКОЙ:
  1. Скопируйте/поместите этот файл в корень проекта (рядом с main.py).
  2. Убедитесь, что реально существуют папки с моделями:
     CNN_side/, lane_guidance_models/, small_models/,
     а также sings/, sings_text/, static/, templates/, assets/, signs.json.
     Часть из них в .gitignore (модели не хранятся в git) — так и должно
     быть, но физически на диске сборочной машины они обязаны быть.
  3. Если вы НЕ используете ONNX/OpenVINO backend — можно убрать их
     из hiddenimports/collect_* ниже, это уменьшит размер сборки.
  4. ffmpeg НЕ бандлится сюда: server/map_server.py вызывает системный
     ffmpeg через subprocess (для транскодирования клипов на карте).
     Либо распространяйте ffmpeg.exe рядом с приложением и добавьте
     его в data ниже, либо (см. .iss) предложите пользователю поставить
     его отдельно / через инсталлятор кодеков.
"""

import os
from PyInstaller.utils.hooks import (
    collect_submodules,
    collect_data_files,
    collect_dynamic_libs,
)

block_cipher = None
ROOT = os.path.dirname(os.path.abspath(SPEC))

# ═══════════════════════════════════════════════════════════════════
# ОБФУСКАЦИЯ: Если существует build/obfuscated/, используем его
# ═══════════════════════════════════════════════════════════════════
OBFUSCATED_DIR = os.path.join(ROOT, 'build', 'obfuscated')
USE_OBFUSCATED = os.path.isdir(OBFUSCATED_DIR)

if USE_OBFUSCATED:
    print(f"[signer.spec] OK: Obfuscated code found: {OBFUSCATED_DIR}")
    print(f"[signer.spec] Using obfuscated build")
    MAIN_SCRIPT = os.path.join(OBFUSCATED_DIR, 'main.py')
    # Добавляем build/obfuscated/ в pathex, чтобы импорты работали
    EXTRA_PATHEX = [OBFUSCATED_DIR]
else:
    print(f"[signer.spec] INFO: No obfuscation, using source code")
    MAIN_SCRIPT = os.path.join(ROOT, 'main.py')
    EXTRA_PATHEX = []

# ═══════════════════════════════════════════════════════════════════
# БИНАРНИКИ (нативные .dll/.so зависимостей)
# ═══════════════════════════════════════════════════════════════════
binaries = []
binaries += collect_dynamic_libs('torch')
binaries += collect_dynamic_libs('torchvision')
binaries += collect_dynamic_libs('cv2')

# ONNX Runtime / OpenVINO — опциональные CPU-бэкенды (BLOCK M).
# Если не установлены в venv сборки, collect_dynamic_libs просто
# вернёт пустой список — ошибки не будет.
binaries += collect_dynamic_libs('onnxruntime')
binaries += collect_dynamic_libs('openvino')

# ═══════════════════════════════════════════════════════════════════
# ДАННЫЕ (не-код файлы, нужные во время выполнения)
# ═══════════════════════════════════════════════════════════════════
datas = []
datas += collect_data_files('ultralytics')
datas += collect_data_files('easyocr')          # шрифты/наборы символов OCR
datas += collect_data_files('pyproj')            # proj.db — обязателен для core/converter.py
datas += collect_data_files('geopy')
datas += collect_data_files('certifi')           # requests/geopy используют CA-сертификаты

# Опционально — если бэкенды установлены
datas += collect_data_files('onnxruntime')
datas += collect_data_files('openvino')

# ── Собственные ресурсы проекта ────────────────────────────────────
# Обёрнуто в проверку на существование, чтобы явная ошибка была видна
# в консоли сборки, а не глухой FileNotFoundError от PyInstaller.
_project_dirs = [
    ('assets', 'assets'),
    ('CNN_side', 'CNN_side'),
    ('lane_guidance_models', 'lane_guidance_models'),
    ('small_models', 'small_models'),
    ('sings', 'sings'),                # иконки знаков для карты (server/map_server.py)
    ('sings_text', 'sings_text'),      # иконки знаков с текстом
    ('static', 'static'),              # статика Flask-сервера карты
    ('templates', 'templates'),        # templates/map.html
]
for src, dst in _project_dirs:
    full = os.path.join(ROOT, src)
    if os.path.isdir(full):
        datas.append((full, dst))
    else:
        print(f"[signer.spec] ПРЕДУПРЕЖДЕНИЕ: папка не найдена и НЕ будет включена: {full}")

_project_files = [
    'configs/data/signs.json',
    'version.json',  # Файл версии для автообновлений
]
for fname in _project_files:
    full = os.path.join(ROOT, fname)
    if os.path.isfile(full):
        # signs.json нужен в корне для обратной совместимости
        if fname == 'configs/data/signs.json':
            datas.append((full, '.'))
        else:
            datas.append((full, '.'))
    else:
        print(f"[signer.spec] ПРЕДУПРЕЖДЕНИЕ: файл не найден и НЕ будет включён: {full}")

# ── Автообновление: 7z.exe для Updater ─────────────────────────────
# Используем 7z.exe из директории installer (там же где для Inno Setup).
# Также требуется 7z.dll.
_7z_exe = os.path.join(ROOT, 'installer', '7z.exe')
_7z_dll = os.path.join(ROOT, 'installer', '7z.dll')

if os.path.isfile(_7z_exe) and os.path.isfile(_7z_dll):
    datas.append((_7z_exe, '.'))
    datas.append((_7z_dll, '.'))
    print(f"[signer.spec] OK: 7z.exe включён в сборку: {_7z_exe}")
    print(f"[signer.spec] OK: 7z.dll включён в сборку: {_7z_dll}")
else:
    if not os.path.isfile(_7z_exe):
        print(f"[signer.spec] ⚠ ВНИМАНИЕ: 7z.exe не найден в {_7z_exe}")
    if not os.path.isfile(_7z_dll):
        print(f"[signer.spec] ⚠ ВНИМАНИЕ: 7z.dll не найден в {_7z_dll}")
    print(f"[signer.spec] Автообновление не будет работать без 7z.exe и 7z.dll!")
    print(f"[signer.spec] Скачайте 7-Zip и поместите 7z.exe и 7z.dll в installer/")

# ── PyArmor runtime (ЗАДАЧА 3: Обфускация лицензирования) ──────────
# Если сборка идёт из build/obfuscated (после obfuscate_licensing.py),
# PyArmor генерирует папку pyarmor_runtime_XXXXXX, которую нужно включить.
_obfuscated_root = os.path.join(ROOT, 'build', 'obfuscated')
if os.path.isdir(_obfuscated_root):
    # БАГ 5: Ищем pyarmor_runtime_* рекурсивно (может быть вложен в licensing/)
    import glob
    pyarmor_runtime_dirs = glob.glob(
        os.path.join(_obfuscated_root, '**', 'pyarmor_runtime_*'),
        recursive=True
    )
    # Дедуплицируем (если один runtime встречается несколько раз по путям)
    seen = set()
    for rt_dir in pyarmor_runtime_dirs:
        if os.path.isdir(rt_dir):
            rt_name = os.path.basename(rt_dir)
            if rt_name not in seen:
                seen.add(rt_name)
                datas.append((rt_dir, rt_name))
                print(f"[signer.spec] OK: PyArmor runtime включён: {rt_name}")
else:
    print(f"[signer.spec] INFO: No obfuscation applied (build/obfuscated not found)")

# ═══════════════════════════════════════════════════════════════════
# HIDDEN IMPORTS (модули, которые PyInstaller не видит статическим
# анализом — динамические import'ы внутри функций, плагинные системы)
# ═══════════════════════════════════════════════════════════════════
hiddenimports = []
hiddenimports += collect_submodules('ultralytics')
hiddenimports += collect_submodules('torch')
hiddenimports += collect_submodules('torchvision')
hiddenimports += collect_submodules('cv2')
hiddenimports += collect_submodules('numpy')
hiddenimports += collect_submodules('easyocr')
hiddenimports += collect_submodules('PyQt6')
hiddenimports += collect_submodules('joblib')
hiddenimports += collect_submodules('shapely')
hiddenimports += collect_submodules('pyproj')
hiddenimports += collect_submodules('geopy')
hiddenimports += collect_submodules('gpxpy')
hiddenimports += collect_submodules('geojson')

# Flask / SocketIO стек (server/map_server.py, server/server_thread.py)
hiddenimports += collect_submodules('flask')
hiddenimports += collect_submodules('flask_cors')
hiddenimports += collect_submodules('flask_socketio')
hiddenimports += collect_submodules('engineio')
hiddenimports += collect_submodules('socketio')
hiddenimports += [
    'engineio.async_drivers.threading',  # async_mode="threading" в map_server.py
]

# Опциональные CPU-инференс бэкенды (configs/sign_models.py, configs/inference_threading.py)
hiddenimports += collect_submodules('onnxruntime')
hiddenimports += collect_submodules('openvino')

# Автообновление, лицензирование и утилиты (app/, updater/, licensing/, ui/)
hiddenimports += [
    # ЗАДАЧА 3: Явные импорты лицензирования для PyInstaller
    'licensing',
    'licensing.license_manager',
    'licensing.license_client',
    'licensing.device_fingerprint',
    'licensing.public_key',
]

# UI, core, processing, configs, server - используем collect_submodules для полного покрытия
# Если используем обфусцированный код, collect_submodules должен работать из EXTRA_PATHEX
if USE_OBFUSCATED:
    # Добавляем временно build/obfuscated в sys.path для collect_submodules
    import sys
    if OBFUSCATED_DIR not in sys.path:
        sys.path.insert(0, OBFUSCATED_DIR)
    print(f"[signer.spec] Collecting submodules from obfuscated build...")

hiddenimports += collect_submodules('ui')
hiddenimports += collect_submodules('core')
hiddenimports += collect_submodules('processing')
hiddenimports += collect_submodules('configs')
hiddenimports += collect_submodules('server')
hiddenimports += collect_submodules('app')
hiddenimports += collect_submodules('updater')

# ═══════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════
a = Analysis(
    [MAIN_SCRIPT],  # Используем обфусцированный main.py если есть
    pathex=[ROOT] + EXTRA_PATHEX,  # Добавляем build/obfuscated/ в путь
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=['onnx.reference', 'tensorflow', 'keras'],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='Signer',
    debug=False,
    console=False,
    icon=os.path.join(ROOT, 'assets', 'ico.ico'),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='Signer',
)
