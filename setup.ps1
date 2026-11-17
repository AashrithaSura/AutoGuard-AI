# Install the AutoGuard AI environment on Windows.
# Run from the project root:  powershell -ExecutionPolicy Bypass -File .\setup.ps1
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$venv = Join-Path $root ".venv"
$python = Join-Path $venv "Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "Creating Python 3.11 virtual environment..." -ForegroundColor Cyan
    py -3.11 -m venv $venv
}

Write-Host "Upgrading pip..." -ForegroundColor Cyan
& $python -m pip install --upgrade pip

Write-Host "Installing CPU PyTorch wheels (large download)..." -ForegroundColor Cyan
& $python -m pip install --index-url https://download.pytorch.org/whl/cpu torch torchvision

Write-Host "Installing project requirements..." -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $root "requirements.txt")

Write-Host "Installing development/test requirements..." -ForegroundColor Cyan
& $python -m pip install -r (Join-Path $root "requirements-dev.txt")

Write-Host ""
Write-Host "Setup complete. Start the app with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe -m uvicorn api.main:app --host 127.0.0.1 --port 8000"
Write-Host "Then open http://127.0.0.1:8000"
Write-Host ""
Write-Host "Optional: seed the labelled demo dashboard with:" -ForegroundColor Green
Write-Host "  .\.venv\Scripts\python.exe scripts\seed_demo.py --days 21"
