<#
.SYNOPSIS
    Автоматическая загрузка релиза Signer PRIME на GitHub
.DESCRIPTION
    Скрипт создает GitHub Release и загружает все необходимые файлы из папки release\
.NOTES
    Требования:
    - GitHub CLI (gh) должен быть установлен и авторизован
    - Файлы должны находиться в папке release\
#>

param(
    [string]$Version = "",
    [string]$RepoOwner = "",
    [string]$RepoName = "",
    [switch]$Draft = $false,
    [switch]$PreRelease = $false
)

# Кодировка UTF-8 для корректного отображения
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  🚀 Загрузка релиза Signer PRIME на GitHub" -ForegroundColor Cyan
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# ============================================================================
# Проверка GitHub CLI
# ============================================================================

Write-Host "[1/6] ⚙️  Проверка GitHub CLI..." -ForegroundColor Yellow

$ghPath = Get-Command gh -ErrorAction SilentlyContinue
if (-not $ghPath) {
    Write-Host "❌ GitHub CLI (gh) не найден в PATH" -ForegroundColor Red
    Write-Host ""
    Write-Host "Установите GitHub CLI:" -ForegroundColor Yellow
    Write-Host "  https://cli.github.com/" -ForegroundColor White
    Write-Host ""
    Write-Host "Или используйте winget:" -ForegroundColor Yellow
    Write-Host "  winget install --id GitHub.cli" -ForegroundColor White
    Write-Host ""
    exit 1
}

# Проверка авторизации
$authStatus = gh auth status 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ GitHub CLI не авторизован" -ForegroundColor Red
    Write-Host ""
    Write-Host "Выполните авторизацию:" -ForegroundColor Yellow
    Write-Host "  gh auth login" -ForegroundColor White
    Write-Host ""
    exit 1
}

Write-Host "✅ GitHub CLI найден и авторизован" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Определение версии
# ============================================================================

Write-Host "[2/6] 📋 Определение версии..." -ForegroundColor Yellow

if (-not $Version) {
    # Читаем версию из version.json
    if (Test-Path "version.json") {
        $versionJson = Get-Content "version.json" -Raw | ConvertFrom-Json
        $Version = $versionJson.version
        Write-Host "   Версия из version.json: $Version" -ForegroundColor White
    } else {
        Write-Host "❌ version.json не найден" -ForegroundColor Red
        Write-Host "   Укажите версию параметром: -Version '2.0.0'" -ForegroundColor Yellow
        exit 1
    }
}

$tagName = "v$Version"
Write-Host "✅ Версия: $Version (тег: $tagName)" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Определение репозитория
# ============================================================================

Write-Host "[3/6] 🔍 Определение репозитория..." -ForegroundColor Yellow

if (-not $RepoOwner -or -not $RepoName) {
    # Пытаемся определить из git remote
    try {
        $remoteUrl = git config --get remote.origin.url
        if ($remoteUrl -match "github\.com[:/](.+?)/(.+?)(\.git)?$") {
            $RepoOwner = $Matches[1]
            $RepoName = $Matches[2] -replace '\.git$', ''
            Write-Host "   Определено из git remote: $RepoOwner/$RepoName" -ForegroundColor White
        } else {
            Write-Host "⚠️  Не удалось определить репозиторий из git remote" -ForegroundColor Yellow
            $RepoOwner = Read-Host "   Введите владельца репозитория (username/organization)"
            $RepoName = Read-Host "   Введите название репозитория"
        }
    } catch {
        Write-Host "⚠️  Не удалось выполнить git команду" -ForegroundColor Yellow
        $RepoOwner = Read-Host "   Введите владельца репозитория (username/organization)"
        $RepoName = Read-Host "   Введите название репозитория"
    }
}

$repoFullName = "$RepoOwner/$RepoName"
Write-Host "✅ Репозиторий: $repoFullName" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Проверка файлов
# ============================================================================

Write-Host "[4/6] 📁 Проверка файлов в папке release\..." -ForegroundColor Yellow

if (-not (Test-Path "release")) {
    Write-Host "❌ Папка release\ не найдена" -ForegroundColor Red
    Write-Host "   Сначала выполните: build_release.bat" -ForegroundColor Yellow
    exit 1
}

# Получаем все части архива
$archiveParts = Get-ChildItem "release\Signer.7z.*" -ErrorAction SilentlyContinue
if (-not $archiveParts) {
    Write-Host "❌ Части архива Signer.7z.* не найдены в release\" -ForegroundColor Red
    exit 1
}

# Проверяем обязательные файлы
$requiredFiles = @(
    "checksum.sha256",
    "release_notes.txt"
)

foreach ($file in $requiredFiles) {
    if (-not (Test-Path "release\$file")) {
        Write-Host "❌ Файл $file не найден в release\" -ForegroundColor Red
        exit 1
    }
}

