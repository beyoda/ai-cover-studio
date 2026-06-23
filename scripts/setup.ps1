$ErrorActionPreference = "Stop"
Set-Location (Split-Path -Parent $PSScriptRoot)
if (!(Test-Path ".venv")) { py -3 -m venv .venv }
.\.venv\Scripts\python.exe -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
.\.venv\Scripts\pip.exe install -e ".[dev]"
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Environment ready. Run scripts\run_gui.ps1 to start."