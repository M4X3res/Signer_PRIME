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
    copy_metadata,
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

# ── CPU-бэкенды: ONNX Runtime / OpenVINO (ОБЯЗАТЕЛЬНО в v2.0.1+) ──
# Проверяем наличие пакетов в venv сборки
import subprocess
import sys

def check_package_installed(package_name: str) -> bool:
    """Проверяет, установлен ли пакет в текущем venv."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            check=False
        )
        return result.returncode == 0
    except Exception:
        return False

def get_package_version(package_name: str) -> str:
    """Возвращает версию установленного пакета."""
    try:
        result = subprocess.run(
            [sys.executable, "-m", "pip", "show", package_name],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode == 0:
            for line in result.stdout.splitlines():
                if line.startswith("Version:"):
                    return line.split(":", 1)[1].strip()
        return "unknown"
    except Exception:
        return "unknown"

# КРИТИЧНО: Проверяем соответствие версий требованиям
REQUIRED_VERSIONS = {
    "onnx": "1.17.0",
    "onnxruntime": "1.19.2",
    "openvino": "2024.4.0",
}

version_mismatches = []
for package_name, required_version in REQUIRED_VERSIONS.items():
    if check_package_installed(package_name):
        installed_version = get_package_version(package_name)
        if installed_version != required_version:
            version_mismatches.append(
                f"{package_name}: требуется {required_version}, установлено {installed_version}"
            )

if version_mismatches:
    print(f"[signer.spec] ❌ ERROR: Несоответствие версий CPU-бэкендов!")
    for mismatch in version_mismatches:
        print(f"[signer.spec]    {mismatch}")
    print(f"[signer.spec] ")
    print(f"[signer.spec] КРИТИЧНО: Версии при экспорте и runtime должны совпадать!")
    print(f"[signer.spec] Установите точные версии:")
    print(f"[signer.spec]    pip install -r requirements-cpu-backends.txt")
    raise RuntimeError(
        "Несоответствие версий CPU-бэкендов. Экспортированные модели могут не загружаться. "
        f"Проблемы: {'; '.join(version_mismatches)}"
    )

# Проверяем ONNX Runtime
onnx_installed = check_package_installed('onnxruntime')
if onnx_installed:
    onnx_libs = collect_dynamic_libs('onnxruntime')
    binaries += onnx_libs
    print(f"[signer.spec] ✅ ONNX Runtime: найдено {len(onnx_libs)} библиотек")
else:
    print(f"[signer.spec] ❌ ERROR: ONNX Runtime не установлен в venv сборки!")
    print(f"[signer.spec]    Установите: pip install onnxruntime")
    print(f"[signer.spec]    CPU-бэкенд ONNX НЕ будет работать в собранном приложении!")
    # Прерываем сборку
    raise RuntimeError(
        "ONNX Runtime отсутствует. Для релиза v2.0.1+ это обязательная зависимость. "
        "Установите: pip install onnxruntime"
    )

# Проверяем OpenVINO
openvino_installed = check_package_installed('openvino')
# Временное хранилище для дополнительных файлов OpenVINO
extra_openvino_datas = []

if openvino_installed:
    openvino_libs = collect_dynamic_libs('openvino')
    binaries += openvino_libs
    print(f"[signer.spec] ✅ OpenVINO: найдено {len(openvino_libs)} библиотек")
    
    # КРИТИЧЕСКОЕ ИСПРАВЛЕНИЕ (BUG-ROOT-CAUSE): явный сбор всех файлов OpenVINO
    # collect_dynamic_libs не всегда подхватывает плагины и конфиги
    import glob
    try:
        import openvino
        ov_root = os.path.dirname(openvino.__file__)
        ov_libs_dir = os.path.join(ov_root, 'libs')
        
        # Собираем все файлы из libs/ (DLL, XML конфиги плагинов и т.д.)
        if os.path.isdir(ov_libs_dir):
            extra_ov_files = []
            for root_dir, dirs, files in os.walk(ov_libs_dir):
                for file in files:
                    src = os.path.join(root_dir, file)
                    # Относительный путь внутри openvino/libs/
                    rel_path = os.path.relpath(src, ov_root)
                    dest_dir = os.path.join('openvino', os.path.dirname(rel_path))
                    
                    # Добавляем как data (не binary), чтобы сохранить структуру
                    extra_ov_files.append((src, dest_dir))
            
            # Убираем дубликаты с binaries (уже добавленные через collect_dynamic_libs)
            existing_binaries_set = {os.path.basename(b[0]) for b in binaries}
            unique_ov_files = [
                (src, dst) for src, dst in extra_ov_files 
                if os.path.basename(src) not in existing_binaries_set
            ]
            
            if unique_ov_files:
                extra_openvino_datas = unique_ov_files
            
            print(f"[signer.spec] ℹ️  OpenVINO root: {ov_root}")
    except Exception as e:
        print(f"[signer.spec] ⚠️  Ошибка при сборе дополнительных файлов OpenVINO: {e}")
else:
    print(f"[signer.spec] ❌ ERROR: OpenVINO не установлен в venv сборки!")
    print(f"[signer.spec]    Установите: pip install openvino")
    print(f"[signer.spec]    CPU-бэкенд OpenVINO НЕ будет работать в собранном приложении!")
    # Прерываем сборку
    raise RuntimeError(
        "OpenVINO отсутствует. Для релиза v2.0.1+ это обязательная зависимость. "
        "Установите: pip install openvino"
    )

# ═══════════════════════════════════════════════════════════════════
# ДАННЫЕ (не-код файлы, нужные во время выполнения)
# ═══════════════════════════════════════════════════════════════════
datas = []
for package in ("onnx", "onnxruntime", "openvino", "ultralytics", "easyocr"):
    datas += copy_metadata(package)

ocr_dir = os.path.join(ROOT, "build", "ocr_models")
for name in ("craft_mlt_25k.pth", "cyrillic_g2.pth"):
    source = os.path.join(ocr_dir, name)
    if not os.path.isfile(source):
        raise RuntimeError("Run scripts/build/prepare_ocr.py before building: " + source)
    datas.append((source, "ocr_models"))

datas += collect_data_files('ultralytics')
datas += collect_data_files('easyocr')          # шрифты/наборы символов OCR
datas += collect_data_files('pyproj')            # proj.db — обязателен для core/converter.py
datas += collect_data_files('geopy')
datas += collect_data_files('certifi')           # requests/geopy используют CA-сертификаты

# Опционально — если бэкенды установлены
onnx_data = collect_data_files('onnxruntime')
openvino_data = collect_data_files('openvino')
datas += onnx_data
datas += openvino_data

# Добавляем дополнительные файлы OpenVINO, собранные выше
if extra_openvino_datas:
    datas += extra_openvino_datas

print(f"[signer.spec] ✅ ONNX Runtime data: {len(onnx_data)} файлов")
print(f"[signer.spec] ✅ OpenVINO data: {len(openvino_data)} файлов")
if extra_openvino_datas:
    print(f"[signer.spec] ✅ OpenVINO дополнительные файлы добавлены: {len(extra_openvino_datas)}")


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

# ── CPU-бэкенды: проверка наличия экспортированных моделей (v2.0.1+) ──
import glob

# Every runtime model is mandatory, not just one export of each format.
import ast
with open(os.path.join(ROOT, 'scripts', 'export_models_onnx.py'), encoding='utf-8-sig') as stream:
    export_tree = ast.parse(stream.read())
model_specs = next(ast.literal_eval(node.value) for node in export_tree.body
                   if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name)
                   and target.id == 'MODELS' for target in node.targets))
for relative, task, image_size in model_specs:
    source = os.path.join(ROOT, relative)
    base = os.path.splitext(source)[0]
    required = [source, base + '.onnx', os.path.join(base + '_openvino_model', os.path.basename(base) + '.xml'),
                os.path.join(base + '_openvino_model', os.path.basename(base) + '.bin')]
    for path in required:
        if not os.path.isfile(path) or os.path.getsize(path) == 0:
            raise RuntimeError('Missing model component: ' + path)
    with open(source, 'rb') as stream:
        if stream.read(50).startswith(b'version https://git-lfs.github.com/spec/v1'):
            raise RuntimeError('Git LFS pointer instead of model weights: ' + source)

# Проверяем наличие .onnx файлов
onnx_models = []
for model_dir in ['CNN_side', 'lane_guidance_models', 'small_models']:
    pattern = os.path.join(ROOT, model_dir, '*.onnx')
    found = glob.glob(pattern)
    onnx_models.extend(found)

if onnx_models:
    print(f"[signer.spec] ✅ Найдено {len(onnx_models)} ONNX моделей")
else:
    print(f"[signer.spec] ❌ ERROR: ONNX модели не найдены!")
    print(f"[signer.spec]    Запустите: python scripts/export_models_onnx.py --format onnx")
    print(f"[signer.spec]    CPU-бэкенд ONNX НЕ будет работать без экспортированных моделей!")
    raise RuntimeError(
        "ONNX модели не найдены. Для релиза v2.0.1+ необходимо экспортировать модели. "
        "Запустите: python scripts/export_models_onnx.py --format onnx"
    )

# Проверяем наличие OpenVINO моделей
openvino_models = []
for model_dir in ['CNN_side', 'lane_guidance_models', 'small_models']:
    pattern = os.path.join(ROOT, model_dir, '*_openvino_model')
    found = glob.glob(pattern)
    # Проверяем, что это действительно директории
    found = [d for d in found if os.path.isdir(d)]
    openvino_models.extend(found)

if openvino_models:
    print(f"[signer.spec] ✅ Найдено {len(openvino_models)} OpenVINO моделей")
else:
    print(f"[signer.spec] ❌ ERROR: OpenVINO модели не найдены!")
    print(f"[signer.spec]    Запустите: python scripts/export_models_onnx.py --format openvino")
    print(f"[signer.spec]    CPU-бэкенд OpenVINO НЕ будет работать без экспортированных моделей!")
    raise RuntimeError(
        "OpenVINO модели не найдены. Для релиза v2.0.1+ необходимо экспортировать модели. "
        "Запустите: python scripts/export_models_onnx.py --format openvino"
    )

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
# ОБЯЗАТЕЛЬНЫ в v2.0.1+ для поддержки ONNX Runtime и OpenVINO
onnx_submodules = collect_submodules('onnxruntime')
openvino_submodules = collect_submodules('openvino')
hiddenimports += onnx_submodules
hiddenimports += openvino_submodules
print(f"[signer.spec] ✅ ONNX Runtime submodules: {len(onnx_submodules)}")
print(f"[signer.spec] ✅ OpenVINO submodules: {len(openvino_submodules)}")

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
    runtime_hooks=[os.path.join(ROOT, "scripts", "build", "frozen_runtime.py")],
    noarchive=False,
)

a.datas = [entry for entry in a.datas if not entry[0].endswith(".opt.onnx")]

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
