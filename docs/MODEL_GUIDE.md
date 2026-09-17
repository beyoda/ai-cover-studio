# Model Guide

AIVOICE currently integrates with so-vits-svc-style inference through the local pipeline. Training is not performed inside AIVOICE; train or obtain a compatible model separately, then register it.

**This repository distributes no model files.** [`config/voices.json`](../config/voices.json) ships as an empty template (`example_voice`, `"enabled": false`, `default_voice_id: null`), and `models/` plus `tools/` are git-ignored. Every runner needs a model you are allowed to use.

## Compatible Voice Models

The current registry and adapter path expects:

| Item | Requirement |
| --- | --- |
| Framework | so-vits-svc 4.x-compatible inference files |
| Checkpoint | generator checkpoint such as `G_10000.pth` |
| Config | matching `config.json` from the same training run |
| Speaker | at least one speaker in the config, matching the command speaker |
| Encoder | config and runtime must use the same feature encoder expected by the model |
| Location | under `models_dir` from `config/voices.json`, or absolute paths |

`models_dir` resolution: a relative value is anchored at the repository root, an absolute value is used as-is. `config/svc.yaml` ships the same value so both services look at one directory.

The current code does not directly load RVC, GPT-SoVITS, OpenVoice, or arbitrary ONNX voice-conversion weights. Supporting those formats would require an adapter change, not only a registry edit.

## Vocal Separation Model

The UVR step is configured separately in [`config/uvr.yaml`](../config/uvr.yaml). It ships with a portable command that uses `{python}` (the interpreter running AIVOICE) and expects the model at `models/uvr/<uvr.model_name>`, which is git-ignored. Place a separation model whose license allows your use there, or point `--model_file_dir` at another directory.

## Check Your Environment

```powershell
.\scripts\setup_tools.ps1
```

This reports, per component, whether the SVC source tree, the CUDA interpreter, the UVR model, `ffmpeg`, and every enabled registry entry's files are present. It never downloads anything and never edits your configuration. It exits non-zero with `-Strict`, which makes it usable as a preflight gate.

## Add A Voice

1. Place the authorized checkpoint and matching config under the configured models directory, normally `tools/so-vits-svc/logs/44k/`.
2. Add an entry to [`config/voices.json`](../config/voices.json). The shipped `example_voice` entry is a copy-ready template.
3. Keep `enabled: true` only for models that are ready to use.
4. Use aliases for natural-language matching, but avoid aliases that conflict with another voice.
5. Run `.\scripts\setup_tools.ps1` to confirm the files resolve, then run the registry tests.

Example:

```json
"my_voice": {
  "display_name": "My Voice",
  "description": "Authorized test voice",
  "checkpoint": "G_10000.pth",
  "config": "config.json",
  "enabled": true,
  "metadata": {
    "language": "zh",
    "style": "pop"
  },
  "aliases": ["my_voice", "My Voice"]
}
```

Verified registry behavior:

- `VoiceRegistry.load()` reads `config/voices.json`.
- `models_dir` can be relative to the project root or absolute.
- Relative `checkpoint` and `config` values are resolved under `models_dir`.
- `resolve()` accepts `voice_id`, display name, checkpoint stem, and aliases.
- `require_paths()` fails fast if either file is missing.
- In `CoverRequest`, `voice_id` wins over legacy `model_name`.

## Training Notes

Use the upstream so-vits-svc documentation for the exact training commands for your selected version. General flow:

1. Prepare voice data that you own or are authorized to use.
2. Clean, segment, and resample the material according to the upstream model requirements.
3. Extract the matching feature representation and pitch features.
4. Train in the so-vits-svc project.
5. Copy the selected `G_*.pth` and matching config into the runtime model directory.
6. Register the model in `config/voices.json`.

Do not publish models trained on third-party voices unless you can document the right to redistribute them.

## Demo Asset Policy

The public repository should use only rights-cleared demo assets. If you want an online preview, add a short audio file whose source recording, song/composition, voice model, and generated output can all be publicly redistributed.

Recommended replacements:

- a self-recorded or contributor-authorized voice model;
- a public-domain melody with documented source;
- model weights whose license explicitly allows redistribution in this repo;
- a README note linking to external instructions rather than shipping restricted weights.
