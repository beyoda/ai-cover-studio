param(
    [Parameter(Mandatory=$true)][string]$InputAudio,
    [string]$ModelName = ""
)
$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path ".venv\Scripts\python.exe")) { powershell -ExecutionPolicy Bypass -File .\scripts\setup.ps1 }
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
# --model is optional: with no value the CLI picks the first model installed
# locally, and reports clearly when none is present (nothing ships with the repo).
if ([string]::IsNullOrWhiteSpace($ModelName)) {
    .\.venv\Scripts\python.exe -m aivoice_studio.cli $InputAudio
} else {
    .\.venv\Scripts\python.exe -m aivoice_studio.cli $InputAudio --model $ModelName
}
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
