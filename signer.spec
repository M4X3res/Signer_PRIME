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
    print(f"[signer.spec] ✓ 7z.exe включён в сборку: {_7z_exe}")
    print(f"[signer.spec] ✓ 7z.dll включён в сборку: {_7z_dll}")
else:
    if not os.path.isfile(_7z_exe):
        print(f"[signer.spec] ⚠ ВНИМАНИЕ: 7z.exe не найден в {_7z_exe}")
    if not os.path.isfile(_7z_dll):
        print(f"[signer.spec] ⚠ ВНИМАНИЕ: 7z.dll не найден в {_7z_dll}")
    print(f"[signer.spec] Автообновление не будет работать без 7z.exe и 7z.dll!")
    print(f"[signer.spec] Скачайте 7-Zip и поместите 7z.exe и 7z.dll в installer/")

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

# Автообновление и утилиты (app/, updater/, ui/widgets/update_*)
hiddenimports += [
    'app',
    'app.version',
    'app.utils',
    'updater',
    'updater.updater',
    'updater.updater_main',
    'ui.widgets.update_worker',
    'ui.widgets.update_dialog',
]

# ═══════════════════════════════════════════════════════════════════
# ANALYSIS
# ═══════════════════════════════════════════════════════════════════
a = Analysis(
    ['main.py'],
    pathex=[ROOT],
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
