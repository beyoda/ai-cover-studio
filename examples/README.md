# Examples (v1.0)

## Online demo (play in browser) — ~25 seconds

**Open this file (not anything under `audio/`):**

https://github.com/beyoda/ai-cover-studio/blob/main/examples/demo/eason_preview.mp3

It is a short clip from a completed **example_voice** cover of《示例曲目》.  
If you hear ~12s of tone/noise, you opened the old synthetic test file (removed). Hard-refresh or use the link above.

Model requirements & training: [docs/MODEL_GUIDE.md](../docs/MODEL_GUIDE.md)

| Path | What |
|------|------|
| `demo/eason_preview.mp3` | **Playable showcase** (~25s example_voice clip, Git LFS) |
| `voices/example_voice/G_27200.pth` | Example SVC checkpoint (Git LFS, ~599MB) |
| `voices/example_voice/config1.json` | Matching config |
| `models/uvr/UVR_MDXNET_Main.onnx` | Example UVR model (Git LFS, ~64MB) |

## Disclaimer

**Full text (Chinese):** [docs/DISCLAIMER.md](../docs/DISCLAIMER.md)

- The `example_voice` checkpoint and `demo/eason_preview.mp3` are **technical demos only**. They are **not** an official license or commercial voice pack.
- Do **not** use example voices or song covers for commercial distribution without proper rights.
- Replace example assets with voices and audio you are allowed to use.

## Install into runtime paths

```powershell
.\scripts\setup_tools.ps1
```
