# Examples (v1.0)

These files are meant for **clone + one-click setup**, not for shipping the full 10GB `tools/` tree.

## Online demo (play in browser)

Open on GitHub to hear the example voice:

- **[demo/eason_preview.mp3](demo/eason_preview.mp3)** — short example_voice cover of `audio/sample_input.mp3` (synthetic input, not a commercial song)

Model requirements & training: [docs/MODEL_GUIDE.md](../docs/MODEL_GUIDE.md)

| Path | What |
|------|------|
| `demo/eason_preview.mp3` | **Playable showcase** (~480KB, Git LFS) |
| `voices/example_voice/G_27200.pth` | Example SVC checkpoint (Git LFS, ~599MB) |
| `voices/example_voice/config1.json` | Matching config |
| `models/uvr/UVR_MDXNET_Main.onnx` | Example UVR model (Git LFS, ~64MB) |
| `audio/sample_input.mp3` | Synthetic 12s test tone (not a commercial song) |

## Disclaimer

- The `example_voice` checkpoint and preview are provided **only as a technical example** for personal / research wiring of AIVOICE.
- Do **not** use voice models or song covers for commercial distribution without proper rights.
- Replace example assets with voices/songs you are allowed to use.

## Install into runtime paths

From repo root:

```powershell
.\scripts\setup_tools.ps1
```
