# Upload Release Script for Signer PRIME
# This script uploads release files to GitHub

param(
    [string]$Version = "",
    [switch]$Draft = $false,
    [switch]$PreRelease = $false
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host "  Upload Release to GitHub" -ForegroundColor Cyan
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host ""

# Check GitHub CLI
Write-Host "[1/5] Checking GitHub CLI..." -ForegroundColor Yellow

$ghPath = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghPath) {
    Write-Host "ERROR: GitHub CLI not found" -ForegroundColor Red
    Write-Host ""
    Write-Host "Install: winget install --id GitHub.cli" -ForegroundColor Yellow
    Write-Host "Or download: https://cli.github.com/" -ForegroundColor White
    Write-Host ""
    exit 1
}

$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERROR: GitHub CLI not authorized" -ForegroundColor Red
    Write-Host ""
    Write-Host "Run: gh auth login" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "OK: GitHub CLI ready" -ForegroundColor Green
Write-Host ""

# Get version
Write-Host "[2/5] Getting version..." -ForegroundColor Yellow

if (-not $Version) {
    if (Test-Path "version.json") {
        $versionJson = Get-Content "version.json" -Raw | ConvertFrom-Json
        $Version = $versionJson.version
        Write-Host "   Version: $Version" -ForegroundColor White
    } else {
        Write-Host "ERROR: version.json not found" -ForegroundColor Red
        exit 1
    }
}

$tagName = "v$Version"
Write-Host "OK: Tag: $tagName" -ForegroundColor Green
Write-Host ""

# Get repository
Write-Host "[3/5] Getting repository..." -ForegroundColor Yellow

$RepoOwner = ""
$RepoName = ""

try {
    $remoteUrl = git config --get remote.origin.url
    if ($remoteUrl -match "github\.com[:/](.+?)/(.+?)(\.git)?$") {
        $RepoOwner = $Matches[1]
        $RepoName = $Matches[2] -replace '\.git$', ''
        Write-Host "   Repository: $RepoOwner/$RepoName" -ForegroundColor White
    } else {
        Write-Host "WARNING: Could not determine repository" -ForegroundColor Yellow
        $RepoOwner = Read-Host "   Repository owner"
        $RepoName = Read-Host "   Repository name"
    }
} catch {
    Write-Host "WARNING: Git error" -ForegroundColor Yellow
    $RepoOwner = Read-Host "   Repository owner"
    $RepoName = Read-Host "   Repository name"
}

$repoFullName = "$RepoOwner/$RepoName"
Write-Host "OK: Repository: $repoFullName" -ForegroundColor Green
Write-Host ""

# Check files
Write-Host "[4/5] Checking files..." -ForegroundColor Yellow

if (-not (Test-Path "release")) {
    Write-Host "ERROR: release\ folder not found" -ForegroundColor Red
    Write-Host "   Run first: .\scripts\build\prepare_release.bat" -ForegroundColor Yellow
    exit 1
}

$archiveParts = Get-ChildItem "release\Signer.7z.*" -ErrorAction SilentlyContinue
if (-not $archiveParts) {
    Write-Host "ERROR: Archive parts not found in release\" -ForegroundColor Red
    exit 1
}

$requiredFiles = @("checksum.sha256", "release_notes.txt")
foreach ($file in $requiredFiles) {
    if (-not (Test-Path "release\$file")) {
        Write-Host "ERROR: File $file not found" -ForegroundColor Red
        exit 1
    }
}

Write-Host "   Found:" -ForegroundColor White
Write-Host "     - Archive parts: $($archiveParts.Count)" -ForegroundColor White
foreach ($part in $archiveParts) {
    $sizeMB = [math]::Round($part.Length / 1MB, 2)
    Write-Host "       - $($part.Name) ($sizeMB MB)" -ForegroundColor Gray
}
Write-Host "     - checksum.sha256" -ForegroundColor White
Write-Host "     - release_notes.txt" -ForegroundColor White

Write-Host "OK: All files ready" -ForegroundColor Green
Write-Host ""

# Create or update release
Write-Host "[5/5] Creating release on GitHub..." -ForegroundColor Yellow
Write-Host ""

$releaseOptions = @()
if ($Draft) {
    $releaseOptions += "--draft"
    Write-Host "   Mode: draft" -ForegroundColor Yellow
}
if ($PreRelease) {
    $releaseOptions += "--prerelease"
    Write-Host "   Mode: pre-release" -ForegroundColor Yellow
}

# Check if release exists
$existingRelease = gh release view $tagName --repo $repoFullName 2>&1
$releaseExists = $LASTEXITCODE -eq 0

