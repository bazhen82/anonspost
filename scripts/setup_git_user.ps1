# Step 2: git user.name and user.email (run once)
param(
    [Parameter(Mandatory = $true)]
    [string]$Name,
    [Parameter(Mandatory = $true)]
    [string]$Email
)

git config --global user.name $Name
git config --global user.email $Email
Write-Host "OK: user.name  = $(git config --global user.name)" -ForegroundColor Green
Write-Host "OK: user.email = $(git config --global user.email)" -ForegroundColor Green
Write-Host ""
Write-Host "GitHub username needed on step 3 (e.g. bazhen82)." -ForegroundColor Cyan
