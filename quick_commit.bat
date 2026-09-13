@echo off
chcp 65001 >nul

echo Staging changes...
git add licensing/license_client.py ui/main_window.py main.py scripts/build/obfuscate_licensing.py tests/test_licensing.py docs/OBFUSCATION_REGRESSION_TEST.md docs/BUG_FIX_REPORT.md docs/BUILD_AUTOUPDATE.md CHECKLIST.md

echo.
echo Committing...
git commit -m "fix: critical bugs after HARDEN_LICENSING - NameError, save on license expiry, PyArmor stability"

echo.
echo Pushing...
git push

echo.
echo Done!
pause
