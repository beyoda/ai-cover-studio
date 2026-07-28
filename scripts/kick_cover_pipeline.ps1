$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root ".venv\Scripts\python.exe"
if (-not (Test-Path $Py)) {
    $Py = "python"
}
$Script = Join-Path $PSScriptRoot "kick_cover_pipeline.py"
& $Py $Script @args
exit $LASTEXITCODE