if ($releaseExists) {
    Write-Host "WARNING: Release $tagName already exists" -ForegroundColor Yellow
    Write-Host "   Old files will be deleted and new files will be uploaded" -ForegroundColor Yellow
    Write-Host ""
    
    $response = Read-Host "   Update release? (Y/n)"
    if ($response -eq "n" -or $response -eq "N") {
        Write-Host "ERROR: Cancelled by user" -ForegroundColor Red
        exit 1
    }
    
    # Delete old assets
    Write-Host "   Deleting old files..." -ForegroundColor White
    
    # Get list of assets
    $assets = gh release view $tagName --repo $repoFullName --json assets --jq '.assets[].name' 2>&1
    if ($LASTEXITCODE -eq 0 -and $assets) {
        $assetList = $assets -split "`n" | Where-Object { $_ -ne "" }
        foreach ($asset in $assetList) {
            Write-Host "      Deleting $asset..." -ForegroundColor Gray
            gh release delete-asset $tagName $asset --repo $repoFullName --yes 2>&1 | Out-Null
        }
        Write-Host "   OK: Old files deleted" -ForegroundColor Green
    } else {
        Write-Host "   INFO: No old files found" -ForegroundColor Gray
    }
    
    Write-Host ""
} else {
    # Create new release
    Write-Host "   Creating release $tagName..." -ForegroundColor White
    gh release create $tagName --repo $repoFullName --title "Signer PRIME v$Version" --notes-file "release\release_notes.txt" $releaseOptions

    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create release" -ForegroundColor Red
        exit 1
    }

    Write-Host "OK: Release created" -ForegroundColor Green
    Write-Host ""
}

# Upload files
Write-Host "Uploading files..." -ForegroundColor Yellow
Write-Host ""

$allFiles = @()
$allFiles += Get-ChildItem "release\Signer.7z.*"
$allFiles += Get-ChildItem "release\checksum.sha256"
$allFiles += Get-ChildItem "release\manifest.json" -ErrorAction Stop
$allFiles += Get-ChildItem "release\delta-from-*.zip" -ErrorAction SilentlyContinue
$allFiles += Get-ChildItem "release\delta-from-*.json" -ErrorAction SilentlyContinue
$allFiles += Get-ChildItem "release\release_notes.txt"

if (Test-Path "release\README.md") {
    $allFiles += Get-ChildItem "release\README.md"
}
if (Test-Path "release\BUILD_AUTOUPDATE.md") {
    $allFiles += Get-ChildItem "release\BUILD_AUTOUPDATE.md"
}

$total = $allFiles.Count
Write-Host "   Total files: $total" -ForegroundColor White
Write-Host "   Starting sequential upload..." -ForegroundColor White
Write-Host ""

# Sequential upload with progress
$current = 0
$failed = @()

foreach ($file in $allFiles) {
    $current++
    $percent = [math]::Round(($current / $total) * 100)
    $sizeMB = [math]::Round($file.Length / 1MB, 2)
    
    Write-Host "[$current/$total] ($percent%) Uploading: $($file.Name) ($sizeMB MB)..." -ForegroundColor Cyan
    
    # Show progress bar
    $barLength = 50
    $filled = [math]::Floor($barLength * $current / $total)
    $empty = $barLength - $filled
    $bar = ("[" + ("=" * $filled) + ("." * $empty) + "]")
    Write-Host "   $bar" -ForegroundColor Gray
    
    # Upload file
    $output = gh release upload $tagName $file.FullName --repo $repoFullName --clobber 2>&1
    
    if ($LASTEXITCODE -ne 0) {
        $failed += $file.Name
        Write-Host "   ERROR: Upload failed" -ForegroundColor Red
        Write-Host ""
    } else {
        Write-Host "   OK: Upload complete" -ForegroundColor Green
        Write-Host ""
    }
}

if ($failed.Count -gt 0) {
    Write-Host ""
    Write-Host "ERROR: Failed to upload $($failed.Count) file(s)" -ForegroundColor Red
    foreach ($file in $failed) {
        Write-Host "   - $file" -ForegroundColor Red
    }
    exit 1
}

Write-Host ""

# Final message
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host "  Release published!" -ForegroundColor Green
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Version: $Version" -ForegroundColor White
Write-Host "Tag: $tagName" -ForegroundColor White
Write-Host "Repository: $repoFullName" -ForegroundColor White
Write-Host ""
Write-Host "Link:" -ForegroundColor Yellow
Write-Host "   https://github.com/$repoFullName/releases/tag/$tagName" -ForegroundColor Cyan
Write-Host ""
Write-Host "===============================================================" -ForegroundColor Cyan
Write-Host ""

$response = Read-Host "Open in browser? (Y/n)"
if ($response -ne "n" -and $response -ne "N") {
    Start-Process "https://github.com/$repoFullName/releases/tag/$tagName"
}
