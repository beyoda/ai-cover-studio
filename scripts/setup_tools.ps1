# AIVOICE local runtime diagnostics + optional bootstrap (Windows).
#
# Design rules for this script:
#   * Never downloads models, songs, or preview audio.
#   * Never overwrites an existing configuration file.
#   * Never reports success when a required component is missing.
#
# Usage:
#   .\scripts\setup_tools.ps1                  # diagnostics only
#   .\scripts\setup_tools.ps1 -CloneSvcSource  # also clone so-vits-svc source when missing
#   .\scripts\setup_tools.ps1 -Strict          # exit 1 if a required component is missing
#
# This repository ships no voice checkpoint, no UVR weight, and no audio.
# Supply your own rights-cleared assets; see docs/MODEL_GUIDE.md.

[CmdletBinding()]
param(
    [switch]$CloneSvcSource,
    [switch]$Strict
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$missing = New-Object System.Collections.Generic.List[string]
$warnings = New-Object System.Collections.Generic.List[string]

function Write-Section([string]$Title) {
    Write-Host ""
    Write-Host "== $Title ==" -ForegroundColor Cyan
}

function Write-Ok([string]$Message) {
    Write-Host "  [ ok ]   $Message" -ForegroundColor Green
}

function Write-Miss([string]$Message, [string]$Hint) {
    Write-Host "  [miss]   $Message" -ForegroundColor Yellow
    if ($Hint) { Write-Host "           -> $Hint" -ForegroundColor Gray }
    $missing.Add($Message)
}

function Write-WarnLine([string]$Message) {
    Write-Host "  [warn]   $Message" -ForegroundColor Yellow
    $warnings.Add($Message)
}

function Get-YamlScalar([string]$FilePath, [string]$Key) {
    if (-not (Test-Path -LiteralPath $FilePath)) { return $null }
    foreach ($line in (Get-Content -LiteralPath $FilePath -Encoding UTF8)) {
        if ($line -match ("^\s*" + [regex]::Escape($Key) + "\s*:\s*(.+?)\s*$")) {
            $value = $Matches[1].Trim().Trim("'").Trim('"')
            if ($value -eq "" -or $value -eq "null") { return $null }
            return $value
        }
    }
    return $null
}

function Resolve-ConfigPath([string]$Value, [string]$BaseDir) {
    if ([string]::IsNullOrWhiteSpace($Value)) { return $null }
    if ([System.IO.Path]::IsPathRooted($Value)) { return $Value }
    return (Join-Path $BaseDir $Value)
}

Write-Host "AIVOICE setup_tools - diagnostics" -ForegroundColor White
Write-Host "repository root: $Root"

# --- 1. Repository sanity ----------------------------------------------------
Write-Section "[1/6] Repository files"
$voicesPath = Join-Path $Root "config\voices.json"
$svcPath = Join-Path $Root "config\svc.yaml"
$uvrPath = Join-Path $Root "config\uvr.yaml"

foreach ($required in @("config\voices.json", "config\svc.yaml", "config\uvr.yaml", "config\default.yaml", "pyproject.toml")) {
    $full = Join-Path $Root $required
    if (Test-Path -LiteralPath $full) {
        Write-Ok $required
    } else {
        Write-Miss $required "This file is part of the repository; re-clone or restore it."
    }
}

# --- 2. External tooling -----------------------------------------------------
Write-Section "[2/6] External tooling"
if (Get-Command git -ErrorAction SilentlyContinue) {
    Write-Ok ("git " + ((git --version) -replace '^git version ', ''))
} else {
    Write-Miss "git not found on PATH" "Install Git for Windows: https://git-scm.com/download/win"
}

$lfsVersion = $null
try { $lfsVersion = (git lfs version 2>$null) } catch { $lfsVersion = $null }
if ($LASTEXITCODE -eq 0 -and $lfsVersion) {
    Write-Ok ("git-lfs available: " + ($lfsVersion -replace '^git-lfs/', '') + " (only needed if you contribute example assets)")
} else {
    Write-WarnLine "git-lfs not found; the repository itself needs no LFS content to run"
}

$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
if (Test-Path -LiteralPath $venvPy) {
    Write-Ok ".venv found: $venvPy"
} else {
    Write-Miss ".venv not found" "Run: python -m venv .venv ; .\.venv\Scripts\activate ; pip install -e ."
}

if (Get-Command ffmpeg -ErrorAction SilentlyContinue) {
    Write-Ok "ffmpeg found on PATH"
} else {
    Write-Miss "ffmpeg not found on PATH" "Install ffmpeg and add it to PATH; mixing and MP3 export require it."
}

# --- 3. so-vits-svc source ---------------------------------------------------
Write-Section "[3/6] so-vits-svc source tree"
$svcProjectRaw = Get-YamlScalar $svcPath "project_dir"
$svcProject = Resolve-ConfigPath $svcProjectRaw $Root
if (-not $svcProject) {
    Write-Miss "config\svc.yaml has no 'project_dir'" "Set svc.project_dir to your so-vits-svc checkout."
} elseif (Test-Path -LiteralPath (Join-Path $svcProject "inference_main.py")) {
    Write-Ok "so-vits-svc source: $svcProject"
} else {
    if ($CloneSvcSource) {
        Write-Host "  cloning svc-develop-team/so-vits-svc (shallow) -> $svcProject" -ForegroundColor Gray
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $svcProject) | Out-Null
        try {
            git clone --depth 1 https://github.com/svc-develop-team/so-vits-svc.git $svcProject
        } catch {
            Write-WarnLine "git clone failed: $($_.Exception.Message)"
        }
        if (Test-Path -LiteralPath (Join-Path $svcProject "inference_main.py")) {
            Write-Ok "so-vits-svc source cloned"
        } else {
            Write-Miss "clone did not produce inference_main.py" "Check network access, then re-run with -CloneSvcSource."
        }
    } else {
        Write-Miss "so-vits-svc source missing at $svcProject" "Re-run with -CloneSvcSource, or clone it yourself and set svc.project_dir."
    }
}

