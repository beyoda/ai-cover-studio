# AIVOICE one-click local tools bootstrap (Windows)
# - Pulls Git LFS example assets (example_voice voice + UVR + sample mp3)
# - Ensures so-vits-svc source tree exists (clone if missing; does NOT upload 5GB workenv)
# - Copies example models into the runtime paths CoverService expects

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

Write-Host "== AIVOICE setup_tools =="
Write-Host "root: $Root"

function Ensure-Dir([string]$Path) {
    New-Item -ItemType Directory -Force -Path $Path | Out-Null
}

# 1) Git LFS assets
Write-Host "`n[1/5] Git LFS pull (examples)..."
try {
    git lfs install | Out-Null
    git lfs pull
} catch {
    Write-Warning "git lfs pull failed: $_. Install Git LFS from https://git-lfs.com then re-run."
}

$easonPth = Join-Path $Root "examples\voices\example_voice\G_27200.pth"
$uvrOnnx = Join-Path $Root "examples\models\uvr\UVR_MDXNET_Main.onnx"
$sampleMp3 = Join-Path $Root "examples\audio\sample_input.mp3"
if (-not (Test-Path $easonPth)) { throw "Missing $easonPth — run: git lfs pull" }
if (-not (Test-Path $uvrOnnx)) { throw "Missing $uvrOnnx — run: git lfs pull" }

# 2) so-vits-svc source (code only)
$SvcRoot = Join-Path $Root "tools\so-vits-svc"
Write-Host "`n[2/5] so-vits-svc source -> $SvcRoot"
Ensure-Dir (Join-Path $Root "tools")
if (-not (Test-Path (Join-Path $SvcRoot "inference_main.py"))) {
    Write-Host "Cloning svc-develop-team/so-vits-svc (shallow)..."
    git clone --depth 1 https://github.com/svc-develop-team/so-vits-svc.git $SvcRoot
} else {
    Write-Host "so-vits-svc already present."
}

# 3) Copy example voice + UVR into runtime locations
Write-Host "`n[3/5] Install example models into runtime paths..."
$Logs44k = Join-Path $SvcRoot "logs\44k"
Ensure-Dir $Logs44k
Copy-Item -Force $easonPth (Join-Path $Logs44k "G_27200.pth")
Copy-Item -Force (Join-Path $Root "examples\voices\example_voice\config1.json") (Join-Path $Logs44k "config1.json")

$UvrDir = Join-Path $Root "models\uvr"
Ensure-Dir $UvrDir
Copy-Item -Force $uvrOnnx (Join-Path $UvrDir "UVR_MDXNET_Main.onnx")
Write-Host "OK: example_voice -> $Logs44k"
Write-Host "OK: UVR  -> $UvrDir"

# 4) SVC workenv (CUDA) — cannot ship on GitHub (~5GB)
Write-Host "`n[4/5] Check SVC workenv..."
$WorkPy = Join-Path $SvcRoot "workenv\python.exe"
if (Test-Path $WorkPy) {
    Write-Host "Found workenv: $WorkPy"
} else {
    Write-Warning @"
SVC workenv not found ($WorkPy).
GitHub cannot host the ~5GB CUDA Python env.
Options:
  A) Copy your backup tools\so-vits-svc\workenv here
  B) Create a CUDA venv under tools\so-vits-svc\workenv and install so-vits-svc requirements
Then re-run this script or edit config\svc.yaml python path.
"@
}

# 5) Rewrite config\svc.yaml paths to this machine (keep voices.json as-is)
Write-Host "`n[5/5] Patch config\svc.yaml paths to this repo..."
$SvcYaml = Join-Path $Root "config\svc.yaml"
@"
svc:
  enabled: true
  mode: so-vits-svc
  python: $Root\tools\so-vits-svc\workenv\python.exe
  project_dir: $Root\tools\so-vits-svc
  inference_script: inference_main.py
  command: '{python} {script} -m {model_path} -c {config_path} -n {input_name} -t {pitch} -s {speaker} -f0p {f0_method} -wf {output_format}'
  models_dir: $Root\tools\so-vits-svc\logs\44k
  default_model: G_27200
  f0_method: rmvpe
  pitch: 0
  speaker: output
  output_format: wav
"@ | Set-Content -Path $SvcYaml -Encoding utf8

Write-Host "`n== Done =="
Write-Host "Example voice : example_voice (示例歌手) / G_27200.pth"
Write-Host "Sample audio  : $sampleMp3"
Write-Host "Next:"
Write-Host "  1) Ensure ffmpeg in PATH"
Write-Host "  2) .\scripts\setup_tools.ps1   (this script)"
Write-Host "  3) hermes gateway run"
Write-Host "  4) Feishu: 用示例歌手声音翻唱 examples 里的歌名，或本地:"
Write-Host "     用 example_voice 翻唱 examples/audio/sample_input.mp3"
