$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    Write-Error "Missing venv python: $Py"
}
$env:PYTHONPATH = Join-Path $Root "src"
# Avoid Hermes / other env pollution
Remove-Item Env:VIRTUAL_ENV -ErrorAction SilentlyContinue
Set-Location $Root
Write-Host "Starting AIVOICE worker skeleton (Ctrl+C to stop)..."
& $Py -m aivoice_studio.worker @args
