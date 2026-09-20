@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

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
    pause
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
    pause
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
    pause
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
    pause
    exit /b 1
)

.venv\Scripts\python.exe --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python in .venv not working
    pause
    exit /b 1
)

.venv\Scripts\python.exe -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not installed
    echo Run: .venv\Scripts\pip.exe install pyinstaller
    pause
    exit /b 1
)

if not exist "installer\7z.exe" (
    echo ERROR: 7z.exe not found in installer\
    echo Download: https://www.7-zip.org/
    pause
    exit /b 1
)

echo OK: All dependencies ready
echo.

REM ================================================================
REM [2/9] Clean old builds
REM ================================================================

echo [2/9] Cleaning old builds...
rmdir /s /q "dist\Signer" 2>nul
rmdir /s /q "dist\Updater" 2>nul
rmdir /s /q "build" 2>nul
rmdir /s /q "release" 2>nul
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
    pause
    exit /b 1
)

REM Export models (both formats at once)
echo    Exporting models...
.venv\Scripts\python.exe scripts\export_models_onnx.py --format all
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
    pause
    exit /b 1
)

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
        pause
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
    pause
    exit /b 1
)

echo    Building Updater.exe...
.venv\Scripts\pyinstaller.exe updater.spec --noconfirm
if errorlevel 1 (
    echo ERROR: Failed to build Updater.exe
    pause
    exit /b 1
)

echo    Copying files...

REM Check if files exist before copying
if not exist "dist\Signer\Signer.exe" (
    echo ERROR: Signer.exe not found in dist\Signer\
    pause
    exit /b 1
)

REM Check both possible locations for Updater.exe
if exist "dist\Updater.exe" (
    set UPDATER_PATH=dist\Updater.exe
) else if exist "dist\Updater\Updater.exe" (
    set UPDATER_PATH=dist\Updater\Updater.exe
) else (
    echo ERROR: Updater.exe not found
    pause
    exit /b 1
)

copy /Y "%UPDATER_PATH%" "dist\Signer\Updater.exe" >nul
if errorlevel 1 (
    echo ERROR: Failed to copy Updater.exe
    pause
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
    pause
    exit /b 1
)

echo OK: CPU backends verified
echo.

REM ================================================================
REM [7/9] Create archive
REM ================================================================

echo [7/9] Creating archive...
echo.

mkdir release 2>nul
cd dist

REM Remove old archives
del /q Signer.7z.* 2>nul

REM Create multi-volume archive (100MB parts)
..\installer\7z.exe a -v100m -mx=5 Signer.7z Signer\
if errorlevel 1 (
    echo ERROR: Failed to create archive
    cd ..
    pause
    exit /b 1
)

echo OK: Archive created
echo.

REM ================================================================
REM [8/9] Calculate checksums
REM ================================================================

echo [8/9] Calculating SHA-256 checksums...
echo.

powershell -Command "Get-ChildItem 'Signer.7z.*' | ForEach-Object { $hash = (Get-FileHash $_.FullName -Algorithm SHA256).Hash; \"$hash  $($_.Name)\" } | Out-File -Encoding utf8 'checksum.sha256'"

if errorlevel 1 (
    echo ERROR: Failed to calculate checksums
    cd ..
    pause
    exit /b 1
)

echo OK: Checksums calculated
echo.

REM ================================================================
REM [9/9] Prepare release/ folder
REM ================================================================

echo [9/9] Moving files to release\...
move /Y Signer.7z.* ..\release\ >nul
move /Y checksum.sha256 ..\release\ >nul

cd ..

REM Build manifests and deltas from preserved release_baselines/<version>/ trees.
.venv\Scripts\python.exe scripts\build\build_delta.py
if errorlevel 1 exit /b 1
.venv\Scripts\python.exe scripts\build\installer_config.py
if errorlevel 1 exit /b 1

REM Copy additional files
copy /Y "README.md" "release\README.md" >nul
if exist "docs\BUILD_AUTOUPDATE.md" copy /Y "docs\BUILD_AUTOUPDATE.md" "release\BUILD_AUTOUPDATE.md" >nul

REM Create release notes if not exists
if not exist "docs\release_notes.txt" (
    echo Signer PRIME v%VERSION% > docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo Changes in this version: >> docs\release_notes.txt
    echo - CPU-backends ONNX Runtime and OpenVINO fully supported >> docs\release_notes.txt
    echo - Guaranteed performance optimization on CPU-only systems >> docs\release_notes.txt
    echo - Optimized project structure >> docs\release_notes.txt
    echo - Simplified build scripts >> docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo System requirements: >> docs\release_notes.txt
    echo - Windows 10/11 ^(64-bit^) >> docs\release_notes.txt
    echo - 8+ GB RAM >> docs\release_notes.txt
    echo - 5+ GB free disk space >> docs\release_notes.txt
)
copy /Y "docs\release_notes.txt" "release\release_notes.txt" >nul

echo OK: Files prepared
echo.

REM ================================================================
REM Final summary
REM ================================================================

echo ================================================================
echo   Release is ready!
echo ================================================================
echo.
echo Version: %VERSION%
echo Location: release\
echo.
echo Contents:
dir /b release\
echo.
echo ================================================================
echo   Next steps:
echo ================================================================
echo.
echo 1. Check files in release\
echo.
echo 2. Upload to GitHub:
echo    .\scripts\build\upload_release.ps1
echo.
echo    Or manually:
echo    https://github.com/YOUR_REPO/releases/new
echo    - Tag: v%VERSION%
echo    - Upload ALL files from release\
echo.
echo ================================================================
echo.

pause
