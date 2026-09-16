# Fix smart quotes in upload_release.ps1
$inputFile = 'scripts\build\upload_release.ps1'
$content = [System.IO.File]::ReadAllText($inputFile, [System.Text.Encoding]::UTF8)

# Replace smart quotes with regular quotes
$content = $content -replace [char]0x2018, "'" # left single quote
$content = $content -replace [char]0x2019, "'" # right single quote  
$content = $content -replace [char]0x201C, '"' # left double quote
$content = $content -replace [char]0x201D, '"' # right double quote

# Save with UTF-8 no BOM
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($inputFile, $content, $utf8NoBom)

Write-Host "Fixed smart quotes in upload_release.ps1" -ForegroundColor Green
