<#
.SYNOPSIS
    Загрузка релиза Signer PRIME на GitHub
.DESCRIPTION
    Создаёт GitHub Release и загружает все файлы из папки release\
.NOTES
    Требования: GitHub CLI (gh) должен быть установлен и авторизован
#>

param(
    [string]$Version = "",
    [switch]$Draft = $false,
    [switch]$PreRelease = $false
)

[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🚀 Загрузка релиза на GitHub" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# Проверка GitHub CLI
# ============================================================================

Write-Host "[1/5] Проверка GitHub CLI..." -ForegroundColor Yellow

$ghPath = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghPath) {
    Write-Host "❌ GitHub CLI не найден" -ForegroundColor Red
    Write-Host ""
    Write-Host "Установите: winget install --id GitHub.cli" -ForegroundColor Yellow
    Write-Host "Или скачайте: https://cli.github.com/" -ForegroundColor White
    Write-Host ""
    exit 1
}

$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ GitHub CLI не авторизован" -ForegroundColor Red
    Write-Host ""
    Write-Host "Выполните: gh auth login" -ForegroundColor Yellow
    Write-Host ""
    exit 1
}

Write-Host "✅ GitHub CLI готов" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Определение версии
# ============================================================================

Write-Host "[2/5] Определение версии..." -ForegroundColor Yellow

if (-not $Version) {
    if (Test-Path "version.json") {
        $versionJson = Get-Content "version.json" -Raw | ConvertFrom-Json
        $Version = $versionJson.version
        Write-Host "   Версия: $Version" -ForegroundColor White
    } else {
        Write-Host "❌ version.json не найден" -ForegroundColor Red
        exit 1
    }
}

$tagName = "v$Version"
Write-Host "✅ Тег: $tagName" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Определение репозитория
# ============================================================================

Write-Host "[3/5] Определение репозитория..." -ForegroundColor Yellow

$RepoOwner = ""
$RepoName = ""

try {
    $remoteUrl = git config --get remote.origin.url
    if ($remoteUrl -match "github\.com[:/](.+?)/(.+?)(\.git)?$") {
        $RepoOwner = $Matches[1]
        $RepoName = $Matches[2] -replace '\.git$', ''
        Write-Host "   Репозиторий: $RepoOwner/$RepoName" -ForegroundColor White
    } else {
        Write-Host "⚠️  Не удалось определить репозиторий" -ForegroundColor Yellow
        $RepoOwner = Read-Host "   Владелец репозитория"
        $RepoName = Read-Host "   Название репозитория"
    }
} catch {
    Write-Host "⚠️  Ошибка git" -ForegroundColor Yellow
    $RepoOwner = Read-Host "   Владелец репозитория"
    $RepoName = Read-Host "   Название репозитория"
}

$repoFullName = "$RepoOwner/$RepoName"
Write-Host "✅ Репозиторий: $repoFullName" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Проверка файлов
# ============================================================================

Write-Host "[4/5] Проверка файлов..." -ForegroundColor Yellow

if (-not (Test-Path "release")) {
    Write-Host "❌ Папка release\ не найдена" -ForegroundColor Red
    Write-Host "   Сначала выполните: .\scripts\build\prepare_release.bat" -ForegroundColor Yellow
    exit 1
}

$archiveParts = Get-ChildItem "release\Signer.7z.*" -ErrorAction SilentlyContinue
if (-not $archiveParts) {
    Write-Host "❌ Архивы не найдены в release\" -ForegroundColor Red
    exit 1
}

$requiredFiles = @("checksum.sha256", "release_notes.txt")
foreach ($file in $requiredFiles) {
    if (-not (Test-Path "release\$file")) {
        Write-Host "❌ Файл $file не найден" -ForegroundColor Red
        exit 1
    }
}

Write-Host "   Найдено:" -ForegroundColor White
Write-Host "     - Частей архива: $($archiveParts.Count)" -ForegroundColor White
foreach ($part in $archiveParts) {
    $sizeMB = [math]::Round($part.Length / 1MB, 2)
    Write-Host "       • $($part.Name) ($sizeMB MB)" -ForegroundColor Gray
}
Write-Host "     - checksum.sha256" -ForegroundColor White
Write-Host "     - release_notes.txt" -ForegroundColor White

Write-Host "✅ Все файлы готовы" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Создание релиза
# ============================================================================

Write-Host "[5/5] Создание релиза на GitHub..." -ForegroundColor Yellow
Write-Host ""

$releaseNotes = Get-Content "release\release_notes.txt" -Raw -Encoding UTF8

$releaseOptions = @()
if ($Draft) {
    $releaseOptions += "--draft"
    Write-Host "   Режим: черновик" -ForegroundColor Yellow
}
if ($PreRelease) {
    $releaseOptions += "--prerelease"
    Write-Host "   Режим: пре-релиз" -ForegroundColor Yellow
}

# Проверяем существующий релиз
$existingRelease = gh release view $tagName --repo $repoFullName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "⚠️  Релиз $tagName уже существует" -ForegroundColor Yellow
    $response = Read-Host "   Удалить? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        gh release delete $tagName --repo $repoFullName --yes
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Не удалось удалить релиз" -ForegroundColor Red
            exit 1
        }
        Write-Host "   ✅ Удалён" -ForegroundColor Green
    } else {
        Write-Host "❌ Прервано" -ForegroundColor Red
        exit 1
    }
}

# Создаём релиз
Write-Host "   Создание релиза $tagName..." -ForegroundColor White
gh release create $tagName --repo $repoFullName --title "Signer PRIME v$Version" --notes-file "release\release_notes.txt" $releaseOptions

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Ошибка создания релиза" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Релиз создан" -ForegroundColor Green
Write-Host ""

# Загружаем файлы
Write-Host "Загрузка файлов..." -ForegroundColor Yellow
Write-Host ""

$allFiles = @()
$allFiles += Get-ChildItem "release\Signer.7z.*"
$allFiles += Get-ChildItem "release\checksum.sha256"
$allFiles += Get-ChildItem "release\release_notes.txt"

if (Test-Path "release\README.md") {
    $allFiles += Get-ChildItem "release\README.md"
}
if (Test-Path "release\BUILD_AUTOUPDATE.md") {
    $allFiles += Get-ChildItem "release\BUILD_AUTOUPDATE.md"
}

$current = 0
$total = $allFiles.Count

foreach ($file in $allFiles) {
    $current++
    $percent = [math]::Round(($current / $total) * 100)
    Write-Host "   [$current/$total] $($file.Name)... ($percent%)" -ForegroundColor White
    
    gh release upload $tagName $file.FullName --repo $repoFullName --clobber
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   ❌ Ошибка" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "   ✅ Загружен" -ForegroundColor Green
}

Write-Host ""

# ============================================================================
# Финал
# ============================================================================

Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✅ Релиз опубликован!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📦 Версия: $Version" -ForegroundColor White
Write-Host "🏷️  Тег: $tagName" -ForegroundColor White
Write-Host "📁 Репозиторий: $repoFullName" -ForegroundColor White
Write-Host ""
Write-Host "🌐 Ссылка:" -ForegroundColor Yellow
Write-Host "   https://github.com/$repoFullName/releases/tag/$tagName" -ForegroundColor Cyan
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

$response = Read-Host "Открыть в браузере? (Y/n)"
if ($response -ne "n" -and $response -ne "N") {
    Start-Process "https://github.com/$repoFullName/releases/tag/$tagName"
}
