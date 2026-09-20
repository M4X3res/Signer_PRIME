# PowerShell script for git commit and push
Write-Host ""
Write-Host "================================================================"
Write-Host "  Git Commit and Push - Production Bugfixes"
Write-Host "================================================================"
Write-Host ""

# Read commit message
$commitMsg = Get-Content -Path ".git_commit_msg.txt" -Raw

# Create commit
Write-Host "[1/2] Creating commit..."
git commit -F .git_commit_msg.txt

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to create commit" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "OK: Commit created" -ForegroundColor Green
Write-Host ""

# Push to remote
Write-Host "[2/2] Pushing to remote..."
git push

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to push" -ForegroundColor Red
    Write-Host ""
    Write-Host "Possible reasons:"
    Write-Host "- No access to remote repository"
    Write-Host "- Authentication required"
    Write-Host "- Conflict with remote branch"
    Write-Host ""
    Write-Host "Try manual push: git push"
    Write-Host ""
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host "OK: Push completed successfully" -ForegroundColor Green
Write-Host ""
Write-Host "================================================================"
Write-Host "  Done!"
Write-Host "================================================================"
Write-Host ""
Write-Host "Changes have been pushed to remote repository."
Write-Host ""

Read-Host "Press Enter to exit"
