# AIVOICE v1.3-0.3.3 — Real Worker E2E smoke wrapper
# Clears Hermes PYTHONPATH pollution, sets project src, forwards args.
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing venv python: $Py"
}

$env:PYTHONPATH = Join-Path $Root "src"
$env:PYTHONIOENCODING = "utf-8"
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue

Set-Location $Root
Write-Host "AIVOICE Worker E2E smoke (real CoverService, no mock)..."
& $Py (Join-Path $PSScriptRoot "smoke_worker_e2e.py") @args
exit $LASTEXITCODE
