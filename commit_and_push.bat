@echo off
chcp 65001 >nul
echo ===============================================
echo Git Commit and Push - Bug Fix Report
echo ===============================================
echo.

echo [1/4] Checking git status...
git status
echo.

echo [2/4] Staging changes...
git add licensing/license_client.py
git add ui/main_window.py
git add main.py
git add scripts/build/obfuscate_licensing.py
git add tests/test_licensing.py
git add docs/OBFUSCATION_REGRESSION_TEST.md
git add docs/BUG_FIX_REPORT.md
git add docs/BUILD_AUTOUPDATE.md
git add CHECKLIST.md
echo Done.
echo.

echo [3/4] Creating commit...
git commit -m "fix: critical bugs after HARDEN_LICENSING" -m "Fixes post-HARDEN_LICENSING critical issues:" -m "" -m "STEP 0 (BLOCKER): Fix NameError in LicenseClient.__init__" -m "- Remove undefined REQUESTS_AVAILABLE check" -m "- Add regression test to prevent future NameError issues" -m "" -m "STEP 1: Reliable save on license expiration during processing" -m "- Replace fixed 2s timeout with results_saved signal" -m "- Add 5-minute safety timeout to prevent hanging" -m "- Make quit dialog idempotent" -m "" -m "STEP 2: PyArmor runtime stability for delta updates" -m "- Use -i flag for packages to place runtime inside" -m "- Ensures fixed location: licensing/pyarmor_runtime_000000/" -m "- Prevents accumulation of dead pyarmor_runtime_* folders" -m "" -m "STEP 3: Create obfuscated build regression test checklist" -m "- Full test procedure in docs/OBFUSCATION_REGRESSION_TEST.md" -m "- 12-step verification including license activation, video processing, decompilation attempt" -m "" -m "STEP 4: Final cleanup" -m "- Remove LICENSE_MOCK_MODE mentions from status docs" -m "- Verify runtime monitoring and obfuscation docs are up-to-date" -m "" -m "Changed files:" -m "- licensing/license_client.py (fix NameError)" -m "- ui/main_window.py (add results_saved signal)" -m "- main.py (await results_saved on license expiry)" -m "- scripts/build/obfuscate_licensing.py (add -i flag)" -m "- tests/test_licensing.py (add regression test)" -m "- docs/OBFUSCATION_REGRESSION_TEST.md (new checklist)" -m "- docs/BUG_FIX_REPORT.md (full report)" -m "- docs/BUILD_AUTOUPDATE.md (update obfuscation section)" -m "- CHECKLIST.md (remove LICENSE_MOCK_MODE mention)" -m "" -m "All critical bugs verified and fixed. Ready for regression testing."

if errorlevel 1 (
    echo ERROR: Commit failed
    pause
    exit /b 1
)
echo Done.
echo.

echo [4/4] Pushing to GitHub...
git push
if errorlevel 1 (
    echo ERROR: Push failed
    pause
    exit /b 1
)
echo Done.
echo.

echo ===============================================
echo SUCCESS: All changes committed and pushed!
echo ===============================================
echo.
pause
