# AnonsPost — подготовка к первому push на GitHub (запускать из корня проекта)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    Write-Host "Git не найден. Установите: https://git-scm.com/download/win" -ForegroundColor Red
    exit 1
}

$secrets = @(".env", "anonspost.db", "*.db")
foreach ($pattern in $secrets) {
    Get-ChildItem -Path $Root -Filter $pattern -ErrorAction SilentlyContinue | ForEach-Object {
        Write-Host "WARN: найден $($_.Name) — в GitHub не попадёт (.gitignore)" -ForegroundColor Yellow
    }
}

if (-not (Test-Path ".git")) {
    git init
    git branch -M main
    Write-Host "Git-репозиторий создан." -ForegroundColor Green
}

git add -A
git status

Write-Host ""
Write-Host "Дальше (после создания репозитория на GitHub):" -ForegroundColor Cyan
Write-Host '  git commit -m "Initial commit: AnonsPost MVP"'
Write-Host '  git remote add origin https://github.com/USER/anonspost.git'
Write-Host "  git push -u origin main"