# --- 4. SVC runtime (CUDA python) -------------------------------------------
Write-Section "[4/6] SVC runtime interpreter"
$svcPyRaw = Get-YamlScalar $svcPath "python"
$svcPy = $null
if ($svcPyRaw -and $svcProject) { $svcPy = Resolve-ConfigPath $svcPyRaw $svcProject }
if ($svcPy -and (Test-Path -LiteralPath $svcPy)) {
    Write-Ok "runtime interpreter: $svcPy"
} else {
    Write-Miss "SVC runtime interpreter not found ($svcPyRaw)" "Create or copy a CUDA/SVC environment under tools\so-vits-svc\workenv, or point svc.python at your own interpreter."
}

# --- 5. UVR model ------------------------------------------------------------
Write-Section "[5/6] UVR separation model"
$uvrModelName = Get-YamlScalar $uvrPath "model_name"
$uvrModelDir = Join-Path $Root "models\uvr"
if (-not $uvrModelName) {
    Write-Miss "config\uvr.yaml has no 'model_name'" "Set uvr.model_name to the separation model filename you provide."
} elseif (Test-Path -LiteralPath (Join-Path $uvrModelDir $uvrModelName)) {
    Write-Ok "UVR model: models\uvr\$uvrModelName"
} else {
    Write-Miss "UVR model missing: models\uvr\$uvrModelName" "This repository ships no model weights. Obtain a model whose license allows your use and place it in models\uvr\ (git-ignored)."
}
if (Test-Path -LiteralPath $venvPy) {
    & $venvPy -c "import importlib.util,sys; sys.exit(0 if importlib.util.find_spec('audio_separator') else 1)" 2>$null | Out-Null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "python package 'audio-separator' importable"
    } else {
        Write-WarnLine "python package 'audio-separator' not importable; real-mode separation will fail"
    }
}

# --- 6. Voice registry -------------------------------------------------------
Write-Section "[6/6] Voice registry (config\voices.json)"
if (-not (Test-Path -LiteralPath $voicesPath)) {
    Write-Miss "config\voices.json missing" "Restore it from the repository."
} else {
    try {
        $registry = Get-Content -LiteralPath $voicesPath -Raw -Encoding UTF8 | ConvertFrom-Json
        $modelsDirRaw = $registry.models_dir
        $modelsDir = Resolve-ConfigPath $modelsDirRaw $Root
        Write-Host "  models_dir: $modelsDir" -ForegroundColor Gray

        $entries = @()
        if ($registry.voices) { $entries = $registry.voices.PSObject.Properties }
        $enabledCount = 0
        foreach ($entry in $entries) {
            $meta = $entry.Value
            $isEnabled = $true
            if ($null -ne $meta.enabled) { $isEnabled = [bool]$meta.enabled }
            if (-not $isEnabled) {
                Write-Host ("  [skip]   {0} (enabled: false)" -f $entry.Name) -ForegroundColor DarkGray
                continue
            }
            $enabledCount++
            $ckpt = Resolve-ConfigPath $meta.checkpoint $modelsDir
            $cfg = Resolve-ConfigPath $meta.config $modelsDir
            $okCkpt = $ckpt -and (Test-Path -LiteralPath $ckpt)
            $okCfg = $cfg -and (Test-Path -LiteralPath $cfg)
            if ($okCkpt -and $okCfg) {
                Write-Ok ("{0}: {1} + {2}" -f $entry.Name, (Split-Path -Leaf $ckpt), (Split-Path -Leaf $cfg))
            } else {
                $detail = @()
                if (-not $okCkpt) { $detail += "checkpoint($ckpt)" }
                if (-not $okCfg) { $detail += "config($cfg)" }
                Write-Miss ("{0}: missing {1}" -f $entry.Name, ($detail -join ", ")) "Place your own rights-cleared model files here, or disable this entry."
            }
        }
        if ($enabledCount -eq 0) {
            Write-Miss "no enabled voice is registered" "Add a voice you are authorized to use to config\voices.json (docs/MODEL_GUIDE.md)."
        }
    } catch {
        Write-Miss "config\voices.json is not valid JSON: $($_.Exception.Message)" "Fix the JSON or restore the template."
    }
}

# --- Summary -----------------------------------------------------------------
Write-Section "Summary"
if ($missing.Count -eq 0) {
    Write-Host "  All checked components are present." -ForegroundColor Green
    Write-Host "  Next: hermes gateway run   (or run the GUI / worker entry points)"
    exit 0
}

Write-Host ("  {0} required component(s) missing; the pipeline is NOT ready to run." -f $missing.Count) -ForegroundColor Yellow
foreach ($item in $missing) { Write-Host "    - $item" -ForegroundColor Yellow }
if ($warnings.Count -gt 0) {
    Write-Host ("  {0} warning(s):" -f $warnings.Count) -ForegroundColor Yellow
    foreach ($item in $warnings) { Write-Host "    - $item" -ForegroundColor DarkYellow }
}
Write-Host ""
Write-Host "  Nothing was downloaded and no configuration file was modified." -ForegroundColor Gray
Write-Host "  See docs/MODEL_GUIDE.md for supplying your own rights-cleared models." -ForegroundColor Gray

if ($Strict) { exit 1 }
exit 0
