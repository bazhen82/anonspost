# Step 4: first commit and push to GitHub
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$remote = "https://github.com/bazhen82/anonspost.git"

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    $env:Path = "C:\Program Files\Git\cmd;C:\Program Files\Git\bin;" + $env:Path
}

if (Test-Path ".env") {
    Write-Host "WARN: .env exists locally (will NOT be committed - OK)" -ForegroundColor Yellow
}

if (-not (Test-Path ".git")) {
    git init
    git branch -M main
}

git add -A
$staged = git diff --cached --name-only
if ($staged -match "\.env$") {
    Write-Host "ERROR: .env is staged! Abort." -ForegroundColor Red
    git reset HEAD .env 2>$null
    exit 1
}

$status = git status --porcelain
if (-not $status) {
    Write-Host "Nothing to commit." -ForegroundColor Yellow
} else {
    git commit -m "Initial commit: AnonsPost email mailing panel MVP"
}

$hasOrigin = git remote 2>$null | Select-String "origin"
if (-not $hasOrigin) {
    git remote add origin $remote
} else {
    git remote set-url origin $remote
}

Write-Host ""
Write-Host "Pushing to $remote ..." -ForegroundColor Cyan
git push -u origin main

if ($LASTEXITCODE -eq 0) {
    Write-Host "Done: https://github.com/bazhen82/anonspost" -ForegroundColor Green
}
