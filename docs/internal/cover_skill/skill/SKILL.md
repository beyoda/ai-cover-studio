---
name: aivoice-cover
description: >-
  Run a local AI cover (UVR → so-vits-svc → mix → MP3) via AI Cover Studio's
  Cover Service. Use when the user asks to cover/翻唱 a song, convert vocals
  with a SVC model, or generate an AI cover MP3 on this machine.
---

# AI Cover Studio — Cover Skill

## When to use

- User wants a **local AI cover / 翻唱** of an audio file
- User mentions so-vits-svc models (`G_16000`, `G_27200`, etc.), pitch, or reverb
- User asks Hermes to generate `cover.mp3` without opening the GUI

## When not to use

- General audio editing unrelated to this pipeline
- Training SVC models
- Changing UVR/SVC install or GPU drivers (ops tasks, not this skill)

## Architecture reminder

```
This Skill → Cover Service (HTTP) → Pipeline Adapter → existing Pipeline
```

Do **not** call `audio-separator`, `inference_main.py`, or `ffmpeg` directly.  
Do **not** import or invoke `aivoice_studio.core.pipeline` from the skill.

GUI users keep using the desktop app; this skill is for agent/Hermes invocation only.

## Prerequisites

1. Project root: `C:\path\to\repo` (or the deployed project root)
2. Cover Service listening (default `http://127.0.0.1:17890`)
3. Health check:

```http
GET http://127.0.0.1:17890/v1/health
```

If down, tell the user to start Cover Service (implementation provides the start command later). Do not invent a pipeline bypass.

## Primary tool call

Prefer the synchronous endpoint:

```http
POST http://127.0.0.1:17890/v1/cover/run
Content-Type: application/json

{
  "input_audio": "D:/path/to/song.mp3",
  "model_name": "G_16000",
  "pitch": 0,
  "reverb": "关闭",
  "f0_method": "rmvpe",
  "export_mp3": true,
  "client": "hermes"
}
```

### Parameters

| Name | Required | Notes |
|------|----------|-------|
| `input_audio` | yes | Absolute local path Hermes can read |
| `model_name` | yes | From `GET /v1/cover/models` when unsure |
| `pitch` | no | Integer -12..12, default 0 |
| `reverb` | no | One of: `关闭`, `录音棚`, `现场`, `大教堂` |
| `f0_method` | no | Default `rmvpe` |
| `export_mp3` | no | Default true |
| `accompaniment` | no | Optional instrumental path |
| `client` | no | Set `hermes` |

## Async alternative

1. `POST /v1/cover/jobs` with body = CoverRequest (`wait: false`)
2. Poll `GET /v1/cover/jobs/{job_id}` until `status` is `succeeded` or `failed`
3. Read `result.mp3_path` / `result.error`

## Success response (shape)

```json
{
  "success": true,
  "job_id": "e49d3ec8f4e6",
  "wav_path": "C:/path/to/repo/outputs/.../cover.wav",
  "mp3_path": "C:/path/to/repo/outputs/.../cover.mp3",
  "error": null,
  "model_name": "G_16000",
  "pitch": 0,
  "reverb": "关闭"
}
```

Report `mp3_path` to the user. Optionally mention `wav_path`.

## Failure handling

- `success: false` → show `error` verbatim; suggest `logs/pipeline.log`
- HTTP 503 / connection refused → Cover Service not running
- HTTP 400 → fix paths/parameters; do not retry blindly with different models unless user asks

## Models

```http
GET http://127.0.0.1:17890/v1/cover/models
```

If unavailable, fall back to asking the user which checkpoint name to use (e.g. `G_16000`).

## Progress (optional)

If using async jobs, surface `stage` + `percent` + `message` from the job snapshot.  
Stages mirror the existing pipeline: `uvr` → `svc` → `mixing` → `exporting` → `done` | `failed`.

## Invariants

- Existing GUI/CLI/Pipeline behavior is out of scope for this skill
- One cover = one Cover Service job = one Adapter call = one `Pipeline.run`
- Never claim GPU/UVR optimizations were applied unless the Service health payload says so
