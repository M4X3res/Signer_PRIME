# Publish only complete releases. Published versions are immutable.
param(
    [string]$Version = "",
    [switch]$Draft,
    [switch]$PreRelease
)
$ErrorActionPreference = "Stop"
Set-Location -LiteralPath (Join-Path $PSScriptRoot "../..")
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

function Invoke-Gh {
    param([string[]]$Arguments)
    $output = & gh @Arguments
    if ($LASTEXITCODE -ne 0) { throw "GitHub CLI failed: $($Arguments -join ' ')" }
    return $output
}

if (-not $Version) { $Version = (Get-Content version.json -Raw | ConvertFrom-Json).version }
if ($Version -notmatch '^\d+\.\d+\.\d+(\.\d+)?$') { throw "Invalid version: $Version" }
$python = Join-Path $PWD '.venv/Scripts/python.exe'
& $python scripts/build/validate_release.py --version $Version
if ($LASTEXITCODE -ne 0) { throw "Release validation failed; nothing was uploaded" }

$files = @(Get-ChildItem release -File | Where-Object {
    $_.Name -match '^Signer\.7z\.\d+$|^delta-from-.*\.(zip|json)$' -or
    $_.Name -in @('checksum.sha256', 'manifest.json', 'release_notes.txt', "SignerInstaller-$Version.exe")
})
$localAssets = @{}
foreach ($file in $files) {
    $localAssets[$file.Name] = @{size=$file.Length; hash=(Get-FileHash -LiteralPath $file.FullName -Algorithm SHA256).Hash.ToLowerInvariant()}
}
Get-Command gh -ErrorAction Stop | Out-Null
Invoke-Gh -Arguments @('auth', 'status') | Out-Null
$repository = (Invoke-Gh -Arguments @('repo', 'view', '--json', 'nameWithOwner') | ConvertFrom-Json).nameWithOwner
# The installer and update client use this repository too.
if ($repository -ne 'M4X3res/Signer_PRIME') { throw "Repository differs from installer/update URLs: $repository" }
$tag = "v$Version"
# Listing authenticated releases includes drafts and propagates network/auth failures.
$pages = Invoke-Gh -Arguments @('api', "repos/$repository/releases?per_page=100", '--paginate', '--slurp') | ConvertFrom-Json
$existing = @($pages | ForEach-Object { $_ } | Where-Object { $_.tag_name -eq $tag })
if ($existing.Count -gt 1) { throw "Multiple releases for $tag" }
if ($existing.Count -eq 1 -and -not $existing[0].draft) {
    throw "Published release $tag is immutable. Increment version.json and prepare a new release."
}
if ($existing.Count -eq 0) {
    $options = @('release', 'create', $tag, '--repo', $repository, '--draft', '--title', "Signer PRIME v$Version", '--notes-file', 'release/release_notes.txt')
    if ($PreRelease) { $options += '--prerelease' }
    Invoke-Gh -Arguments $options
}
foreach ($file in $files) {
    Write-Host "Uploading $($file.Name)..."
    Invoke-Gh -Arguments @('release', 'upload', $tag, $file.FullName, '--repo', $repository, '--clobber')
}
$releaseId = (Invoke-Gh -Arguments @('release', 'view', $tag, '--repo', $repository, '--json', 'databaseId') | ConvertFrom-Json).databaseId
$remote = Invoke-Gh -Arguments @('api', "repos/$repository/releases/$releaseId") | ConvertFrom-Json
if (-not $remote.draft) { throw "Release became public during upload; refusing further changes" }
# Remove only obsolete assets of this unpublished draft.
foreach ($asset in $remote.assets) {
    if (-not $localAssets.ContainsKey($asset.name)) {
        Invoke-Gh -Arguments @('release', 'delete-asset', $tag, $asset.name, '--repo', $repository, '--yes')
    }
}
$remote = Invoke-Gh -Arguments @('api', "repos/$repository/releases/$releaseId") | ConvertFrom-Json
if (@($remote.assets).Count -ne $localAssets.Count) { throw "Incomplete remote asset list; release remains a draft" }
foreach ($asset in $remote.assets) {
    $expected = $localAssets[$asset.name]
    if (-not $expected -or $asset.size -ne $expected.size -or $asset.digest -ne "sha256:$($expected.hash)") {
        throw "Remote size/hash mismatch: $($asset.name). Release remains a draft."
    }
}
$edit = @('release', 'edit', $tag, '--repo', $repository, '--notes-file', 'release/release_notes.txt', "--prerelease=$($PreRelease.IsPresent.ToString().ToLowerInvariant())")
if (-not $Draft) { $edit += '--draft=false' }
Invoke-Gh -Arguments $edit
Write-Host "Release $tag ready (draft=$($Draft.IsPresent)): https://github.com/$repository/releases/tag/$tag"
