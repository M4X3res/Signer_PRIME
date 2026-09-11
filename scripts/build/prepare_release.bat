@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

echo.
echo ================================================================
echo   Preparing Signer PRIME Release
echo ================================================================
echo.

REM Get version from version.json
for /f "tokens=2 delims=:, " %%a in ('type version.json ^| findstr "version"') do (
    set VERSION=%%~a
)
echo Version: %VERSION%
echo.

REM ================================================================
REM [1/5] Check dependencies
REM ================================================================

echo [1/5] Checking dependencies...
echo.

python --version >nul 2>&1
if errorlevel 1 (
    echo ERROR: Python not found
    pause
    exit /b 1
)

python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo ERROR: PyInstaller not installed
    echo Run: pip install pyinstaller
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
REM [2/5] Clean old builds
REM ================================================================

echo [2/5] Cleaning old builds...
rmdir /s /q "dist\Signer" 2>nul
rmdir /s /q "dist\Updater" 2>nul
rmdir /s /q "build" 2>nul
rmdir /s /q "release" 2>nul
echo OK: Cleaned
echo.

REM ================================================================
REM [3/5] Build application
REM ================================================================

echo [3/5] Building application...
echo.

echo    Building Signer.exe...
pyinstaller signer.spec --noconfirm
if errorlevel 1 (
    echo ERROR: Failed to build Signer.exe
    pause
    exit /b 1
)

echo    Building Updater.exe...
pyinstaller updater.spec --noconfirm
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

echo    Files copied successfully
echo OK: Build completed
echo.

REM ================================================================
REM [4/5] Create archive
REM ================================================================

echo [4/5] Creating archive...
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
REM [5/5] Calculate checksums
REM ================================================================

echo [5/5] Calculating SHA-256 checksums...
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
REM Prepare release/ folder
REM ================================================================

echo Moving files to release\...
move /Y Signer.7z.* ..\release\ >nul
move /Y checksum.sha256 ..\release\ >nul

cd ..

REM Copy additional files
copy /Y "README.md" "release\README.md" >nul
if exist "docs\BUILD_AUTOUPDATE.md" copy /Y "docs\BUILD_AUTOUPDATE.md" "release\BUILD_AUTOUPDATE.md" >nul

REM Create release notes if not exists
if not exist "docs\release_notes.txt" (
    echo Signer PRIME v%VERSION% > docs\release_notes.txt
    echo. >> docs\release_notes.txt
    echo Changes in this version: >> docs\release_notes.txt
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
