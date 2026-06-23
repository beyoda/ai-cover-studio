$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
$env:PYTHONPATH = (Join-Path (Get-Location) "src")

Write-Host "♫ AI Cover Studio — Server + Feishu Bot" -ForegroundColor Green
Write-Host ""

# ── ngrok binary ─────────────────────────────────
if ($env:FEISHU_APP_ID -and (Test-Path "ngrok.exe")) {
    Write-Host "ngrok: starting tunnel..." -ForegroundColor Cyan
    Start-Process -PassThru -NoNewWindow ".\ngrok.exe" -ArgumentList "start","feishu","--config=ngrok.yml","--log=stdout"
    Start-Sleep -Seconds 5
    Write-Host "ngrok: tunnel started" -ForegroundColor Green
}

Write-Host ""
Write-Host "Starting server..." -ForegroundColor Gray
Write-Host "  Web UI: http://localhost:5000" -ForegroundColor Cyan
Write-Host ""

.\.venv\Scripts\python.exe -m aivoice_studio.server.api
