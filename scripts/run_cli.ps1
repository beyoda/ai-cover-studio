param([Parameter(Mandatory=$true)][string]$InputAudio, [string]$ModelName = "G_16000")
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path ".venv\Scripts\python.exe")) { powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 }
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
.\.venv\Scripts\python.exe -m aivoice_studio.cli $InputAudio --model $ModelName
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }