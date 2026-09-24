@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0\..\.."
if errorlevel 1 exit /b 1
set PYTHONIOENCODING=utf-8
set YOLO_AUTOINSTALL=false

echo.
echo ================================================================
echo   Preparing Signer PRIME Release
echo ================================================================
echo.

REM ================================================================
REM [0/7] Check license server URL configuration (TASK 2)
REM ================================================================

echo [0/9] Checking license server configuration...
echo.

if not exist "build_config.json" (
    echo ERROR: build_config.json not found!
    echo.
    echo Before building a production release, you MUST:
    echo 1. Copy build_config.json.example to build_config.json
    echo 2. Set the real license server URL in build_config.json
    echo.
    echo Example:
    echo {
    echo   "license_server_url": "https://your-license-server.run.app"
    echo }
    echo.
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

REM Check if placeholder URL is used
findstr /C:"https://license.signer-prime.com" build_config.json >nul
if not errorlevel 1 (
    echo ERROR: build_config.json contains placeholder URL!
    echo.
    echo Current URL: https://license.signer-prime.com
    echo.
    echo This is a placeholder URL. Replace it with your real license server URL.
    echo Example: https://your-license-server.run.app
    echo.
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

findstr /C:"your-license-server.run.app" build_config.json >nul
if not errorlevel 1 (
    echo ERROR: build_config.json contains example URL!
    echo.
    echo Current URL: https://your-license-server.run.app
    echo.
    echo Replace it with your REAL license server URL.
    echo.
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

echo OK: License server URL configured
echo.

REM Get version from version.json
for /f "tokens=2 delims=:, " %%a in ('type version.json ^| findstr "version"') do (
    set VERSION=%%~a
)
echo Version: %VERSION%
echo.

REM ================================================================
REM [1/9] Check dependencies
REM ================================================================

echo [1/9] Checking dependencies...
echo.

REM Use venv Python for consistency
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python not found in .venv\Scripts\
    echo Please create and activate virtual environment first
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

.venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python in .venv not working
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

.venv\Scripts\python.exe -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not installed
    echo Run: .venv\Scripts\pip.exe install pyinstaller
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

if not exist "installer\7z.dll" exit /b 1

if not exist "installer\7z.exe" (
    echo ERROR: 7z.exe not found in installer\
    echo Download: https://www.7-zip.org/
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

.venv\Scripts\python.exe -c "import rasterio, shapefile; from server.raster_environment import raster_environment; ctx = raster_environment(); ctx.__enter__(); print(rasterio.crs.CRS.from_epsg(3857)); ctx.__exit__(None, None, None)"
if errorlevel 1 (
    echo ERROR: Local background dependencies are missing or incompatible.
    echo Run: .venv\Scripts\python.exe -m pip install -r requirements.txt
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

echo OK: All dependencies ready
echo.

REM ================================================================
REM [2/9] Clean old builds
REM ================================================================

echo [2/9] Cleaning old builds...
.venv\Scripts\python.exe scripts\build\release_preflight.py
if errorlevel 1 exit /b 1
echo OK: Cleaned
echo.

REM ================================================================
REM [3/9] Export models to ONNX/OpenVINO (NEW in v2.0.1)
REM ================================================================

echo [3/9] Exporting models to ONNX and OpenVINO formats...
echo.

REM Check if venv python exists
if not exist ".venv\Scripts\python.exe" (
    echo ERROR: Python not found in .venv\Scripts\
    echo Please create and activate virtual environment first
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

REM Export models (both formats at once)
echo    Exporting models...
.venv\Scripts\python.exe scripts\export_models_onnx.py --format all --force
if errorlevel 1 (
    echo.
    echo ERROR: Model export failed!
    echo.
    echo CPU backends ONNX Runtime and OpenVINO will NOT work in the built application.
    echo.
    echo Possible reasons:
    echo   1. Dependencies not installed: pip install onnx onnxruntime openvino openvino-dev
    echo   2. Source .pt model files not found
    echo   3. Export error - see logs above
    echo.
    echo Build aborted. Fix errors and try again.
    echo.
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

echo Preparing offline OCR weights...
.venv\Scripts\python.exe scripts\build\prepare_ocr.py
if errorlevel 1 exit /b 1

echo OK: Models exported
echo.

REM ================================================================
REM [4/9] Obfuscate licensing modules
REM ================================================================

echo [4/9] Obfuscating licensing modules with PyArmor...
echo.

REM Check if pyarmor.exe exists in venv
if exist ".venv\Scripts\pyarmor.exe" (
    echo PyArmor found, starting obfuscation...
    set PYTHONIOENCODING=utf-8
    .venv\Scripts\python.exe scripts\build\obfuscate_licensing.py
    if errorlevel 1 (
        echo ERROR: Obfuscation failed
        if not defined SIGNER_NONINTERACTIVE pause
        exit /b 1
    )
    echo OK: Obfuscation completed
    echo.
    set SKIP_OBFUSCATION=0
) else (
    echo WARNING: PyArmor not installed in .venv
    echo Run: .venv\Scripts\pip.exe install pyarmor
    echo Skipping obfuscation...
    echo.
    set SKIP_OBFUSCATION=1
)

REM ================================================================
REM [5/9] Build application
REM ================================================================

echo [5/9] Building application...
echo.

REM Release builds must pass the production license key check.
set SKIP_PROD_KEY_CHECK=
.venv\Scripts\python.exe scripts\build\verify_license_key.py
if errorlevel 1 exit /b 1
echo Production license key check enabled.

echo.

echo    Building Signer.exe...

REM НОВАЯ ЛОГИКА: signer.spec сам определяет, использовать ли обфусцированный код
REM Если существует build/obfuscated/, spec автоматически использует его
REM Не нужно копировать файлы - spec работает напрямую с build/obfuscated/

if "%SKIP_OBFUSCATION%"=="0" (
    if exist "build\obfuscated\" (
        echo    Building from obfuscated source in build\obfuscated\
    ) else (
        echo WARNING: Obfuscation completed but build\obfuscated\ not found
        echo    Building from normal source
        set SKIP_OBFUSCATION=1
    )
) else (
    echo    Building from normal source
)

.venv\Scripts\pyinstaller.exe signer.spec --noconfirm
if errorlevel 1 (
    echo ERROR: Failed to build Signer.exe
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

echo    Building Updater.exe...
.venv\Scripts\pyinstaller.exe updater.spec --noconfirm
if errorlevel 1 (
    echo ERROR: Failed to build Updater.exe
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

echo    Copying files...

REM Check if files exist before copying
if not exist "dist\Signer\Signer.exe" (
    echo ERROR: Signer.exe not found in dist\Signer\
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

REM Check both possible locations for Updater.exe
if exist "dist\Updater.exe" (
    set UPDATER_PATH=dist\Updater.exe
) else if exist "dist\Updater\Updater.exe" (
    set UPDATER_PATH=dist\Updater\Updater.exe
) else (
    echo ERROR: Updater.exe not found
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

copy /Y "%UPDATER_PATH%" "dist\Signer\Updater.exe" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy Updater.exe
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

copy /Y "installer\7z.exe" "dist\Signer\7z.exe" >nul
copy /Y "installer\7z.dll" "dist\Signer\7z.dll" >nul
copy /Y "version.json" "dist\Signer\version.json" >nul
copy /Y "build_config.json" "dist\Signer\build_config.json" >nul

echo    Files copied successfully
echo OK: Build completed
echo.

REM ================================================================
REM [6/9] Verify CPU backends (NEW in v2.0.1)
REM ================================================================

echo [6/9] Verifying CPU backends (ONNX Runtime, OpenVINO)...
echo.

REM КРИТИЧНО: Проверяем собранный .exe, а не dev-venv!
.venv\Scripts\python.exe scripts\build\verify_cpu_backends.py --exe-path dist\Signer\Signer.exe
if errorlevel 1 (
    echo.
    echo ERROR: CPU backend verification failed!
    echo.
    echo This means ONNX Runtime and/or OpenVINO backends are NOT working
    echo in the built application and fall back to slower PyTorch.
    echo.
    echo Possible reasons:
    echo   1. onnxruntime/openvino DLLs not collected by PyInstaller
    echo   2. Exported models not found in dist\Signer\
    echo   3. signer.spec did not include all necessary files
    echo   4. Version mismatch between export and runtime libraries
    echo.
    echo Build aborted. Fix errors and try again.
    echo.
    if not defined SIGNER_NONINTERACTIVE pause
    exit /b 1
)

echo OK: CPU backends verified
echo.

REM ================================================================
REM Package the verified distribution, checksums, deltas, and installer.
REM ================================================================
.venv\Scripts\python.exe scripts\build\finish_release.py
if errorlevel 1 exit /b 1
echo Release ready. Upload with scripts\build\upload_release.ps1
if not defined SIGNER_NONINTERACTIVE pause
