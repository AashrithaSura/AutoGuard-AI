# Start the AutoGuard AI web app.
$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$python = Join-Path $root ".venv\Scripts\python.exe"

if (-not (Test-Path $python)) {
    Write-Host "No .venv found. Run .\setup.ps1 first." -ForegroundColor Red
    exit 1
}

Set-Location $root
Write-Host "AutoGuard AI: http://127.0.0.1:8000" -ForegroundColor Cyan
& $python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
