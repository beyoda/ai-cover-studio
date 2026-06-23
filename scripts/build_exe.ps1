$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path ".venv\Scripts\pyinstaller.exe")) { powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 }
.\.venv\Scripts\pyinstaller.exe --noconfirm --windowed --name "AI Cover Studio" --add-data "config;config" --paths "src" "src\aivoice_studio\app.py"
Write-Host "Build finished: dist\AI Cover Studio"