Write-Host "   Найдено файлов:" -ForegroundColor White
Write-Host "     - Частей архива: $($archiveParts.Count)" -ForegroundColor White
foreach ($part in $archiveParts) {
    $sizeMB = [math]::Round($part.Length / 1MB, 2)
    Write-Host "       • $($part.Name) ($sizeMB MB)" -ForegroundColor Gray
}
Write-Host "     - checksum.sha256" -ForegroundColor White
Write-Host "     - release_notes.txt" -ForegroundColor White

$optionalFiles = @("README.md", "BUILD_AUTOUPDATE.md")
foreach ($file in $optionalFiles) {
    if (Test-Path "release\$file") {
        Write-Host "     - $file" -ForegroundColor White
    }
}

Write-Host "✅ Все необходимые файлы найдены" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Создание релиза
# ============================================================================

Write-Host "[5/6] 🎉 Создание релиза на GitHub..." -ForegroundColor Yellow

# Читаем release notes
$releaseNotes = Get-Content "release\release_notes.txt" -Raw -Encoding UTF8

# Опции релиза
$releaseOptions = @()
if ($Draft) {
    $releaseOptions += "--draft"
    Write-Host "   Режим: черновик (draft)" -ForegroundColor Yellow
}
if ($PreRelease) {
    $releaseOptions += "--prerelease"
    Write-Host "   Режим: пре-релиз (pre-release)" -ForegroundColor Yellow
}

# Проверяем, существует ли релиз
$existingRelease = gh release view $tagName --repo $repoFullName 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "⚠️  Релиз $tagName уже существует" -ForegroundColor Yellow
    $response = Read-Host "   Удалить существующий релиз? (y/N)"
    if ($response -eq "y" -or $response -eq "Y") {
        Write-Host "   Удаление релиза $tagName..." -ForegroundColor Yellow
        gh release delete $tagName --repo $repoFullName --yes
        if ($LASTEXITCODE -ne 0) {
            Write-Host "❌ Не удалось удалить существующий релиз" -ForegroundColor Red
            exit 1
        }
        Write-Host "   ✅ Существующий релиз удален" -ForegroundColor Green
    } else {
        Write-Host "❌ Прервано пользователем" -ForegroundColor Red
        exit 1
    }
}

# Создаем новый релиз
Write-Host "   Создание релиза $tagName..." -ForegroundColor White
$createCmd = "gh release create $tagName --repo $repoFullName --title 'Signer PRIME v$Version' --notes-file 'release\release_notes.txt' $($releaseOptions -join ' ')"
Write-Host "   Команда: $createCmd" -ForegroundColor Gray

Invoke-Expression $createCmd

if ($LASTEXITCODE -ne 0) {
    Write-Host "❌ Не удалось создать релиз" -ForegroundColor Red
    exit 1
}

Write-Host "✅ Релиз создан" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Загрузка файлов
# ============================================================================

Write-Host "[6/6] 📤 Загрузка файлов..." -ForegroundColor Yellow
Write-Host ""

# Загружаем все файлы
$allFiles = @()
$allFiles += Get-ChildItem "release\Signer.7z.*"
$allFiles += Get-ChildItem "release\checksum.sha256"
$allFiles += Get-ChildItem "release\release_notes.txt"

# Опциональные файлы
foreach ($file in $optionalFiles) {
    if (Test-Path "release\$file") {
        $allFiles += Get-ChildItem "release\$file"
    }
}

$current = 0
$total = $allFiles.Count

foreach ($file in $allFiles) {
    $current++
    $percent = [math]::Round(($current / $total) * 100)
    Write-Host "   [$current/$total] Загрузка $($file.Name)... ($percent%)" -ForegroundColor White
    
    gh release upload $tagName $file.FullName --repo $repoFullName --clobber
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "   ❌ Ошибка загрузки $($file.Name)" -ForegroundColor Red
        exit 1
    }
    
    Write-Host "   ✅ $($file.Name) загружен" -ForegroundColor Green
}

Write-Host ""
Write-Host "✅ Все файлы загружены" -ForegroundColor Green
Write-Host ""

# ============================================================================
# Финальная информация
# ============================================================================

Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  ✅ Релиз успешно создан и опубликован!" -ForegroundColor Green
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""
Write-Host "📦 Версия: $Version" -ForegroundColor White
Write-Host "🏷️  Тег: $tagName" -ForegroundColor White
Write-Host "📁 Репозиторий: $repoFullName" -ForegroundColor White
Write-Host ""
Write-Host "🌐 Ссылка на релиз:" -ForegroundColor Yellow
Write-Host "   https://github.com/$repoFullName/releases/tag/$tagName" -ForegroundColor Cyan
Write-Host ""
Write-Host "════════════════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host ""

# Открываем страницу релиза в браузере
$response = Read-Host "Открыть релиз в браузере? (Y/n)"
if ($response -ne "n" -and $response -ne "N") {
    Start-Process "https://github.com/$repoFullName/releases/tag/$tagName"
}

